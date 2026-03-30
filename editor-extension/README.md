## Awarenet Operator Bridge (VS Code / Cursor Extension)

This extension exposes a small **local HTTP API** so the Awarenet operator can control the editor (VS Code or Cursor).

### Endpoints (localhost only)
- `GET /health`
- `POST /openFile` `{ "path": "C:\\path\\to\\file" }`
- `POST /search` `{ "query": "text", "include": "**/*" }`
- `POST /applyEdits` `{ "path": "...", "edits": [{ "startLine": 1, "startCol": 1, "endLine": 1, "endCol": 1, "text": "..." }] }`
- `POST /runTask` `{ "name": "build" }`

### Build
From `editor-extension/`:

```bash
npm install
npm run build
```

### Install (dev)
Use "Developer: Install Extension from Location..." and select the `editor-extension/` folder after building.

