"""
The pay page, as a stranger on a phone gets it from an email.

This is the highest-traffic screen and the only one most people ever see. The
API suite already covers what the endpoint returns; these cover what only a
real browser and separate processes can show — that the page lays out at
phone width, and that tapping a button leaves something behind in the
database once the request is over.
"""

import re

import pytest
from playwright.sync_api import expect

from app.domain.parsing import ParsedRow
from app.models.accounts import Identity, Person
from app.models.campaigns import Obligation, ObligationStatus, PaymentHandle
from app.services import campaigns as svc


@pytest.fixture
def obligation(db):
    """
    One open bill: Alex fronted $360 for courts.

    Four ways, not three — the fronter is a row on the roster too, which is
    why the amount is read off the obligation below rather than written out.
    """
    from datetime import UTC, datetime

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
    # Reachable, as if each had signed in once; see tests/conftest.py `joined`.
    for participant in campaign.participants:
        for identity in participant.person.identities:
            if identity.kind == Identity.KIND_EMAIL:
                identity.verified_at = datetime.now(UTC)
    db.commit()
    svc.open_campaign(db, campaign)
    db.commit()

    return (
        db.query(Obligation)
        .filter_by(campaign_id=campaign.id)
        .order_by(Obligation.amount_cents.desc())
        .first()
    )


def status_of(db, obligation) -> str:
    """Read back from the database, outside any session the request used."""
    db.expire_all()
    return db.get(Obligation, obligation.id).status


def test_a_stranger_sees_what_they_owe_and_to_whom(phone, obligation):
    phone.goto(f"/pay/{obligation.pay_token}")

    expect(phone.get_by_text("You owe Alex")).to_be_visible()
    expect(phone.get_by_text(f"${obligation.amount_cents / 100:,.2f}")).to_be_visible()
    expect(phone.get_by_text("for Courts")).to_be_visible()
    expect(phone.get_by_role("button", name="I've sent it")).to_be_visible()


def test_the_page_does_not_scroll_sideways_on_a_phone(phone, obligation):
    """jsdom never lays anything out, so only a browser can catch this."""
    phone.goto(f"/pay/{obligation.pay_token}")
    expect(phone.get_by_text("You owe Alex")).to_be_visible()

    overflow = phone.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0, f"the page is {overflow}px wider than the phone"


def test_saying_it_was_sent_settles_it_and_it_stays_settled(db, phone, obligation):
    """
    The write has to outlive the request.

    The API suite cannot show this: its requests share one session, so a
    flushed-but-uncommitted row is still visible to the next call. Here the
    reload is a new request in a new session, and the database is read from a
    different process altogether.
    """
    phone.goto(f"/pay/{obligation.pay_token}")
    phone.get_by_role("button", name="I've sent it").click()

    expect(phone.get_by_text("Settled. Nothing more to do.")).to_be_visible()
    assert status_of(db, obligation) == ObligationStatus.PAID

    phone.reload()
    expect(phone.get_by_text("Settled with Alex")).to_be_visible()


def test_taking_it_back_reopens_the_bill(db, phone, obligation):
    phone.goto(f"/pay/{obligation.pay_token}")
    phone.get_by_role("button", name="I've sent it").click()
    phone.get_by_role("button", name=re.compile("Didn't mean to")).click()

    expect(phone.get_by_role("button", name="I've sent it")).to_be_visible()
    assert status_of(db, obligation) == ObligationStatus.OPEN

    phone.reload()
    expect(phone.get_by_text("You owe Alex")).to_be_visible()


def test_the_link_from_an_old_email_still_lands(phone, obligation):
    """`/p/` is what the Django app mailed, and a link in an email is forever."""
    phone.goto(f"/p/{obligation.pay_token}")

    expect(phone).to_have_url(re.compile(f"/pay/{obligation.pay_token}$"))
    expect(phone.get_by_text("You owe Alex")).to_be_visible()


def test_a_dead_link_says_so(phone, console_errors, db):
    phone.goto("/pay/not-a-real-token")

    expect(phone.get_by_text("This link does not work")).to_be_visible()
    # The 404 itself is logged by the browser; that one is expected.
    console_errors[:] = [e for e in console_errors if "404" not in e]
