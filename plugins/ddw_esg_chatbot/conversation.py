"""Conversation manager — session and message lifecycle."""

import datetime
import uuid
from typing import Optional


class ConversationManager:
    """In-memory conversation manager.

    In production, all data flows through SQLAlchemy via routes.py.
    This manager is used by the test suite and for lightweight in-process state.
    """

    def __init__(self):
        self.sessions: dict[str, dict] = {}
        self.messages: dict[str, list[dict]] = {}

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def create_session(
        self,
        user_id: str,
        topic: str = "",
        metadata: Optional[dict] = None,
        company_id: Optional[str] = None,
    ) -> dict:
        session_id = uuid.uuid4().hex[:12]
        now = datetime.datetime.utcnow().isoformat()
        session = {
            "id": session_id,
            "user_id": user_id,
            "company_id": company_id,
            "topic": topic,
            "status": "active",
            "metadata": metadata or {},
            "message_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        self.sessions[session_id] = session
        self.messages[session_id] = []
        return session

    def get_session(self, session_id: str) -> Optional[dict]:
        return self.sessions.get(session_id)

    def list_sessions(
        self,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        results = []
        for s in self.sessions.values():
            if user_id and s["user_id"] != user_id:
                continue
            if status and s["status"] != status:
                continue
            results.append(s)
            if len(results) >= limit:
                break
        return results

    def close_session(self, session_id: str) -> dict:
        session = self.sessions.get(session_id)
        if session:
            session["status"] = "closed"
            session["updated_at"] = datetime.datetime.utcnow().isoformat()
        return session or {}

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        **kwargs,
    ) -> dict:
        if session_id not in self.messages:
            raise ValueError(f"Session {session_id} not found")

        msg_id = uuid.uuid4().hex[:12]
        now = datetime.datetime.utcnow().isoformat()
        msg = {
            "id": msg_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "created_at": now,
            **kwargs,
        }
        self.messages[session_id].append(msg)
        self.sessions[session_id]["message_count"] += 1
        self.sessions[session_id]["updated_at"] = now
        return msg

    def get_history(
        self, session_id: str, limit: int = 50
    ) -> list[dict]:
        msgs = self.messages.get(session_id, [])
        return msgs[-limit:]

    def search_history(
        self,
        user_id: Optional[str] = None,
        keyword: str = "",
        limit: int = 20,
    ) -> list[dict]:
        """Search messages across sessions."""
        results: list[dict] = []
        for sid, msgs in self.messages.items():
            session = self.sessions.get(sid, {})
            if user_id and session.get("user_id") != user_id:
                continue
            for m in msgs:
                if keyword.lower() in m.get("content", "").lower():
                    results.append(m)
                    if len(results) >= limit:
                        return results
        return results

    def get_context_summary(self, session_id: str) -> str:
        """Build a text summary of the conversation for escalation context."""
        msgs = self.messages.get(session_id, [])
        if not msgs:
            return "No conversation context."
        lines = []
        for m in msgs[-10:]:
            role_label = "用户" if m["role"] == "user" else "AI"
            lines.append(f"{role_label}: {m['content'][:200]}")
        return "\n".join(lines)
