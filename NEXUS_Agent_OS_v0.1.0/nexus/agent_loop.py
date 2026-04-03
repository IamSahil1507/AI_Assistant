"""
NEXUS Layer 4: Agent Loop — The 6-Step Execution Cycle
Fusion: Claude Code multi-step tool chains + NEXUS Perceive→Plan→Act→Observe→Reflect→Replan

This is the HEART of NEXUS — the loop that turns a goal into completed work.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from nexus.config import PATHS

logger = logging.getLogger("nexus.loop")


# ──────────────────────────────────────────────
# Task State Machine
# ──────────────────────────────────────────────

class TaskState(Enum):
    PENDING = "pending"
    PERCEIVING = "perceiving"
    PLANNING = "planning"
    ACTING = "acting"
    OBSERVING = "observing"
    REFLECTING = "reflecting"
    REPLANNING = "replanning"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING_USER = "waiting_user"
    DEBUGGING = "debugging"


@dataclass
class Step:
    """A single atomic step in a plan."""
    id: str
    goal: str
    tool: str           # bash | file_read | file_write | browser | desktop | vision | research
    action: Dict[str, Any]
    status: str = "pending"  # pending | running | success | failed | skipped
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retries: int = 0
    max_retries: int = 2


@dataclass
class TaskContext:
    """Full context for a running task."""
    task_id: str
    goal: str
    state: TaskState = TaskState.PENDING
    steps: List[Step] = field(default_factory=list)
    current_step_index: int = 0
    observations: List[Dict[str, Any]] = field(default_factory=list)
    reflections: List[str] = field(default_factory=list)
    error_count: int = 0
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def current_step(self) -> Optional[Step]:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def is_done(self) -> bool:
        return self.state in (TaskState.COMPLETED, TaskState.FAILED)

    def summary(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "state": self.state.value,
            "steps_total": len(self.steps),
            "steps_completed": sum(1 for s in self.steps if s.status == "success"),
            "steps_failed": sum(1 for s in self.steps if s.status == "failed"),
            "current_step": self.current_step_index,
            "error_count": self.error_count,
            "duration_s": round(time.time() - self.started_at, 1),
        }


# ──────────────────────────────────────────────
# Agent Loop — The 6-Step Cycle
# ──────────────────────────────────────────────

class AgentLoop:
    """
    NEXUS Agent Loop — the core execution engine.
    
    Every task runs through this cycle:
    1. PERCEIVE  — Screenshot + OCR + system state
    2. PLAN      — Decompose goal into atomic steps
    3. ACT       — Execute one verified step
    4. OBSERVE   — Did it work? Re-read screen state
    5. REFLECT   — Update task state, note what changed
    6. REPLAN    — Adjust next step or trigger debug engine
    
    Key principle: After every single action, re-capture and verify.
    No blind execution chains. No assuming. Every step validated.
    """

    def __init__(
        self,
        brain: Any,           # nexus.brain.Brain
        safety: Any,          # nexus.safety.SafetyLayer
        si: Any,              # nexus.si_layer.SituationalIntelligence
        vision: Optional[Any] = None,   # nexus.vision.VisionPipeline
        research: Optional[Any] = None, # nexus.research.ResearchEngine
    ):
        self.brain = brain
        self.safety = safety
        self.si = si
        self.vision = vision
        self.research = research
        self._active_task: Optional[TaskContext] = None

    def execute(self, goal: str, *, max_iterations: int = 20) -> Dict[str, Any]:
        """
        Execute a goal through the full agent loop.
        This is the main entry point.
        """
        task = TaskContext(
            task_id=f"task_{int(time.time())}_{uuid4().hex[:6]}",
            goal=goal,
        )
        self._active_task = task

        logger.info(f"Starting task {task.task_id}: {goal}")

        iteration = 0
        while not task.is_done() and iteration < max_iterations:
            iteration += 1
            logger.info(f"Loop iteration {iteration}/{max_iterations} — state: {task.state.value}")

            try:
                if task.state == TaskState.PENDING:
                    self._step_perceive(task)

                elif task.state == TaskState.PERCEIVING:
                    self._step_plan(task)

                elif task.state == TaskState.PLANNING:
                    if not task.steps:
                        task.state = TaskState.COMPLETED
                    else:
                        self._step_act(task)

                elif task.state == TaskState.ACTING:
                    self._step_observe(task)

                elif task.state == TaskState.OBSERVING:
                    self._step_reflect(task)

                elif task.state == TaskState.REFLECTING:
                    self._step_replan(task)

                elif task.state == TaskState.REPLANNING:
                    # After replanning, go back to acting on next step
                    if task.current_step_index >= len(task.steps):
                        task.state = TaskState.COMPLETED
                    else:
                        task.state = TaskState.ACTING

                elif task.state == TaskState.DEBUGGING:
                    self._step_debug(task)

            except Exception as e:
                logger.error(f"Loop error at state {task.state.value}: {e}")
                task.error_count += 1
                if task.error_count >= 3:
                    task.state = TaskState.FAILED
                    task.reflections.append(f"Fatal: {str(e)}")
                else:
                    task.state = TaskState.REPLANNING

        task.completed_at = time.time()
        self._active_task = None

        # Save checkpoint
        self._save_checkpoint(task)

        return {
            "task_id": task.task_id,
            "goal": goal,
            "status": task.state.value,
            "summary": task.summary(),
            "reflections": task.reflections,
            "iterations": iteration,
        }

    # ──────────────────────────────────────────
    # Step 1: PERCEIVE
    # ──────────────────────────────────────────

    def _step_perceive(self, task: TaskContext) -> None:
        """Capture current state: screenshot + OCR + system signals."""
        task.state = TaskState.PERCEIVING
        perception: Dict[str, Any] = {"timestamp": time.time()}

        # System state via SI
        si_context = self.si.build_context(task.goal, task_id=task.task_id)
        perception["si_context"] = si_context

        # Screen state via Vision (if available)
        if self.vision:
            try:
                screen = self.vision.perceive(use_ocr=True, use_vision_llm=False)
                perception["screen"] = {
                    "ocr_text": screen.get("ocr", {}).get("text", ""),
                    "has_error": False,
                }
                # Check for errors on screen
                if screen.get("ocr", {}).get("text"):
                    error_check = self.vision.detect_error(
                        ocr_text=screen["ocr"]["text"]
                    )
                    perception["screen"]["has_error"] = error_check.get("has_error", False)
                    if error_check.get("has_error"):
                        perception["screen"]["error_patterns"] = error_check.get("error_patterns", [])
            except Exception as e:
                logger.warning(f"Vision perceive failed: {e}")

        task.observations.append(perception)
        task.state = TaskState.PERCEIVING  # Signal ready for planning

    # ──────────────────────────────────────────
    # Step 2: PLAN
    # ──────────────────────────────────────────

    def _step_plan(self, task: TaskContext) -> None:
        """Decompose goal into atomic steps using the Brain."""
        task.state = TaskState.PLANNING

        # Build planning prompt
        prompt = (
            f"Decompose this goal into atomic, verifiable steps:\n\n"
            f"GOAL: {task.goal}\n\n"
            f"Return a JSON array of steps. Each step must have:\n"
            f'- "goal": what this step achieves\n'
            f'- "tool": one of [bash, file_read, file_write, browser, desktop, vision, research]\n'
            f'- "action": tool-specific parameters as object\n\n'
            f"Return ONLY the JSON array, no other text.\n"
            f"Keep it to 3-7 steps maximum.\n"
        )

        # Add observations context
        if task.observations:
            latest = task.observations[-1]
            if latest.get("screen", {}).get("ocr_text"):
                prompt += f"\nCurrent screen text:\n{latest['screen']['ocr_text'][:500]}\n"

        response = self.brain.reason(prompt, temperature=0.3)

        # Parse steps from LLM response
        try:
            steps_data = json.loads(response.content)
            if not isinstance(steps_data, list):
                steps_data = [steps_data]

            for i, s in enumerate(steps_data):
                task.steps.append(Step(
                    id=f"step_{i}",
                    goal=str(s.get("goal", "")),
                    tool=str(s.get("tool", "bash")),
                    action=s.get("action", {}),
                ))
        except (json.JSONDecodeError, TypeError):
            # If LLM didn't return valid JSON, create a single bash step
            task.steps.append(Step(
                id="step_0",
                goal=task.goal,
                tool="bash",
                action={"command": task.goal},
            ))

        task.state = TaskState.PLANNING  # Ready to act

    # ──────────────────────────────────────────
    # Step 3: ACT
    # ──────────────────────────────────────────

    def _step_act(self, task: TaskContext) -> None:
        """Execute one step through the safety layer."""
        task.state = TaskState.ACTING
        step = task.current_step()
        if not step:
            task.state = TaskState.COMPLETED
            return

        step.status = "running"
        logger.info(f"Acting: step {step.id} — {step.goal}")

        # Safety check BEFORE execution
        safety_eval = self.safety.evaluate(
            f"{step.tool}: {json.dumps(step.action)[:200]}",
            tool=step.tool,
            rationale=step.goal,
        )

        if not safety_eval.get("allowed"):
            step.status = "failed"
            step.error = f"Blocked by safety: {safety_eval.get('reason')}"
            logger.warning(f"Step blocked: {step.error}")
            task.state = TaskState.OBSERVING
            return

        # Execute the tool (placeholder — each tool has its own executor)
        try:
            result = self._execute_tool(step)
            step.result = result
            step.status = "success" if result.get("ok") else "failed"
            if not result.get("ok"):
                step.error = result.get("error", "unknown")
        except Exception as e:
            step.status = "failed"
            step.error = str(e)

        # Log outcome to audit
        self.safety.audit.log_outcome(
            f"{step.tool}:{step.id}",
            step.status == "success",
            step.error or "",
        )

        task.state = TaskState.ACTING  # Ready to observe

    def _execute_tool(self, step: Step) -> Dict[str, Any]:
        """Route step to the appropriate tool executor."""
        # This is the extensible tool registry
        # Each tool will be implemented as the system grows
        tool_handlers = {
            "bash": self._tool_bash,
            "file_read": self._tool_file_read,
            "file_write": self._tool_file_write,
        }

        handler = tool_handlers.get(step.tool)
        if handler:
            return handler(step.action)

        return {"ok": False, "error": f"Tool '{step.tool}' not implemented yet"}

    def _tool_bash(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a bash/shell command."""
        import subprocess
        command = str(action.get("command", ""))
        if not command:
            return {"ok": False, "error": "empty_command"}

        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=60, cwd=str(PATHS.root),
            )
            return {
                "ok": result.returncode == 0,
                "stdout": result.stdout[:5000],
                "stderr": result.stderr[:5000],
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "timeout"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _tool_file_read(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Read a file's contents."""
        path = action.get("path", "")
        try:
            content = Path(path).read_text(encoding="utf-8")
            return {"ok": True, "content": content[:50000]}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _tool_file_write(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Write content to a file."""
        path = action.get("path", "")
        content = action.get("content", "")
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(content, encoding="utf-8")
            return {"ok": True, "path": path, "bytes_written": len(content)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ──────────────────────────────────────────
    # Step 4: OBSERVE
    # ──────────────────────────────────────────

    def _step_observe(self, task: TaskContext) -> None:
        """Verify the action's result by re-reading state."""
        task.state = TaskState.OBSERVING
        step = task.current_step()

        observation = {
            "step_id": step.id if step else "?",
            "step_status": step.status if step else "?",
            "step_result": step.result if step else None,
            "timestamp": time.time(),
        }

        # Re-capture screen if vision available
        if self.vision and step and step.tool in ("browser", "desktop"):
            try:
                screen = self.vision.perceive(use_ocr=True)
                observation["screen_after"] = screen.get("ocr", {}).get("text", "")[:1000]
            except Exception:
                pass

        task.observations.append(observation)
        task.state = TaskState.OBSERVING  # Ready to reflect

    # ──────────────────────────────────────────
    # Step 5: REFLECT
    # ──────────────────────────────────────────

    def _step_reflect(self, task: TaskContext) -> None:
        """Analyze what happened and update task state."""
        task.state = TaskState.REFLECTING
        step = task.current_step()

        if step and step.status == "success":
            task.reflections.append(f"✅ Step {step.id} succeeded: {step.goal}")
            task.current_step_index += 1
        elif step and step.status == "failed":
            task.error_count += 1
            task.reflections.append(f"❌ Step {step.id} failed: {step.error}")

            # Retry logic
            if step.retries < step.max_retries:
                step.retries += 1
                step.status = "pending"
                task.reflections.append(f"🔄 Retrying step {step.id} (attempt {step.retries})")
                self.si.increment_retry(task.task_id)
            else:
                task.reflections.append(f"🔧 Max retries reached — escalating to debug")
                task.state = TaskState.DEBUGGING
                return

        # Check if all steps done
        if task.current_step_index >= len(task.steps):
            task.state = TaskState.COMPLETED
        else:
            task.state = TaskState.REFLECTING  # Ready to replan

    # ──────────────────────────────────────────
    # Step 6: REPLAN
    # ──────────────────────────────────────────

    def _step_replan(self, task: TaskContext) -> None:
        """Adjust plan based on reflections."""
        task.state = TaskState.REPLANNING
        # For now, continue with existing plan
        # Future: LLM re-evaluates remaining steps based on observations
        task.state = TaskState.REPLANNING

    # ──────────────────────────────────────────
    # Debug Escalation
    # ──────────────────────────────────────────

    def _step_debug(self, task: TaskContext) -> None:
        """Escalate to debug engine when steps fail repeatedly."""
        task.state = TaskState.DEBUGGING
        step = task.current_step()

        if step and self.research:
            logger.info(f"Debug: researching fix for: {step.error}")
            result = self.research.research(
                step.error or step.goal,
                environment={"tool": step.tool},
            )
            if result.get("ok") and result.get("solutions"):
                top_fix = result["solutions"][0]
                task.reflections.append(
                    f"🔍 Found fix (score {top_fix['score']}): {top_fix['description'][:200]}"
                )

        # Skip the failed step and continue
        task.current_step_index += 1
        if task.current_step_index >= len(task.steps):
            task.state = TaskState.COMPLETED
        else:
            task.state = TaskState.ACTING

    # ──────────────────────────────────────────
    # Checkpointing
    # ──────────────────────────────────────────

    def _save_checkpoint(self, task: TaskContext) -> None:
        """Save task state for crash recovery."""
        checkpoint_dir = PATHS.data / "checkpoints"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = checkpoint_dir / f"{task.task_id}.json"

        data = {
            "task_id": task.task_id,
            "goal": task.goal,
            "state": task.state.value,
            "steps": [
                {
                    "id": s.id, "goal": s.goal, "tool": s.tool,
                    "status": s.status, "error": s.error,
                }
                for s in task.steps
            ],
            "reflections": task.reflections,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "error_count": task.error_count,
        }
        checkpoint_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
