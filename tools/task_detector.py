"""
Task intent detection - understand what the user is asking and route to right handler.
Distinguishes between queries, tasks, debugging, decisions, etc.
"""

import re
from typing import Tuple, Optional
from enum import Enum


class TaskIntent(Enum):
    """Type of task the user is requesting."""
    QUERY = "query"           # Question that needs answering
    TASK = "task"             # Action to execute
    ANALYSIS = "analysis"     # Analyze/understand something
    DECISION = "decision"     # Help me decide between options
    DEBUG = "debug"           # Fix a problem
    COMMAND = "command"       # Direct command (open X, create Y, etc.)
    CLARIFICATION = "ask"     # Ambiguous - need clarification


class TaskDetector:
    """Detect user intent and confidence."""
    
    # Pattern groups for intent detection
    QUERY_PATTERNS = [
        r"^(what|when|where|who|why|how|which|can|could|would|is|are|do|does)",
        r"\?$",
        r"(tell me|explain|describe|list|show me)",
    ]
    
    TASK_PATTERNS = [
        r"(open|close|create|delete|rename|move|copy|edit|write|read|upload|download)",
        r"(send|email|message|post|publish|save|backup|restore)",
        r"(start|stop|run|execute|launch|install|uninstall)",
        r"(go to|navigate to|visit|browse)",
        r"^(say|write|draft|summarize|generate|analyze|review|check|test|fix|build|create)",
        r"^(please|can you|could you|would you|i need you to)",
    ]
    
    DEBUG_PATTERNS = [
        r"(error|fail|broken|not work|crash|bug|wrong|incorrect|issue|problem)",
        r"(fix|repair|debug|troubleshoot|solve|patch|resolve)",
        r"(why|why is|why does|why won't|why can't)",
    ]
    
    DECISION_PATTERNS = [
        r"(which|what should|should i|better|best|prefer|choose|pick|option)",
        r"(pros and cons|better than|compare|difference between)",
        r"(recommend|advise|suggest)",
    ]
    
    RISKY_PATTERNS = [
        r"(delete|remove|uninstall|wipe|format|shutdown|reboot|restart|kill)",
        r"(modify system|change registry|admin|sudo|elevated)",
        r"(send email|make payment|transfer|purchase)",
    ]
    
    UNCLEAR_PATTERNS = [
        r"(i'm not sure|not clear|confusing|don't know what|unclear)",
        r"(help me|guide me|show me how)",
    ]
    
    @classmethod
    def detect(cls, user_text: str) -> Tuple[TaskIntent, float, Optional[str]]:
        """
        Detect user intent from text.
        
        Returns:
            (intent_type, confidence: 0-1, reason)
        """
        text = user_text.strip().lower()
        
        if not text:
            return TaskIntent.CLARIFICATION, 0.0, "Empty request"
        
        # Check for unclear intent
        if any(re.search(p, text) for p in cls.UNCLEAR_PATTERNS):
            return TaskIntent.CLARIFICATION, 0.7, "User is uncertain"
        
        # Check for risky operations
        risky_match = any(re.search(p, text, re.IGNORECASE) 
                         for p in cls.RISKY_PATTERNS)
        
        # Check for specific intents
        intent_scores = {
            TaskIntent.QUERY: sum(1 for p in cls.QUERY_PATTERNS if re.search(p, text)),
            TaskIntent.TASK: sum(1 for p in cls.TASK_PATTERNS if re.search(p, text)),
            TaskIntent.DEBUG: sum(1 for p in cls.DEBUG_PATTERNS if re.search(p, text)),
            TaskIntent.DECISION: sum(1 for p in cls.DECISION_PATTERNS if re.search(p, text)),
        }
        
        # Find highest scoring intent
        best_intent = max(intent_scores, key=intent_scores.get)
        score = intent_scores[best_intent]
        
        # Calculate confidence based on pattern matches
        if score >= 3:
            confidence = 0.95
        elif score >= 2:
            confidence = 0.8
        elif score >= 1:
            confidence = 0.6
        else:
            # No clear pattern match - still allow straightforward prompts through.
            return TaskIntent.QUERY, 0.55, "Generic request fallback"
        
        # Adjust for risky operations
        if risky_match and best_intent == TaskIntent.TASK:
            confidence *= 0.7  # Require approval for risky ops
        
        reason = f"Matched {score} {best_intent.value} patterns"
        if risky_match:
            reason += " (risky)"
        
        return best_intent, confidence, reason
    
    @classmethod
    def needs_clarification(cls, user_text: str) -> Tuple[bool, Optional[str]]:
        """Check if request needs clarification before proceeding."""
        intent, confidence, _reason = cls.detect(user_text)
        
        if confidence < 0.5:
            return True, "I'm not sure what you're asking. Can you clarify?"
        
        if intent == TaskIntent.CLARIFICATION:
            return True, "Your request is ambiguous. What specifically would you like?"
        
        # Check for missing crucial info
        if any(word in user_text.lower() for word in ["it", "that", "this"]):
            # Pronoun without context
            return True, "Which specific file/app are you referring to?"
        
        return False, None
    
    @classmethod
    def get_confidence_warning(cls, confidence: float) -> Optional[str]:
        """Get a warning message based on confidence level."""
        if confidence >= 0.9:
            return None
        elif confidence >= 0.7:
            return "Note: I'm moderately confident in my interpretation."
        elif confidence >= 0.5:
            return "Warning: I'm not very confident I understand correctly."
        else:
            return "Alert: Please clarify your request - it's ambiguous."


def classify_request(user_text: str) -> dict:
    """
    Full classification of a user request.
    
    Returns dict with:
        - intent: TaskIntent enum
        - confidence: float 0-1
        - needs_clarification: bool
        - clarification_prompt: str or None
        - should_ask_confirmation: bool (for risky requests)
    """
    intent, confidence, reason = TaskDetector.detect(user_text)
    needs_clarify, clarify_msg = TaskDetector.needs_clarification(user_text)
    
    result = {
        "intent": intent,
        "intent_name": intent.value,
        "confidence": confidence,
        "reason": reason,
        "needs_clarification": needs_clarify,
        "clarification_prompt": clarify_msg,
        "warning": TaskDetector.get_confidence_warning(confidence),
    }
    
    # Check if risky
    is_risky = any(re.search(p, user_text.lower()) 
                  for p in TaskDetector.RISKY_PATTERNS)
    result["is_risky"] = is_risky
    result["should_ask_confirmation"] = is_risky and intent == TaskIntent.TASK
    
    return result
