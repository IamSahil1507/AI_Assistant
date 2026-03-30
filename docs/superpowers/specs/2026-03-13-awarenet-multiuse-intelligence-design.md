# Awarenet Multiuse Intelligence Design

Date: 2026-03-13

## Summary

Make the Awarenet proxy behave consistently smart across situations by adding a confidence-driven intent policy, lightweight memory of the last intent and project root, and a detailed project overview follow-up path. Integrate skills.sh discovery so the system can extend capabilities safely when the intent maps to an installed skill.

## Goals

- Avoid "dumb" fall-throughs when the user asks follow-ups like "fully detailed overview".
- React based on situation: act immediately when confident, ask when unsure, and do a minimal safe action for medium confidence.
- Provide a detailed project overview without requiring the user to repeat "project".
- Enable skills discovery and optional install workflow for multiuse expansion.
- Keep responses fast and safe (no secrets or large file content).

## Non-goals

- Full semantic memory across unrelated topics or long-term conversations.
- Reading or exposing secret file contents.
- Large refactors of the proxy architecture.

## Approach Options Considered

1. Confidence-driven triage (recommended)
2. Ask-first for any ambiguity
3. Act-first best-guess in all cases

## Selected Approach

Confidence-driven triage:
- High confidence: do the action.
- Medium confidence: do a minimal safe action and ask a short confirmation.
- Low confidence: ask a single clarifying question.

## Intent Policy

Maintain a lightweight "last intent" memory with timestamp. Example intents:
- project_overview
- project_detail
- code_review
- debugging
- docs_summary
- general_qna
- skill_request

Decision rules:
- If the new request is clearly mapped to a known intent, run it.
- If ambiguous:
  - If last intent is recent and confidence is high, reuse last intent.
  - If medium confidence, run a minimal safe action plus a confirm question.
  - If low confidence, ask one clarifying question.

## Project Detail Follow-up

Add detail intent detection so follow-ups like "fully detailed overview" use the last project root.

### Data shape

```
memory = {
  ...
  "project": {
    "last_root": "C:\\AI_Assistant",
    "last_ts": 1773409999
  },
  "intent": {
    "last": "project_overview",
    "last_ts": 1773409999
  }
}
```

### Detail intent detection

- Detect "detailed", "full", "complete", "in depth" in requests.
- Trigger detail overview when:
  - detail intent and last_root exists, or
  - project intent + detail intent present together.

### Detailed overview content

Return a deeper overview including:
- High-level summary based on known folders and key files.
- Entrypoints if present (e.g., api/server.py, api/ollama_proxy.py).
- API route list by scanning @app.get/post/etc in api/.
- Primary file types and language counts.
- Notable configs by file name only.
- Hot spots (largest or most central files), bounded by limits.

## Skills.sh Integration

When intent maps to a known skill domain:
- Use skills discovery (npx skills find <keywords>).
- Only install a skill when the user explicitly asks.
- Support opt-out of telemetry for installs.

## Safety and Performance

- Skip directories: .git, .venv, node_modules, logs, data, dist, build, caches.
- Limit scans to a max file count.
- Skip large files (e.g., > 2-4 MB) and binary extensions.
- Do not read or output contents of secrets (.env, *.key, *.pem, secrets.*).
- Output file names and paths only for sensitive candidates.

## Logging

Add debug logs to verify behavior:
- openai_clean_user
- detail_overview: { root, reason }
- intent_policy: { confidence, chosen_intent }

## Edge Cases

- If no root can be resolved: return a clear "project root not found" message.
- If last_root is missing or deleted: fall back to workspace root.
- If scan yields no files: return a minimal overview with next-step guidance.

## Testing Plan

Manual:
1. Ask: "analyze currently opened whole project" -> basic overview.
2. Ask: "fully detailed overview" -> detailed overview using last_root.
3. Ask: "detailed overview" without prior request -> fallback to workspace root or ask.
4. Confirm no secret content is printed.
5. Ask an ambiguous request -> check confidence policy behavior.

Log verification:
- openai_clean_user reflects detail intent.
- detail_overview log entry recorded with correct root.
