"""
NEXUS Agent OS — Main Entry Point
The unified system that brings all 9 layers together.

Usage:
    from nexus.nexus_main import NEXUS
    
    agent = NEXUS()
    agent.start()
    result = agent.run("open Chrome and go to GitHub")
    agent.stop()
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict, Optional

from nexus.config import PATHS, OLLAMA_BASE_URL
from nexus.brain import Brain
from nexus.si_layer import SituationalIntelligence
from nexus.safety import SafetyLayer
from nexus.vision import VisionPipeline
from nexus.research import ResearchEngine
from nexus.agent_loop import AgentLoop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(PATHS.logs / "nexus.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("nexus")


class NEXUS:
    """
    NEXUS Agent Operating System — The unified agent.
    
    Combines:
    - Claude Code: Tool system, agent patterns, permissions
    - Awarenet: Critique engine, context injection, model orchestration
    - NEXUS Blueprint: 9-layer architecture, SI, vision, debug, memory
    
    Running on YOUR hardware:
    - HP Victus 16 (i5-11400H, 16GB RAM, GTX 1650 4GB)
    - 10 Ollama models (phi3, qwen3.5, deepseek-r1, llama3.2-vision, ...)
    """

    def __init__(
        self,
        ollama_url: str = OLLAMA_BASE_URL,
        *,
        enable_vision: bool = True,
        enable_research: bool = True,
        enable_critique: bool = True,
    ):
        logger.info("=" * 60)
        logger.info("  NEXUS Agent OS v0.1.0 — Starting up")
        logger.info("  Owner: Sahil | Machine: HP Victus 16")
        logger.info("=" * 60)

        # Ensure directories exist
        PATHS.ensure_dirs()

        # Layer 9: Safety (FIRST — before everything else)
        logger.info("Initializing Layer 9: Safety & Control...")
        self.safety = SafetyLayer()

        # Layer 5: Situational Intelligence
        logger.info("Initializing Layer 5: Situational Intelligence...")
        self.si = SituationalIntelligence()

        # Layer 1: Brain (with SI provider)
        logger.info("Initializing Layer 1: Brain (multi-model orchestrator)...")
        self.brain = Brain(
            ollama_url,
            si_provider=lambda: self.si.build_context(),
        )
        self.brain.critique_engine.enabled = enable_critique

        # Layer 2: Vision
        self.vision = None
        if enable_vision:
            logger.info("Initializing Layer 2: Vision Pipeline...")
            self.vision = VisionPipeline(brain=self.brain)

        # Layer 7: Research
        self.research = None
        if enable_research:
            logger.info("Initializing Layer 7: Internet Research Engine...")
            self.research = ResearchEngine(brain=self.brain)

        # Layer 4: Agent Loop (connects all layers)
        logger.info("Initializing Layer 4: Agent Loop...")
        self.loop = AgentLoop(
            brain=self.brain,
            safety=self.safety,
            si=self.si,
            vision=self.vision,
            research=self.research,
        )

        self._started = False

    def start(self) -> Dict[str, Any]:
        """Initialize all systems and start the agent."""
        logger.info("Starting all systems...")

        # Safety first
        safety_status = self.safety.initialize()
        logger.info(f"Safety: {safety_status}")

        # Check Ollama connection
        ollama_ok = self.brain.client.is_alive()
        if ollama_ok:
            models = self.brain.client.list_models()
            logger.info(f"Ollama: Connected — {len(models)} models available")
        else:
            logger.warning("Ollama: NOT connected — start Ollama first!")

        # System status
        system = self.si._poll_system()
        logger.info(f"System: RAM {system.get('ram_free_gb', '?')}GB free | "
                    f"CPU {system.get('cpu_pct', '?')}% | "
                    f"VRAM {system.get('vram_free_gb', '?')}GB free | "
                    f"Network: {system.get('network', '?')}")

        # Model recommendation
        recommended = self.si.get_model_recommendation()
        logger.info(f"Recommended brain: {recommended}")

        self._started = True
        logger.info("🚀 NEXUS is READY")

        return {
            "status": "ready",
            "ollama": ollama_ok,
            "safety": safety_status,
            "system": system,
            "recommended_brain": recommended,
        }

    def run(self, goal: str) -> Dict[str, Any]:
        """
        Execute a goal through the full agent loop.
        This is the main user-facing method.
        """
        if not self._started:
            self.start()

        logger.info(f"Goal received: {goal}")
        return self.loop.execute(goal)

    def quick(self, prompt: str) -> str:
        """Quick chat — just get a text response, no agent loop."""
        if not self._started:
            self.start()
        return self.brain.quick(prompt)

    def reason(self, prompt: str) -> str:
        """Deep reasoning — uses the think brain."""
        if not self._started:
            self.start()
        response = self.brain.reason(prompt)
        return response.content

    def see(self) -> Dict[str, Any]:
        """Take a screenshot and describe what's on screen."""
        if not self.vision:
            return {"ok": False, "error": "Vision not enabled"}
        return self.vision.perceive(use_ocr=True)

    def research_error(self, error: str) -> Dict[str, Any]:
        """Research an error and find solutions."""
        if not self.research:
            return {"ok": False, "error": "Research not enabled"}
        return self.research.research(error)

    def status(self) -> Dict[str, Any]:
        """Get full system status."""
        system = self.si._poll_system()
        return {
            "started": self._started,
            "system": system,
            "ollama_alive": self.brain.client.is_alive(),
            "recommended_brain": self.si.get_model_recommendation(),
            "active_task": self.loop._active_task.summary() if self.loop._active_task else None,
        }

    def stop(self) -> None:
        """Clean shutdown."""
        logger.info("Shutting down NEXUS...")
        self.safety.shutdown()
        if self.research:
            self.research.shutdown()
        self._started = False
        logger.info("NEXUS stopped.")


