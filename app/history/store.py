"""Persistent conversation history: keeps the last 10 conversations per signed-in user (pinned stay on top).

* SQL Server backend: writes to schema `[app]` (`sql/rls_mssql.sql`) via the app login.
* DuckDB backend (or `APP_HISTORY_BACKEND=sqlite`): writes to `data/app_history.sqlite`.
"""
from __future__ import annotations

import hmac
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer, MetaData, Table, Unicode, UnicodeText,
                        create_engine, delete, event, insert, select, update)
from sqlalchemy.engine import Engine

from app.config import ROOT, backend, env

MAX_CONVERSATIONS = 10


class ConversationLimit(Exception):
    """Raised when all 10 conversations are pinned."""


@dataclass
class Conversation:
    conversation_id: str
    user_id: str
    persona: str
    title: str
    created_at: datetime
    updated_at: datetime
    is_pinned: bool


def normalize_user(display_name: str) -> str:
    s = re.sub(r"\s+", "_", (display_name or "").strip().lower())
    s = re.sub(r"[^a-z0-9_.\-]", "", s)
    return s[:80]


def check_access_code(code: str) -> bool:
    expected = env("APP_ACCESS_CODE")
    if not expected:
        return False
    return hmac.compare_digest(str(code or "").encode(), str(expected).encode())


def _tables(schema: str | None) -> tuple[MetaData, Table, Table, Table]:
    md = MetaData(schema=schema)
    conv = Table("app_conversation", md,
                 Column("conversation_id", Unicode(36), primary_key=True),
                 Column("user_id", Unicode(80), nullable=False, index=True),
                 Column("persona", Unicode(50), nullable=False),
                 Column("title", Unicode(120), nullable=False),
                 Column("created_at", DateTime, nullable=False),
                 Column("updated_at", DateTime, nullable=False),
                 Column("is_pinned", Boolean, nullable=False, default=False))
    fk = f"{schema}.app_conversation.conversation_id" if schema else "app_conversation.conversation_id"
    msg = Table("app_message", md,
                Column("message_id", Unicode(36), primary_key=True),
                Column("conversation_id", Unicode(36), ForeignKey(fk, ondelete="CASCADE"), nullable=False, index=True),
                Column("seq", Integer, nullable=False),
                Column("role", Unicode(10), nullable=False),
                Column("content_markdown", UnicodeText, nullable=False),
                Column("payload_json", UnicodeText, nullable=True),
                Column("created_at", DateTime, nullable=False))
    state = Table("app_conversation_state", md,
                  Column("conversation_id", Unicode(36), ForeignKey(fk, ondelete="CASCADE"), primary_key=True),
                  Column("agent_state_json", UnicodeText, nullable=False))
    return md, conv, msg, state


@lru_cache(maxsize=4)
def _sqlite_engine(path: str) -> Engine:
    eng = create_engine(f"sqlite:///{path}")

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return eng


