"""
Context injection system - automatically includes relevant state in prompts.
Makes models aware of user's environment without explicit passing.
"""

import json
from typing import Any, Dict, Optional
from pathlib import Path
from datetime import datetime

class ContextBuilder:
    """Build context summaries for prompt injection."""
    
    def __init__(self, bridge: Optional[Any] = None):
        self.bridge = bridge
    
    def get_session_context(self) -> str:
        """Get current session/workspace context."""
        parts = []
        
        # Time
        now = datetime.now()
        parts.append(f"Current time: {now.strftime('%A, %I:%M %p')}")
        
        # User info (from state if available)
        if self.bridge:
            try:
                from tools import assistant_state
                state = assistant_state.load()
                prefs = state.get("preferences", {})
                if prefs:
                    parts.append(f"User preferences: {json.dumps(prefs)[:200]}")
            except:
                pass
        
        return "\n".join(parts)
    
    def get_environment_context(self) -> str:
        """Get information about the system environment."""
        parts = []
        
        # Python environment
        import sys
        parts.append(f"Python: {sys.version.split()[0]}")
        
        # Installed packages (sample)
        try:
            import pkg_resources
            installed = {d.project_name for d in pkg_resources.working_set}
            key_packages = ["playwright", "pyautogui", "requests", "fastapi", "torch", "transformers"]
            present = [p for p in key_packages if p in installed]
            if present:
                parts.append(f"Available tools: {', '.join(present)}")
        except:
            pass
        
        # OS
        import platform
        parts.append(f"OS: {platform.system()} {platform.release()}")
        
        return "\n".join(parts)
    
    def get_recent_history(self, limit: int = 3) -> str:
        """Get recent tasks/actions from history."""
        parts = []
        
        if self.bridge:
            try:
                from tools import assistant_state
                state = assistant_state.load()
                
                # Recent tasks
                tasks = state.get("tasks", {}).get("history", [])
                if tasks:
                    parts.append("Recent tasks:")
                    for task in tasks[-limit:]:
                        goal = task.get("goal", "")[:50]
                        status = task.get("status", "")
                        parts.append(f"  - {goal} ({status})")
                
                # Recent actions
                actions = state.get("action_log", [])
                if actions:
                    parts.append("Recent actions:")
                    for action in actions[-limit:]:
                        action_type = action.get("action", "")[:30]
                        result = action.get("status", "")
                        parts.append(f"  - {action_type} → {result}")
            except:
                pass
        
        return "\n".join(parts) if parts else "No recent history"
    
    def get_task_context(self, user_text: str) -> str:
        """Context specific to understanding the current task."""
        parts = []
        
        # Detect intent
        if any(word in user_text.lower() for word in ["error", "fail", "broken", "not work"]):
            parts.append("Context: Troubleshooting an issue")
        elif any(word in user_text.lower() for word in ["open", "click", "navigate", "go to", "browse"]):
            parts.append("Context: User wants to interact with a GUI")
        elif any(word in user_text.lower() for word in ["write", "create", "edit", "modify"]):
            parts.append("Context: User wants to create or modify content")
        
        return "\n".join(parts) if parts else ""
    
    def build_full_context(self, user_text: str = "") -> str:
        """Build complete context for injection into prompts."""
        sections = []
        
        # Session info
        session = self.get_session_context()
        if session:
            sections.append(f"=== Session ===\n{session}")
        
        # Environment
        env = self.get_environment_context()
        if env:
            sections.append(f"=== Environment ===\n{env}")
        
        # History
        history = self.get_recent_history()
        if history:
            sections.append(f"=== Recent History ===\n{history}")
        
        # Task-specific
        if user_text:
            task_ctx = self.get_task_context(user_text)
            if task_ctx:
                sections.append(f"=== Task Context ===\n{task_ctx}")
        
        return "\n\n".join(sections)
    
    def get_context_marker(self) -> str:
        """Get a marker string to indicate context is present in prompt."""
        return "<!-- context injected -->"


# Global context builder instance
_context_builder: Optional[ContextBuilder] = None


def get_context_builder(bridge: Optional[Any] = None) -> ContextBuilder:
    """Get or create the global context builder."""
    global _context_builder
    if _context_builder is None:
        _context_builder = ContextBuilder(bridge)
    return _context_builder


def inject_context(prompt: str, context: str, prepend: bool = True) -> str:
    """Inject context into a prompt."""
    if not context:
        return prompt
    
    if prepend:
        return f"{context}\n\n---\n\nUser request:\n{prompt}"
    else:
        return f"{prompt}\n\n---\n\nContext:\n{context}"
