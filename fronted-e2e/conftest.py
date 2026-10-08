"""
End-to-end: a real browser, against a real API and a real Vite, on a database
of their own.

    cd web && ../api/.venv/bin/pytest e2e -q

The Vitest suite renders components in jsdom and the API suite drives routes
through one shared session, and each is blind to something the other cannot
see. The API tests share a session across requests, so a route that flushes
and never commits passes them and loses the write in production — that hid
SMS consent for its whole life. jsdom never lays anything out, so a pay page
that scrolls sideways on a phone passes Vitest. This suite runs the thing a
payer actually gets: separate processes, a fresh session per request, Chromium
at phone width.

Its own ports, 8010 and 8011, not the 8000/8001 that AGENTS.md pins. Those are
pinned for the OAuth callback, and nothing here signs in through a provider;
borrowing them would collide with a dev server, and a Vite that silently
proxied to somebody else's API would test their data, not ours. Both servers
are started with strict ports and refuse to run if anything is already there.

Its own database too, `fronted_e2e`, dropped and rebuilt per run. Not the test
database the API suite uses: two suites sharing one rebuilt database drop it
out from under each other, and the failures look like real bugs.
"""

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1]
API = WEB.parent / "api"

DATABASE_URL = os.environ.get(
    "E2E_DATABASE_URL",
    "postgresql+psycopg://fronted:fronted@localhost:5432/fronted_e2e",
)
API_PORT = int(os.environ.get("E2E_API_PORT", 8010))
WEB_PORT = int(os.environ.get("E2E_WEB_PORT", 8011))
BASE_URL = f"http://localhost:{WEB_PORT}"

# Before anything imports `app`: settings are read once, and the seeding in
# this process has to write to the database the servers read from.
SERVER_ENV = {
    "DATABASE_URL": DATABASE_URL,
    "SITE_URL": f"http://localhost:{API_PORT}",
    "WEB_URL": BASE_URL,
    "DEBUG": "true",
    # Nothing leaves the machine. Blank keys rather than trusting the
    # allowlists alone: opening a campaign plans reminders, and a .env with
    # real credentials in it is the normal state of a developer's laptop.
    "RESEND_API_KEY": "",
    "TWILIO_ACCOUNT_SID": "",
    "TWILIO_AUTH_TOKEN": "",
    "DEV_EMAIL_ALLOWLIST": "",
    "DEV_SMS_ALLOWLIST": "",
    "TURNSTILE_SITE_KEY": "",
    "TURNSTILE_SECRET": "",
    "MEDIA_BUCKET": "",
}
os.environ.update(SERVER_ENV)
sys.path.insert(0, str(API))


def _listening(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("localhost", port)) == 0


def _wait(url: str, proc: subprocess.Popen, log: Path, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"{url} exited early:\n{log.read_text()[-3000:]}")
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError(f"{url} never came up:\n{log.read_text()[-3000:]}")


@pytest.fixture(scope="session")
def engine():
    from sqlalchemy import create_engine, text

    admin = create_engine(
        DATABASE_URL.rsplit("/", 1)[0] + "/postgres", isolation_level="AUTOCOMMIT"
    )
    name = DATABASE_URL.rsplit("/", 1)[-1]
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()

    subprocess.run(
        [str(API / ".venv/bin/alembic"), "upgrade", "head"],
        cwd=API, env={**os.environ, **SERVER_ENV}, check=True, capture_output=True,
    )
    eng = create_engine(DATABASE_URL)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def servers(engine):
    for port in (API_PORT, WEB_PORT):
        if _listening(port):
            raise RuntimeError(
                f"something is already listening on {port}; "
                "set E2E_API_PORT / E2E_WEB_PORT to run beside it"
            )

    logs = Path(tempfile.mkdtemp(prefix="fronted-e2e-"))
    procs = []
    try:
        api_log = logs / "api.log"
        procs.append(subprocess.Popen(
            [str(API / ".venv/bin/uvicorn"), "app.main:app", "--port", str(API_PORT)],
            cwd=API, env={**os.environ, **SERVER_ENV},
            stdout=api_log.open("w"), stderr=subprocess.STDOUT,
        ))
        _wait(f"http://localhost:{API_PORT}/_health", procs[-1], api_log)

        web_log = logs / "web.log"
        procs.append(subprocess.Popen(
            [str(WEB / "node_modules/.bin/vite"), "--port", str(WEB_PORT),
             "--strictPort"],
            cwd=WEB, env={**os.environ, "API_PORT": str(API_PORT)},
            stdout=web_log.open("w"), stderr=subprocess.STDOUT,
        ))
        _wait(BASE_URL, procs[-1], web_log)
        yield BASE_URL
    finally:
        for proc in procs:
            proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


@pytest.fixture
def db(engine, servers):
    """
    A session for seeding, and empty tables afterwards.

    Seeds are COMMITTED — the servers are other processes and see nothing
    less. Which is also the point: a fixture that only flushed would be the
    shared-session blind spot all over again.
    """
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        with engine.begin() as conn:
            names = conn.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                "AND tablename <> 'alembic_version'"
            )).scalars().all()
            if names:
                joined = ", ".join(f'"{n}"' for n in names)
                conn.execute(text(f"TRUNCATE {joined} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def console_errors():
    """
    Every console error and uncaught exception the page produced.

    Asserted empty after each test, because a page that threw while rendering
    usually still renders SOMETHING, and that something passes a text check.
    A test that expects an error (a 404 logs one) clears the list itself.
    """
    errors: list[str] = []
    yield errors
    assert not errors, f"console errors: {errors}"


@pytest.fixture
def phone(browser, servers, console_errors):
    """A page at phone width, which is where the pay link is opened."""
    context = browser.new_context(
        base_url=servers,
        viewport={"width": 390, "height": 844},
        device_scale_factor=2,
        is_mobile=True,
        has_touch=True,
    )
    page = context.new_page()
    page.on("console", lambda m: m.type == "error" and console_errors.append(m.text))
    page.on("pageerror", lambda e: console_errors.append(str(e)))
    yield page
    context.close()
