from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

FORBIDDEN_TOKENS = ("tool_call", "tool_calls", "function_call", "arguments")

DEFAULTS: Dict[str, Any] = {
    "awarenet_version": "v1",
    "critique_enabled": True,
    "critique_model": "critical_reasoner",
    "max_refine_ratio": 1.5,
    "min_response_chars": 5,
    "max_response_chars": 12000000,
    "critique_timeout_seconds": 20,
    "workflow_timeout_seconds": 60,
    "max_awarenet_depth": 2,
    "warmup_enabled": True,
    "executor_max_workers": 4,
}


class AwarenetEngine:
    """Awarenet orchestration engine with guarded critique."""

    def __init__(self, bridge: Any, config_path: str | Path | None = None) -> None:
        self.bridge = bridge
        self.config_path = Path(config_path) if config_path else Path(__file__).with_name("awarenet_config.json")
        file_config = self._load_config(self.config_path)
        self.base_config = self._merge_settings(DEFAULTS, file_config)
        workers = int(self.base_config.get("executor_max_workers", 4) or 4)
        self.executor = ThreadPoolExecutor(max_workers=workers)
        self._warmup_if_needed()

    def shutdown(self) -> None:
        try:
            self.executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            self.executor.shutdown(wait=False)

    def execute(
        self,
        user_request: str,
        *,
        runtime_mode: str | None = None,
        task_mode: str | None = None,
        model_id: str | None = None,
        context: Dict[str, Any] | None = None,
        runtime_overrides: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        request_id = uuid4().hex
        config = self._merge_settings(self.base_config, runtime_overrides or {})
        self._log_event("awarenet_start", {"request_id": request_id, "model_id": model_id})

        assistant_context = ""
        if hasattr(self.bridge, "build_assistant_context"):
            try:
                assistant_context = str(self.bridge.build_assistant_context() or "")
            except Exception:
                assistant_context = ""
        if assistant_context:
            user_request = self._inject_context(user_request, assistant_context)

        session_context = context if context is not None else {}
        max_depth = int(config.get("max_awarenet_depth", 2) or 2)
        current_depth = int(session_context.get("awarenet_depth", 0))
        if current_depth >= max_depth:
            raise RuntimeError("Awarenet recursion limit reached")
        session_context["awarenet_depth"] = current_depth + 1

        workflow_timeout = int(config.get("workflow_timeout_seconds", 60) or 60)
        workflow_start = time.monotonic()
        try:
            workflow_result = self._run_with_timeout(
                self.bridge.execute_workflow,
                workflow_timeout,
                user_request,
                runtime_mode=runtime_mode,
                task_mode=task_mode,
            )
        except TimeoutError as exc:
            self._log_event(
                "awarenet_error",
                {
                    "request_id": request_id,
                    "error": "workflow_timeout",
                    "detail": str(exc),
                },
            )
            workflow_result = self._fallback_response(user_request)
        except Exception as exc:  # noqa: BLE001
            self._log_event(
                "awarenet_error",
                {
                    "request_id": request_id,
                    "error": "workflow_exception",
                    "detail": str(exc),
                },
            )
            workflow_result = self._fallback_response(user_request)

        workflow_duration = int((time.monotonic() - workflow_start) * 1000)
        response = self._extract_response(workflow_result)
        model_used = self._extract_model_used(workflow_result)
        self._log_event(
            "awarenet_workflow_complete",
            {
                "request_id": request_id,
                "duration_ms": workflow_duration,
                "model": model_used,
            },
        )

        if self._needs_fallback_response(response, config):
            self._log_event(
                "awarenet_error",
                {"request_id": request_id, "error": "response_sanity_fallback"},
            )
            fallback_result = self._fallback_response(user_request)
            response = self._extract_response(fallback_result)
            model_used = self._extract_model_used(fallback_result) or model_used

        response = self._apply_max_response_guard(response, config, request_id)

        final_response = response
        if bool(config.get("critique_enabled", False)):
            critique_timeout = int(config.get("critique_timeout_seconds", 20) or 20)
            critique_model = str(config.get("critique_model", "critical_reasoner")).strip() or "critical_reasoner"
            self._log_event(
                "awarenet_critique_attempt",
                {"request_id": request_id, "model": critique_model},
            )
            critique_start = time.monotonic()
            critique_error_reason = None
            try:
                critique_result = self._run_with_timeout(
                    self._run_critique,
                    critique_timeout,
                    config,
                    user_request,
                    response,
                )
            except TimeoutError as exc:
                critique_error_reason = "critique_timeout"
                critique_result = None
            except Exception as exc:  # noqa: BLE001
                critique_error_reason = "critique_exception"
                critique_result = None

            critique_duration = int((time.monotonic() - critique_start) * 1000)
            if critique_result and critique_result.get("replace"):
                final_response = critique_result["response"]
                final_response = self._apply_max_response_guard(final_response, config, request_id)
                self._log_event(
                    "awarenet_critique_applied",
                    {
                        "request_id": request_id,
                        "duration_ms": critique_duration,
                    },
                )
            else:
                self._log_event(
                    "awarenet_critique_rejected",
                    {
                        "request_id": request_id,
                        "duration_ms": critique_duration,
                        "reason": critique_error_reason or ("no_change" if critique_result else "invalid"),
                    },
                )

        return {
            "success": True,
            "response": final_response,
            "request_id": request_id,
            "model": model_used,
        }

    def _inject_context(self, user_request: str, context: str) -> str:
        marker = "[OPENCLAW_CONTEXT]"
        if marker in user_request:
            return user_request
        return f"{marker}\n{context}\n{marker}\n\n{user_request}"

    def _warmup_if_needed(self) -> None:
        if not bool(self.base_config.get("warmup_enabled", False)):
            return
        try:
            self.bridge.run_model("assistant", "ping")
        except Exception:
            return

    def _run_with_timeout(self, fn, timeout_seconds: int, *args, **kwargs):
        future = self.executor.submit(fn, *args, **kwargs)
        try:
            return future.result(timeout=timeout_seconds)
        except TimeoutError:
            future.cancel()
            raise

    def _run_critique(
        self,
        config: Dict[str, Any],
        user_request: str,
        response: str,
    ) -> Dict[str, Any]:
        critique_model = str(config.get("critique_model", "critical_reasoner")).strip() or "critical_reasoner"
        system_prompt = (
            "You are the Awarenet critique agent. Return strict JSON only. "
            "If no changes are needed, return {\"replace\": false}. "
            "If changes are needed, return {\"replace\": true, \"response\": \"...\"}. "
            "Do not include any other keys or commentary."
        )
        prompt = (
            "User request:\n"
            f"{user_request}\n\n"
            "Original response:\n"
            f"{response}\n\n"
            "Return JSON only."
        )
        result = self.bridge.run_model(critique_model, prompt, system_prompt=system_prompt, temperature=0.1)
        raw_text = str(result.get("response") or "").strip()
        if not raw_text:
            return {}
        lowered = raw_text.lower()
        if any(token in lowered for token in FORBIDDEN_TOKENS):
            return {}

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            return {}
        if not isinstance(data, dict):
            return {}

        allowed_keys = {"replace", "response"}
        if set(data.keys()) - allowed_keys:
            return {}
        if "replace" not in data or not isinstance(data["replace"], bool):
            return {}

        if data["replace"] is False:
            if "response" in data:
                return {}
            return {"replace": False}

        if "response" not in data or not isinstance(data["response"], str):
            return {}

        new_response = data["response"].strip()
        if not new_response:
            return {}
        if new_response.strip() == response.strip():
            return {}

        max_ratio = float(config.get("max_refine_ratio", 1.5) or 1.5)
        if len(response.strip()) > 0 and len(new_response) > len(response) * max_ratio:
            return {}

        return {"replace": True, "response": new_response}

    def _fallback_response(self, user_request: str) -> Dict[str, Any]:
        return self.bridge.run_model("assistant", user_request, temperature=0.2)

    def _extract_response(self, result: Dict[str, Any] | None) -> str:
        if not result:
            return ""
        return str(result.get("response") or result.get("error") or "").strip()

    def _extract_model_used(self, result: Dict[str, Any] | None) -> str:
        if not result:
            return ""
        for key in ("model_used", "model"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for item in result.get("step_results", []) if isinstance(result, dict) else []:
            if isinstance(item, dict):
                value = item.get("model") or item.get("model_used")
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""

    def _needs_fallback_response(self, response: str, config: Dict[str, Any]) -> bool:
        min_chars = int(config.get("min_response_chars", 5) or 5)
        if len(response.strip()) < min_chars:
            return True
        if len(response.strip().split()) < 2:
            return True
        return False

    def _apply_max_response_guard(self, response: str, config: Dict[str, Any], request_id: str) -> str:
        max_chars = int(config.get("max_response_chars", 12000) or 12000)
        if max_chars > 0 and len(response) > max_chars:
            self._log_event(
                "awarenet_error",
                {
                    "request_id": request_id,
                    "error": "response_too_large",
                    "max_chars": max_chars,
                },
            )
            return response[:max_chars]
        return response

    def _merge_settings(self, base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base)
        for key, value in overrides.items():
            merged[key] = value
        return merged

    def _load_config(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _log_event(self, event: str, payload: Dict[str, Any]) -> None:
        try:
            self.bridge.log_event(event, payload)
        except Exception:
            return
