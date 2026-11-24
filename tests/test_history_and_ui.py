"""Conversation history persistence (10-thread cap, pin, rename, delete) and Streamlit UI smoke tests."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.history.store import ConversationLimit, ConversationStore, normalize_user
from app.ui import branding as B


def test_branding_single_source_of_truth():
    assert B.APP_NAME == "CORE Pulse"
    assert B.APP_FULL_NAME == ""
    assert B.TAGLINE == ""
    assert B.AUTHOR == "Rohan Luniya"
    assert B.AUTHOR_LINE == "Developed and maintained by Rohan Luniya"
    assert B.footer_line() == "CORE Pulse v1.0.0 · Developed and maintained by Rohan Luniya"
    assert B.LOGO_PATH.exists()
    assert B.APP_NAME in B.page_title("Chat")


def test_conversation_store_crud_and_ten_thread_eviction(tmp_path):
    db_file = tmp_path / "hist.sqlite"
    eng = create_engine(f"sqlite:///{db_file}")
    store = ConversationStore(engine=eng)
    uid = normalize_user("Alex Morgan")
    assert uid == "alex_morgan"

    cids = []
    for i in range(12):
        cid = store.save_turn(uid, None, "Global CORE Program Lead", f"Question {i}", {"answer_markdown": f"Ans {i}"}, {"turn": i})
        cids.append(cid)

    listed = store.list(uid)
    assert len(listed) == 10, "Must retain at most 10 conversations per user"

    # Pin, rename, load, delete
    top_id = listed[0].conversation_id
    store.pin(uid, top_id, True)
    store.rename(uid, top_id, "Executive Wave Review")
    conv, msgs, state = store.load(uid, top_id)
    assert conv is not None
    assert conv.is_pinned is True
    assert conv.title == "Executive Wave Review"
    assert len(msgs) == 2
    assert state["turn"] == 11

    store.delete(uid, top_id)
    assert len(store.list(uid)) == 9


def test_conversation_limit_when_all_ten_pinned(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'pinned.sqlite'}")
    store = ConversationStore(engine=eng)
    uid = "pinned_user"
    for i in range(10):
        cid = store.save_turn(uid, None, "Global CORE Program Lead", f"Q{i}", {"answer_markdown": "ok"}, {})
        store.pin(uid, cid, True)
    with pytest.raises(ConversationLimit):
        store.save_turn(uid, None, "Global CORE Program Lead", "Q11", {"answer_markdown": "ok"}, {})


def test_streamlit_ui_signin_and_chat_smoke():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(B.ASSETS.parents[1] / "ui" / "streamlit_app.py"), default_timeout=30)
    at.run()
    assert not at.exception
    # Sign in via session state and verify Chat renders KPI cards and answers a question in rules mode
    at.session_state["auth_user"] = "smoke_tester"
    at.session_state["auth_name"] = "Smoke Tester"
    at.session_state["model_select"] = "rules (no LLM)"
    at.session_state["pending"] = "What is current CORE adoption overall?"
    at.run()
    assert not at.exception
    assert len(at.session_state["messages"]) == 2
    assert at.session_state["messages"][1]["answer"]["status"] == "ok"
