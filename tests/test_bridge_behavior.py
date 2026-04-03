import unittest
from pathlib import Path

from tools.openclaw_bridge import OpenClawBridge
from tools.task_detector import classify_request


ROOT = Path(__file__).resolve().parents[1]


class OpenClawBridgeBehaviorTests(unittest.TestCase):
    def test_accepts_project_root_argument(self) -> None:
        bridge = OpenClawBridge(project_root=ROOT)
        self.assertEqual(bridge.config_manager.app_config_path, ROOT / "config" / "openclaw.json")

    def test_pick_fallback_model_prefers_smallest_discovered_model(self) -> None:
        bridge = OpenClawBridge(project_root=ROOT)
        bridge._discovered_models = {
            "slow-model": {"size_bytes": 9_000},
            "fast-model": {"size_bytes": 1_000},
            "unknown-size": {},
        }
        self.assertEqual(bridge._pick_fallback_model(), "fast-model")

    def test_combined_models_flattens_provider_entries(self) -> None:
        bridge = OpenClawBridge(project_root=ROOT)
        bridge.config_manager._config["auto_discover_models"] = False
        bridge._discovered_models = {}
        bridge.config_manager._config["models"] = {
            "providers": {
                "local-proxy": {
                    "baseUrl": "http://127.0.0.1:11435",
                    "api": "ollama",
                    "apiKey": "test-key",
                    "models": [{"id": "awarenet:v1", "name": "Awarenet v1"}],
                }
            }
        }

        models = bridge._combined_models()
        entry = models["awarenet:v1"]
        self.assertEqual(entry["provider"], "local-proxy")
        self.assertEqual(entry["baseUrl"], "http://127.0.0.1:11435")
        self.assertEqual(entry["api"], "ollama")
        self.assertEqual(entry["apiKey"], "test-key")
        self.assertEqual(entry["model"], "awarenet:v1")

    def test_safe_config_redacts_nested_api_keys(self) -> None:
        bridge = OpenClawBridge(project_root=ROOT)
        bridge.config_manager._config["skills"] = {
            "entries": {
                "demo": {
                    "apiKey": "super-secret-value",
                    "enabled": True,
                }
            }
        }

        safe_config = bridge.get_safe_config()
        self.assertEqual(safe_config["skills"]["entries"]["demo"]["apiKey"], "<redacted>")
        self.assertTrue(safe_config["skills"]["entries"]["demo"]["enabled"])


class TaskDetectorBehaviorTests(unittest.TestCase):
    def test_simple_generation_request_no_longer_needs_clarification(self) -> None:
        classification = classify_request("Say hello in five words.")
        self.assertFalse(classification["needs_clarification"])
        self.assertGreaterEqual(classification["confidence"], 0.55)
