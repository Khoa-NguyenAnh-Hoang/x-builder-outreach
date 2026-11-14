"""LIVE controlled send (T13) — opt-in: `uv run pytest -m live -k send`.

Sends exactly ONE DM to the operator's OWN account (dev_test mode, allowlist =
self), on an approved draft, through the full gate chain. This is the brief's
"real sending works" proof — no stranger ever receives a message from the test.
"""

import pytest

from src.config import get_settings
from src.db import connect, init_db, store
from src.integrations.x_client import OfficialXClient
from src.models import Draft, Prospect
from src.services.outreach import send_approved_draft

pytestmark = pytest.mark.live


def test_live_controlled_send_to_own_account():
    settings = get_settings()
    from src.integrations.x_auth import load_tokens
    if not (settings.x_client_id and load_tokens()):
        pytest.skip("run `uv run python -m src.integrations.x_auth` once to authorize")

    client = OfficialXClient.from_settings(settings)
    me = client.get_me()
    own_id = str(me.id)

    # dev_test mode: the only permitted recipient is the operator's own account
    strict = settings.model_copy(update={"test_recipient_allowlist": own_id})

    conn = connect(":memory:")
    init_db(conn)
    pid = store.upsert_prospect(conn, Prospect(
        x_user_id=own_id, username=me.username, source="seed"))
    did = store.create_draft(conn, Draft(
        prospect_id=pid,
        text="T13 controlled test DM from the x-builder-outreach prototype — sent to "
             "its own operator account. Safe to delete. 🤖",
        evidence_refs=[], generator="template"))
    store.set_draft_status(conn, did, "approved", approved_at=store.now_iso())

    outcome = send_approved_draft(conn, client, pid, strict, "dev_test")
    assert outcome.status == "sent", f"controlled send failed: {outcome.model_dump()}"
    assert outcome.message_id
    print(f"controlled DM delivered to @{me.username} (own account), message id {outcome.message_id}")

    # never double-messages: the second send is refused
    second = send_approved_draft(conn, client, pid, strict, "dev_test")
    assert second.status == "denied"