class ConversationStore:
    def __init__(self, engine: Engine | None = None, schema: str | None = None):
        if engine is None:
            if backend() == "mssql" and (env("APP_HISTORY_BACKEND", "") or "").lower() != "sqlite":
                from app.db import get_engine
                engine, schema = get_engine("__history__"), "app"
            else:
                path = ROOT / (env("APP_HISTORY_DB", "data/app_history.sqlite") or "data/app_history.sqlite")
                path.parent.mkdir(parents=True, exist_ok=True)
                engine = _sqlite_engine(str(path))
        self.engine = engine
        self.md, self.conv, self.msg, self.state = _tables(schema)
        if engine.dialect.name == "sqlite":
            self.md.create_all(engine)

    def list(self, user_id: str) -> list[Conversation]:
        c = self.conv
        stmt = (select(c).where(c.c.user_id == user_id)
                .order_by(c.c.is_pinned.desc(), c.c.updated_at.desc()).limit(MAX_CONVERSATIONS))
        with self.engine.connect() as conn:
            return [Conversation(r.conversation_id, r.user_id, r.persona, r.title,
                                 r.created_at, r.updated_at, bool(r.is_pinned))
                    for r in conn.execute(stmt)]

    def load(self, user_id: str, cid: str) -> tuple[Conversation | None, list[dict], dict]:
        c, m, s = self.conv, self.msg, self.state
        with self.engine.connect() as conn:
            crow = conn.execute(select(c).where(c.c.conversation_id == cid, c.c.user_id == user_id)).fetchone()
            if crow is None:
                return None, [], {}
            mrows = conn.execute(select(m).where(m.c.conversation_id == cid).order_by(m.c.seq)).fetchall()
            srow = conn.execute(select(s).where(s.c.conversation_id == cid)).fetchone()
        msgs = []
        for r in mrows:
            if r.role == "user":
                msgs.append({"role": "user", "content": r.content_markdown})
            else:
                msgs.append({"role": "assistant", "answer": json.loads(r.payload_json or "{}")})
        mem = json.loads(srow.agent_state_json) if srow and srow.agent_state_json else {}
        return Conversation(crow.conversation_id, crow.user_id, crow.persona, crow.title,
                            crow.created_at, crow.updated_at, bool(crow.is_pinned)), msgs, mem

    def save_turn(self, user_id: str, cid: str | None, persona: str, question: str,
                  payload: dict, memory: dict) -> str:
        c, m, s = self.conv, self.msg, self.state
        now = datetime.now()
        with self.engine.begin() as conn:
            existing = (conn.execute(select(c).where(c.c.conversation_id == cid, c.c.user_id == user_id)).fetchone()
                        if cid else None)
            if existing is None:
                all_rows = conn.execute(
                    select(c).where(c.c.user_id == user_id).order_by(c.c.is_pinned.desc(), c.c.updated_at.desc())
                ).fetchall()
                if len(all_rows) >= MAX_CONVERSATIONS:
                    unpinned = [r for r in all_rows if not r.is_pinned]
                    if not unpinned:
                        raise ConversationLimit("All 10 conversations are pinned. Unpin one to start a new thread.")
                    for victim in unpinned[MAX_CONVERSATIONS - 1 - (len(all_rows) - len(unpinned)):]:
                        conn.execute(delete(m).where(m.c.conversation_id == victim.conversation_id))
                        conn.execute(delete(s).where(s.c.conversation_id == victim.conversation_id))
                        conn.execute(delete(c).where(c.c.conversation_id == victim.conversation_id))
                cid = str(uuid.uuid4())
                title = (question or "New conversation").strip()[:90]
                conn.execute(insert(c).values(
                    conversation_id=cid, user_id=user_id, persona=persona,
                    title=title, created_at=now, updated_at=now, is_pinned=False,
                ))
                seq = 0
            else:
                conn.execute(update(c).where(c.c.conversation_id == cid).values(updated_at=now, persona=persona))
                last_seq = conn.execute(
                    select(m.c.seq).where(m.c.conversation_id == cid).order_by(m.c.seq.desc()).limit(1)
                ).scalar()
                seq = (int(last_seq) + 1) if last_seq is not None else 0

            conn.execute(insert(m).values(
                message_id=str(uuid.uuid4()), conversation_id=cid, seq=seq,
                role="user", content_markdown=question, payload_json=None, created_at=now,
            ))
            conn.execute(insert(m).values(
                message_id=str(uuid.uuid4()), conversation_id=cid, seq=seq + 1,
                role="assistant", content_markdown=payload.get("answer_markdown", ""),
                payload_json=json.dumps(payload, default=str), created_at=now,
            ))
            conn.execute(delete(s).where(s.c.conversation_id == cid))
            conn.execute(insert(s).values(conversation_id=cid, agent_state_json=json.dumps(memory, default=str)))
        return cid

    def rename(self, user_id: str, cid: str, new_title: str) -> None:
        title = (new_title or "").strip()[:120]
        if not title:
            return
        with self.engine.begin() as conn:
            conn.execute(update(self.conv).where(
                self.conv.c.conversation_id == cid, self.conv.c.user_id == user_id
            ).values(title=title))

    def pin(self, user_id: str, cid: str, pinned: bool) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(self.conv).where(
                self.conv.c.conversation_id == cid, self.conv.c.user_id == user_id
            ).values(is_pinned=bool(pinned)))

    def delete(self, user_id: str, cid: str) -> None:
        with self.engine.begin() as conn:
            own = conn.execute(select(self.conv.c.conversation_id).where(
                self.conv.c.conversation_id == cid, self.conv.c.user_id == user_id
            )).fetchone()
            if own:
                conn.execute(delete(self.msg).where(self.msg.c.conversation_id == cid))
                conn.execute(delete(self.state).where(self.state.c.conversation_id == cid))
                conn.execute(delete(self.conv).where(self.conv.c.conversation_id == cid))
