"""
Integrated request processing pipeline - combines prompt templates, context injection, 
task detection, and response evaluation into a cohesive flow.
"""

from typing import Dict, Any, Optional, Tuple
from tools.prompt_templates import get_system_prompt, get_thinking_chain
from tools.context_injector import ContextBuilder, inject_context
from tools.task_detector import TaskDetector, classify_request
from tools.response_evaluator import ResponseEvaluator


class RequestProcessor:
    """Process user requests with full context and intent awareness."""
    
    def __init__(self, bridge: Optional[Any] = None):
        self.bridge = bridge
        self.context_builder = ContextBuilder(bridge)
    
    def process_request(self, user_text: str, model_id: str = "assistant") -> Dict[str, Any]:
        """
        Full request processing pipeline.
        
        Returns dict with:
            - intent: detected intent
            - confidence: confidence in detection
            - should_ask: whether user clarification is needed
            - system_prompt: prepared system prompt
            - injected_prompt: prompt with context
            - thinking_steps: chain of reasoning steps
        """
        # 1. Classify the request
        classification = classify_request(user_text)
        
        # 2. Check if clarification needed
        needs_clarify = classification["needs_clarification"]
        if needs_clarify and classification["clarification_prompt"]:
            return {
                "status": "needs_clarification",
                "question": classification["clarification_prompt"],
                "classification": classification,
            }
        
        # 3. Select appropriate system prompt
        prompt_type = self._map_intent_to_prompt(classification["intent_name"])
        system_prompt = self._get_contextualized_prompt(prompt_type)
        
        # 4. Build and inject context
        context = self.context_builder.get_session_context() + "\n"
        context += self.context_builder.get_environment_context() + "\n"
        context += self.context_builder.get_task_context(user_text)
        
        injected_prompt = inject_context(user_text, context, prepend=True)
        
        # 5. Get reasoning chain for this task type
        thinking_steps = get_thinking_chain(classification["intent_name"])
        
        # 6. Check if requires confirmation
        should_confirm = classification.get("should_ask_confirmation", False)
        
        return {
            "status": "ready",
            "classification": classification,
            "system_prompt": system_prompt,
            "injected_prompt": injected_prompt,
            "thinking_steps": thinking_steps,
            "should_confirm": should_confirm,
            "warnings": classification.get("warning"),
        }
    
    def evaluate_response(self, response: str, user_request: str = "") -> Dict[str, Any]:
        """Evaluate response quality and detect issues."""
        return ResponseEvaluator.evaluate(response, user_request)
    
    def refine_response(self, original_response: str, evaluation: Dict[str, Any]) -> Optional[str]:
        """Generate a prompt for refining a weak response."""
        if evaluation["quality"].value in ["excellent", "good"]:
            return None  # No refinement needed
        
        return ResponseEvaluator.get_improvement_prompt(evaluation)
    
    def _map_intent_to_prompt(self, intent_name: str) -> str:
        """Map detected intent to system prompt type."""
        mapping = {
            "query": "assistant",
            "task": "executor",
            "analysis": "reasoner",
            "decision": "reasoner",
            "debug": "reasoner",
            "command": "executor",
            "ask": "assistant",
        }
        return mapping.get(intent_name, "assistant")
    
    def _get_contextualized_prompt(self, prompt_type: str) -> str:
        """Get system prompt with context injection."""
        base_prompt = get_system_prompt(prompt_type)
        
        if prompt_type == "executor":
            # Add safety warnings for executor
            base_prompt += "\n\n**Safety First:**\nStop immediately if you detect an error or warning. Report the actual error message. Do not proceed with risky operations without explicit confirmation."
        
        return base_prompt


# Global processor instance
_processor: Optional[RequestProcessor] = None


def get_request_processor(bridge: Optional[Any] = None) -> RequestProcessor:
    """Get or create global request processor."""
    global _processor
    if _processor is None:
        _processor = RequestProcessor(bridge)
    return _processor


# Convenience functions for API integration

def classify_user_request(text: str) -> Dict[str, Any]:
    """Quickly classify a user request."""
    return classify_request(text)


def evaluate_model_response(response: str, user_request: str = "") -> Dict[str, Any]:
    """Evaluate a model's response."""
    return ResponseEvaluator.evaluate(response, user_request)


def prepare_prompt(user_text: str, model_id: str = "assistant", bridge: Optional[Any] = None) -> Dict[str, Any]:
    """Prepare a prompt with full processing pipeline."""
    processor = get_request_processor(bridge)
    return processor.process_request(user_text, model_id)
