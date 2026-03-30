import argparse
import sys
from typing import Any, Dict

import requests


def _post_chat(host: str, model: str, text: str) -> str:
    url = host.rstrip("/") + "/v1/chat/completions"
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": text}],
    }
    response = requests.post(url, json=payload, timeout=120)
    if response.status_code != 200:
        raise RuntimeError(f"Server error {response.status_code}: {response.text}")
    data = response.json()
    choices = data.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        return str(message.get("content") or "").strip()
    return str(data)


def _run_once(host: str, model: str, text: str) -> int:
    output = _post_chat(host, model, text)
    if output:
        print(output)
    return 0


def _interactive_loop(host: str, model: str) -> int:
    try:
        while True:
            try:
                line = input("> ").strip()
            except EOFError:
                break
            if not line:
                continue
            output = _post_chat(host, model, line)
            if output:
                print(output)
    except KeyboardInterrupt:
        return 0
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="openclaw")
    subparsers = parser.add_subparsers(dest="command")

    def add_run_parser(name: str):
        run_parser = subparsers.add_parser(name)
        run_parser.add_argument("model", nargs="?", default="awarenet")
        run_parser.add_argument("--once", dest="once", default=None)
        run_parser.add_argument("--host", dest="host", default="http://localhost:8000")
        return run_parser

    add_run_parser("run")
    add_run_parser("chat")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    model = args.model
    host = args.host

    if args.once is not None:
        return _run_once(host, model, args.once)

    if not sys.stdin.isatty():
        text = sys.stdin.read().strip()
        if text:
            return _run_once(host, model, text)
        return 0

    return _interactive_loop(host, model)


if __name__ == "__main__":
    raise SystemExit(main())
