import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ChatEvent:
    ts: float
    kind: str  # user_message | assistant_message | system_note
    role: str  # user | assistant | system
    content: str
    meta: Dict[str, Any]


def _now() -> float:
    return time.time()


def _chats_dir(root: Path) -> Path:
    d = root / "data" / "chats"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _chat_path(root: Path, chat_id: str) -> Path:
    safe = "".join(ch for ch in chat_id if ch.isalnum() or ch in {"-", "_"}).strip()[:80]
    if not safe:
        safe = "chat"
    return _chats_dir(root) / f"{safe}.jsonl"


def append_event(root: Path, chat_id: str, event: ChatEvent) -> None:
    path = _chat_path(root, chat_id)
    payload = {
        "ts": event.ts,
        "kind": event.kind,
        "role": event.role,
        "content": event.content,
        "meta": event.meta or {},
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def list_events(root: Path, chat_id: str, *, limit: int = 200) -> List[Dict[str, Any]]:
    path = _chat_path(root, chat_id)
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    # Simple tail read: read all for now (bounded by limit on return).
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows[-max(1, int(limit)) :]


def new_chat_id() -> str:
    return f"chat-{int(_now())}"


def record_user_and_assistant(
    root: Path,
    chat_id: str,
    *,
    user_text: str,
    assistant_text: str,
    model: str,
    system_prompt: Optional[str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> None:
    if system_prompt:
        append_event(
            root,
            chat_id,
            ChatEvent(ts=_now(), kind="system_note", role="system", content=system_prompt, meta={"model": model}),
        )
    append_event(
        root,
        chat_id,
        ChatEvent(
            ts=_now(),
            kind="user_message",
            role="user",
            content=user_text,
            meta={"model": model, "attachments": attachments or []},
        ),
    )
    append_event(
        root,
        chat_id,
        ChatEvent(
            ts=_now(),
            kind="assistant_message",
            role="assistant",
            content=assistant_text,
            meta={"model": model},
        ),
    )

