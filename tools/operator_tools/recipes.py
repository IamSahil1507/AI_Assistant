from __future__ import annotations

from typing import Any, Dict, List


def gmail_draft_actions(*, to: str, subject: str, body: str) -> List[Dict[str, Any]]:
    """
    Best-effort Gmail compose actions using role/name selectors where possible.

    Note: Gmail UI changes frequently; keep this minimal and rely on operator troubleshooting when it drifts.
    """
    return [
        {"type": "goto", "url": "https://mail.google.com/mail/u/0/#inbox?compose=new"},
        {"type": "wait_for", "selector": "div[role='dialog']", "state": "visible"},
        # To field is usually a textarea[name=to] inside the dialog.
        {"type": "click", "selector": "div[role='dialog'] textarea[name=to]"},
        {"type": "type", "text": to},
        {"type": "press", "key": "Enter"},
        {"type": "click", "selector": "div[role='dialog'] input[name=subjectbox]"},
        {"type": "type", "text": subject},
        {"type": "click", "selector": "div[role='dialog'] div[aria-label='Message Body']"},
        {"type": "type", "text": body, "delay_ms": 5},
        {"type": "screenshot", "full_page": True},
    ]

