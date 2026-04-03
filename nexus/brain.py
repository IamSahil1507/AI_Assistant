"""
NEXUS Layer 1: Brain — Multi-Model Orchestrator
Fusion: Claude Code tool-calling + Awarenet critique + NEXUS three-brain strategy

The Brain is the central reasoning engine. It:
- Selects the right model for each task (fast/think/see/code)
- Translates tool calls between formats
- Runs Awarenet critique loop for quality
- Injects Situational Intelligence context into every prompt
- Manages model loading/unloading to respect VRAM limits
"""

from __future__ import annotations

import json
import time
import logging
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field

import requests

from nexus.config import (
    MODELS, BRAIN_FALLBACK_CHAIN, OLLAMA_BASE_URL,
    FAST_BRAIN, THINK_BRAIN, DEEP_BRAIN, VISION_BRAIN, ModelSpec,
)

logger = logging.getLogger("nexus.brain")


# ──────────────────────────────────────────────
# Data Structures
# ──────────────────────────────────────────────

@dataclass
class Message:
    role: str           # system | user | assistant | tool
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    images: Optional[List[str]] = None  # base64 images for vision


@dataclass
class ToolCall:
    """A tool invocation requested by the LLM."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class BrainResponse:
    """Response from the Brain layer."""
    content: str
    model_used: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    thinking: Optional[str] = None  # deepseek-r1 thinking tokens
    duration_ms: int = 0
    tokens_used: int = 0
    was_critiqued: bool = False


# ──────────────────────────────────────────────
# Ollama Client
# ──────────────────────────────────────────────

class OllamaClient:
    """Direct Ollama API client for local models."""

    def __init__(self, base_url: str = OLLAMA_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Content-Type"] = "application/json"

    def is_alive(self) -> bool:
        try:
            r = self.session.get(f"{self.base_url}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> List[str]:
        try:
            r = self.session.get(f"{self.base_url}/api/tags", timeout=5)
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def loaded_models(self) -> List[Dict[str, Any]]:
        """Check which models are currently loaded in memory."""
        try:
            r = self.session.get(f"{self.base_url}/api/ps", timeout=5)
            return r.json().get("models", [])
        except Exception:
            return []

    def unload_model(self, model: str) -> bool:
        """Unload a model from memory to free VRAM."""
        try:
            r = self.session.post(
                f"{self.base_url}/api/generate",
                json={"model": model, "keep_alive": 0},
                timeout=10,
            )
            return r.status_code == 200
        except Exception:
            return False

    def chat(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """Send a chat completion request to Ollama."""
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if tools:
            payload["tools"] = tools

        start = time.monotonic()
        try:
            r = self.session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=120,
            )
            r.raise_for_status()
            data = r.json()
        except requests.Timeout:
            return {"error": "timeout", "duration_ms": int((time.monotonic() - start) * 1000)}
        except Exception as e:
            return {"error": str(e), "duration_ms": int((time.monotonic() - start) * 1000)}

        duration_ms = int((time.monotonic() - start) * 1000)
        data["duration_ms"] = duration_ms
        return data


# ──────────────────────────────────────────────
# Model Manager (VRAM-Aware)
# ──────────────────────────────────────────────

class ModelManager:
    """
    Manages model loading/unloading to respect the 4GB VRAM limit.
    Ensures only one heavy model is loaded at a time.
    """

    def __init__(self, client: OllamaClient):
        self.client = client
        self._current_model: Optional[str] = None

    def prepare_model(self, model_key: str) -> str:
        """
        Ensure the requested model is ready. Unload others if needed.
        Returns the Ollama model name string.
        """
        spec = MODELS.get(model_key)
        if not spec:
            raise ValueError(f"Unknown model: {model_key}")

        # If switching to a different heavy model, unload current first
        if self._current_model and self._current_model != model_key:
            current_spec = MODELS.get(self._current_model)
            if current_spec and not current_spec.fits_gpu:
                logger.info(f"Unloading {self._current_model} to make room for {model_key}")
                self.client.unload_model(current_spec.name)

        self._current_model = model_key
        return spec.name

    def select_model(
        self,
        task_type: str = "fast",
        *,
        vram_free_gb: Optional[float] = None,
    ) -> str:
        """
        Select the best model for a task type, respecting VRAM constraints.
        
        task_type: fast | think | see | code | debug
        """
        # Map task types to brain roles
        type_map = {
            "fast": "fast",
            "action": "fast",
            "think": "think",
            "plan": "think",
            "debug": "think",
            "rank": "think",
            "see": "see",
            "vision": "see",
            "ocr": "see",
            "code": "code",
        }
        role = type_map.get(task_type, "fast")

        # If VRAM is critically low, force fast model
        if vram_free_gb is not None and vram_free_gb < 1.5:
            logger.warning(f"VRAM critical ({vram_free_gb:.1f}GB free), forcing fast model")
            role = "fast"

        # Get fallback chain
        chain = BRAIN_FALLBACK_CHAIN.get(role, BRAIN_FALLBACK_CHAIN["fast"])

        for model_key in chain:
            spec = MODELS.get(model_key)
            if spec:
                return model_key

        return FAST_BRAIN  # ultimate fallback


# ──────────────────────────────────────────────
# Critique Engine (from Awarenet)
# ──────────────────────────────────────────────

class CritiqueEngine:
    """
    Awarenet-inspired critique loop.
    After the primary model responds, a critic model reviews and optionally refines.
    """

    def __init__(self, client: OllamaClient, model_manager: ModelManager):
        self.client = client
        self.model_manager = model_manager
        self.enabled = True
        self.max_refine_ratio = 1.5

    def critique(
        self,
        user_request: str,
        response: str,
        *,
        critic_model: str = "phi3",
    ) -> Optional[str]:
        """
        Review a response and optionally return a refined version.
        Returns None if the original response is fine.
        """
        if not self.enabled or not response.strip():
            return None

        model_name = self.model_manager.prepare_model(critic_model)
        
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a response quality critic. Review the response for accuracy, "
                    "completeness, and helpfulness. Return JSON only.\n"
                    'If response is good: {"replace": false}\n'
                    'If response needs improvement: {"replace": true, "response": "improved text"}\n'
                    "Return ONLY the JSON, nothing else."
                ),
            },
            {
                "role": "user",
                "content": f"User request:\n{user_request}\n\nResponse to review:\n{response}\n\nReturn JSON only.",
            },
        ]

        result = self.client.chat(model_name, messages, temperature=0.1, max_tokens=2048)
        raw = (result.get("message", {}).get("content") or "").strip()

        try:
            data = json.loads(raw)
            if isinstance(data, dict) and data.get("replace") is True:
                new_response = data.get("response", "").strip()
                if new_response and len(new_response) <= len(response) * self.max_refine_ratio:
                    return new_response
        except (json.JSONDecodeError, TypeError):
            pass

        return None


# ──────────────────────────────────────────────
# Brain — The Central Intelligence
# ──────────────────────────────────────────────

class Brain:
    """
    NEXUS Brain Layer — the unified reasoning engine.
    
    Combines:
    - Claude Code: tool-calling patterns, multi-step chains
    - Awarenet: critique loop, context injection
    - NEXUS: three-brain strategy, VRAM-aware switching
    """

    def __init__(
        self,
        ollama_url: str = OLLAMA_BASE_URL,
        *,
        si_provider: Optional[Callable[[], Dict[str, Any]]] = None,
    ):
        self.client = OllamaClient(ollama_url)
        self.model_manager = ModelManager(self.client)
        self.critique_engine = CritiqueEngine(self.client, self.model_manager)
        self._si_provider = si_provider  # Situational Intelligence context
        self._conversation_history: List[Message] = []

    def think(
        self,
        prompt: str,
        *,
        task_type: str = "fast",
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        images: Optional[List[str]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        critique: bool = False,
    ) -> BrainResponse:
        """
        Central reasoning method. Every NEXUS layer calls this.
        
        task_type: fast | think | see | code | debug | plan | rank
        """
        # Step 1: Get Situational Intelligence context
        si_context = self._get_si_context()
        vram_free = si_context.get("system", {}).get("vram_free_gb") if si_context else None

        # Step 2: Select model based on task + VRAM
        if images:
            model_key = "llama3.2-vision"
        else:
            model_key = self.model_manager.select_model(task_type, vram_free_gb=vram_free)

        model_name = self.model_manager.prepare_model(model_key)

        # Step 3: Build messages with SI context injection
        messages = self._build_messages(prompt, system_prompt, si_context, images)

        # Step 4: Call LLM
        result = self.client.chat(
            model_name,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        )

        if "error" in result:
            # Try fallback model
            logger.warning(f"Model {model_name} failed: {result['error']}, trying fallback")
            model_key = FAST_BRAIN
            model_name = self.model_manager.prepare_model(model_key)
            result = self.client.chat(model_name, messages, temperature=temperature, max_tokens=max_tokens)

        # Step 5: Extract response
        msg = result.get("message", {})
        content = msg.get("content", "")
        tool_calls = self._extract_tool_calls(msg)
        duration_ms = result.get("duration_ms", 0)

        # Step 6: Extract thinking tokens (deepseek-r1)
        thinking = None
        if "<think>" in content:
            parts = content.split("</think>")
            if len(parts) > 1:
                thinking = parts[0].replace("<think>", "").strip()
                content = parts[1].strip()

        # Step 7: Critique loop (if enabled)
        was_critiqued = False
        if critique and not tool_calls and content.strip():
            refined = self.critique_engine.critique(prompt, content)
            if refined:
                content = refined
                was_critiqued = True

        # Step 8: Build response
        tokens = result.get("eval_count", 0) + result.get("prompt_eval_count", 0)

        return BrainResponse(
            content=content,
            model_used=model_name,
            tool_calls=tool_calls,
            thinking=thinking,
            duration_ms=duration_ms,
            tokens_used=tokens,
            was_critiqued=was_critiqued,
        )

    def _get_si_context(self) -> Optional[Dict[str, Any]]:
        """Get current Situational Intelligence context."""
        if self._si_provider:
            try:
                return self._si_provider()
            except Exception:
                return None
        return None

    def _build_messages(
        self,
        prompt: str,
        system_prompt: Optional[str],
        si_context: Optional[Dict[str, Any]],
        images: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        """Build the message array with SI context injection."""
        messages: List[Dict[str, Any]] = []

        # System prompt with SI rules injected
        sys_parts = []
        if system_prompt:
            sys_parts.append(system_prompt)
        else:
            sys_parts.append(
                "You are NEXUS, an autonomous AI assistant created by Sahil. "
                "You can see the screen, control the machine, debug errors, "
                "search the internet, and learn from every session. "
                "Be concise, accurate, and genuinely helpful."
            )

        # Inject SI context and rules
        if si_context:
            rules = si_context.get("rules", [])
            if rules:
                sys_parts.append("\n[SITUATIONAL AWARENESS — follow these rules]")
                for rule in rules:
                    sys_parts.append(f"- {rule}")

            system_info = si_context.get("system", {})
            if system_info:
                sys_parts.append(f"\n[SYSTEM STATE] RAM free: {system_info.get('ram_free_gb', '?')}GB | "
                               f"CPU: {system_info.get('cpu_pct', '?')}% | "
                               f"VRAM free: {system_info.get('vram_free_gb', '?')}GB | "
                               f"Active app: {system_info.get('active_app', '?')}")

        messages.append({"role": "system", "content": "\n".join(sys_parts)})

        # User message (with images if vision)
        user_msg: Dict[str, Any] = {"role": "user", "content": prompt}
        if images:
            user_msg["images"] = images
        messages.append(user_msg)

        return messages

    def _extract_tool_calls(self, message: Dict[str, Any]) -> List[ToolCall]:
        """Extract tool calls from LLM response (Ollama format)."""
        tool_calls = []
        raw_calls = message.get("tool_calls", [])
        for i, call in enumerate(raw_calls):
            func = call.get("function", {})
            tool_calls.append(ToolCall(
                id=f"call_{i}_{int(time.time())}",
                name=func.get("name", ""),
                arguments=func.get("arguments", {}),
            ))
        return tool_calls

    def quick(self, prompt: str, **kwargs) -> str:
        """Quick response using fast brain. Returns just the text."""
        resp = self.think(prompt, task_type="fast", **kwargs)
        return resp.content

    def reason(self, prompt: str, **kwargs) -> BrainResponse:
        """Deep reasoning using think brain."""
        return self.think(prompt, task_type="think", **kwargs)

    def see(self, prompt: str, images: List[str], **kwargs) -> BrainResponse:
        """Vision understanding using vision brain."""
        return self.think(prompt, task_type="see", images=images, **kwargs)

    def debug(self, prompt: str, **kwargs) -> BrainResponse:
        """Debug-focused reasoning."""
        return self.think(prompt, task_type="debug", critique=True, **kwargs)