# ──────────────────────────────────────────────
# CLI Entry Point
# ──────────────────────────────────────────────

def main():
    """Simple CLI for testing NEXUS."""
    print(r"""
    ███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗
    ████╗  ██║██╔════╝╚██╗██╔╝██║   ██║██╔════╝
    ██╔██╗ ██║█████╗   ╚███╔╝ ██║   ██║███████╗
    ██║╚██╗██║██╔══╝   ██╔██╗ ██║   ██║╚════██║
    ██║ ╚████║███████╗██╔╝ ╚██╗╚██████╔╝███████║
    ╚═╝  ╚═══╝╚══════╝╚═╝   ╚═╝ ╚═════╝ ╚══════╝
    Agent OS v0.1.0 — Built by Sahil
    Claude Code + Awarenet + NEXUS Blueprint
    """)

    agent = NEXUS()
    startup = agent.start()

    if not startup.get("ollama"):
        print("⚠️  Ollama not running! Start it with: ollama serve")

    print("\nType your goal (or 'quit' to exit):")
    print("Commands: /status, /see, /quick <msg>, /research <error>\n")

    while True:
        try:
            user_input = input("NEXUS> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "/quit"):
            break

        if user_input == "/status":
            import json
            print(json.dumps(agent.status(), indent=2))
        elif user_input == "/see":
            result = agent.see()
            print(f"OCR Text: {result.get('ocr', {}).get('text', 'N/A')[:500]}")
        elif user_input.startswith("/quick "):
            msg = user_input[7:]
            print(agent.quick(msg))
        elif user_input.startswith("/research "):
            error = user_input[10:]
            import json
            result = agent.research_error(error)
            print(json.dumps(result, indent=2, default=str)[:3000])
        else:
            result = agent.run(user_input)
            print(f"\nStatus: {result.get('status')}")
            print(f"Iterations: {result.get('iterations')}")
            for r in result.get("reflections", []):
                print(f"  {r}")
            print()

    agent.stop()
    print("Goodbye! 👋")


if __name__ == "__main__":
    main()
