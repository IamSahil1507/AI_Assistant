import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from api import server
from tools.operator_controller import OperatorController


class ApiRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=server.app),
            base_url="http://testserver",
            follow_redirects=True,
            timeout=60.0,
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_operator_step_shell_smoke(self) -> None:
        start = await self.client.post("/assistant/operator/start", json={"goal": "test operator"})
        self.assertEqual(start.status_code, 200)
        task_id = start.json()["task_id"]

        response = await self.client.post(
            "/assistant/operator/step",
            json={
                "task_id": task_id,
                "tool": "shell",
                "step_id": "list_root",
                "goal": "list workspace",
                "risk": "normal",
                "success_criteria": "directory listed",
                "action": {"type": "fs_list", "path": "D:/Projects/AI_Assistant", "max_entries": 3},
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["observation"]["ok"])
        self.assertTrue(body["executed"])

    async def test_operator_browser_route_constructs_step(self) -> None:
        with patch.object(OperatorController, "execute_plan_step_async", autospec=True) as execute:
            execute.return_value = {"executed": True}
            response = await self.client.post(
                "/assistant/operator/browser/open_url",
                json={"task_id": "op_test", "url": "https://example.com"},
            )

        self.assertEqual(response.status_code, 200)
        execute.assert_awaited_once()
        _, task_id, plan_step = execute.await_args.args
        self.assertEqual(task_id, "op_test")
        self.assertEqual(plan_step.step_id, "open_url_screenshot")
        self.assertEqual(plan_step.tool, "browser")
        self.assertEqual(plan_step.action["url"], "https://example.com")

    async def test_desktop_routes_pass_artifact_dirs(self) -> None:
        with patch("tools.operator_tools.desktop_windows.launch_app", return_value={"ok": True}) as launch:
            launch_response = await self.client.post("/assistant/desktop/launch", json={"command": "notepad.exe"})
        self.assertEqual(launch_response.status_code, 200)
        self.assertEqual(launch.call_args.kwargs["command"], "notepad.exe")
        self.assertEqual(Path(launch.call_args.kwargs["artifacts_dir"]).name, "desktop")

        with patch("tools.operator_tools.desktop_windows.screenshot_full", return_value={"ok": True}) as screenshot_full:
            screenshot_response = await self.client.post("/assistant/desktop/screenshot_full", json={})
        self.assertEqual(screenshot_response.status_code, 200)
        self.assertEqual(Path(screenshot_full.call_args.kwargs["artifacts_dir"]).name, "desktop")

        with patch("tools.operator_tools.desktop_windows.screenshot_window_title", return_value={"ok": True}) as screenshot_window:
            window_response = await self.client.post(
                "/assistant/desktop/screenshot_window_title",
                json={"title": "Notepad"},
            )
        self.assertEqual(window_response.status_code, 200)
        self.assertEqual(screenshot_window.call_args.kwargs["title_contains"], "Notepad")
        self.assertEqual(Path(screenshot_window.call_args.kwargs["artifacts_dir"]).name, "desktop")

    async def test_voice_routes_use_voice_module(self) -> None:
        with patch.object(server.voice, "speak", return_value={"ok": True}) as speak:
            speak_response = await self.client.post("/assistant/voice/speak", json={"text": "hello"})
        self.assertEqual(speak_response.status_code, 200)
        self.assertEqual(speak.call_args.kwargs["text"], "hello")
        self.assertEqual(Path(speak.call_args.kwargs["artifacts_dir"]).name, "voice")

        with patch.object(server.voice, "listen_once", return_value={"ok": False, "error": "missing_vosk_model_path"}) as listen_once:
            listen_response = await self.client.post("/assistant/voice/listen_once", json={"seconds": 1})
        self.assertEqual(listen_response.status_code, 200)
        self.assertEqual(listen_once.call_args.kwargs["seconds"], 1)
        self.assertEqual(Path(listen_once.call_args.kwargs["artifacts_dir"]).name, "voice")

    async def test_config_endpoint_redacts_sensitive_values(self) -> None:
        entries = server.bridge.config_manager._config.setdefault("skills", {}).setdefault("entries", {})
        sentinel_key = "__redaction_test__"
        original = entries.get(sentinel_key)
        entries[sentinel_key] = {"apiKey": "LEAK_ME_123", "enabled": True}
        try:
            response = await self.client.get("/assistant/config")
        finally:
            if original is None:
                entries.pop(sentinel_key, None)
            else:
                entries[sentinel_key] = original

        self.assertEqual(response.status_code, 200)
        self.assertFalse("LEAK_ME_123" in response.text, "sensitive value leaked in /assistant/config")
        body = response.json()
        self.assertEqual(body["config"]["skills"]["entries"][sentinel_key]["apiKey"], "<redacted>")

    async def test_awarenet_deep_link_returns_index(self) -> None:
        response = await self.client.get("/awarenet/overview")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Awarenet Control Center", response.text)
