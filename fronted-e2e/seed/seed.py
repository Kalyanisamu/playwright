"""
Test data, written through Fronted's own services.

    $FRONTED_ROOT/api/.venv/bin/python seed/seed.py reset     # drop, create, migrate
    ... seed.py truncate                                     # empty every table
    ... seed.py bill                                         # one open bill, as JSON
    ... seed.py stranger                                     # somebody on no campaign
    ... seed.py cookie <person-id>                           # a signed-in session
    ... seed.py status <obligation-id>                       # read one back

The tests are TypeScript, but the data is made here, in Python, on purpose.
Going through `services.campaigns` means a test bill is split by the same
`domain.splitting` rule as a real one and lands in the ledger the way a real
one does. Hand-written INSERTs from TypeScript would be a second, quieter
implementation of both — the thing AGENTS.md calls out as having billed a
group something the manager never saw.

Every command runs in its own process and commits, because the servers under
test are other processes and see nothing less.
"""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# Never the database in fronted's .env. `reset` DROPS what it is pointed at,
# and the .env points at the development database — so the URL is chosen here
# and refused unless it is visibly a throwaway one.
DATABASE_URL = os.environ.get(
    "E2E_DATABASE_URL",
    "postgresql+psycopg://fronted:fronted@localhost:5432/fronted_e2e",
)
if "e2e" not in DATABASE_URL.rsplit("/", 1)[-1]:
    raise SystemExit(f"refusing a database whose name lacks 'e2e': {DATABASE_URL}")
os.environ["DATABASE_URL"] = DATABASE_URL

ROOT = Path(os.environ.get("FRONTED_ROOT", "/Volumes/Data/src/fronted")).resolve()
API = ROOT / "api"
sys.path.insert(0, str(API))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


def reset() -> None:
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
        cwd=API, env=os.environ, check=True, capture_output=True,
    )


def truncate() -> None:
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        names = conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' "
            "AND tablename <> 'alembic_version'"
        )).scalars().all()
        if names:
            joined = ", ".join(f'"{n}"' for n in names)
            conn.execute(text(f"TRUNCATE {joined} RESTART IDENTITY CASCADE"))
    engine.dispose()


def session():
    return sessionmaker(bind=create_engine(DATABASE_URL), expire_on_commit=False)()


def bill() -> dict:
    """
    One open bill: Alex fronted $360 for courts.

    Four ways, not three — the fronter is a row on the roster too, which is
    why the amount goes back to the test rather than being written out there.
    """
    from app.domain.parsing import ParsedRow
    from app.models.accounts import Identity, Person
    from app.models.campaigns import Obligation, PaymentHandle
    from app.services import campaigns as svc

    db = session()
    manager = Person(display_name="Alex")
    db.add(manager)
    db.flush()
    db.add(PaymentHandle(person_id=manager.id, rail="venmo",
                         handle_value="@alex", is_default=True))

    campaign = svc.create_campaign(db, manager=manager, label="Courts",
                                   total_cents=36000)
    svc.add_participants(db, campaign, [
        ParsedRow(name=name, email=f"{name.lower()}@example.com")
        for name in ("Maria", "Devi", "Tomas")
    ])
    # Reachable, as if each had signed in once; see fronted's
    # tests/conftest.py `joined`.
    for participant in campaign.participants:
        for identity in participant.person.identities:
            if identity.kind == Identity.KIND_EMAIL:
                identity.verified_at = datetime.now(UTC)
    db.commit()
    svc.open_campaign(db, campaign)
    db.commit()

    obligation = (
        db.query(Obligation)
        .filter_by(campaign_id=campaign.id)
        .order_by(Obligation.amount_cents.desc())
        .first()
    )
    return {
        "managerId": str(manager.id),
        "campaignToken": campaign.campaign_token,
        "obligationId": str(obligation.id),
        "payToken": obligation.pay_token,
        "amountCents": obligation.amount_cents,
        "fronterName": "Alex",
        "label": "Courts",
    }


def stranger() -> dict:
    """Somebody signed in who is on nothing — the person a 404 is for."""
    from app.models.accounts import Person

    db = session()
    person = Person(display_name="Sam")
    db.add(person)
    db.commit()
    return {"personId": str(person.id)}


def cookie(person_id: str) -> str:
    """
    The session cookie fronted would set after a sign-in, for this person.

    How the suite gets past OAuth without going through it. After the
    provider hands back, all fronted keeps is a cookie holding a person id,
    signed by Starlette's SessionMiddleware with `SECRET_KEY` — which provider
    it was is not in it. So a cookie signed here, with the same key, is
    exactly what a real sign-in would have left, and the server checks its
    signature like any other. Driving Google's own page instead is how a
    suite meets CAPTCHAs and locked test accounts.

    The key is read from fronted's .env, which is also where the API under
    test reads it: SECRET_KEY is deliberately not overridden in its
    environment, so the two cannot disagree.

    The format is SessionMiddleware's — base64 JSON under an itsdangerous
    TimestampSigner. If Starlette ever changes it, every signed-in spec fails
    at once on a sign-in screen, which is the right way for that to show up.
    """
    import base64

    import itsdangerous

    from app.auth.session import SESSION_KEY
    from app.config import settings

    data = base64.b64encode(json.dumps({SESSION_KEY: person_id}).encode())
    return itsdangerous.TimestampSigner(str(settings.secret_key)).sign(data).decode()


def status(obligation_id: str) -> dict:
    from app.models.campaigns import Obligation

    return {"status": str(session().get(Obligation, obligation_id).status)}


def main(argv: list[str]) -> int:
    command, *rest = argv or ["help"]
    if command == "reset":
        reset()
    elif command == "truncate":
        truncate()
    elif command == "bill":
        print(json.dumps(bill()))
    elif command == "stranger":
        print(json.dumps(stranger()))
    elif command == "cookie":
        print(cookie(*rest))
    elif command == "status":
        print(json.dumps(status(*rest)))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
