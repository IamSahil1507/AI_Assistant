import * as http from "http";
import * as url from "url";
import * as vscode from "vscode";

type Json = null | boolean | number | string | Json[] | { [k: string]: Json };

function jsonResponse(res: http.ServerResponse, status: number, payload: unknown) {
  const body = JSON.stringify(payload);
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(body),
  });
  res.end(body);
}

async function readBody(req: http.IncomingMessage): Promise<any> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  const raw = Buffer.concat(chunks).toString("utf8").trim();
  if (!raw) return {};
  return JSON.parse(raw);
}

let server: http.Server | null = null;

async function handle(req: http.IncomingMessage, res: http.ServerResponse) {
  try {
    const parsed = url.parse(req.url || "", true);
    const method = (req.method || "GET").toUpperCase();

    if (parsed.pathname === "/health") {
      return jsonResponse(res, 200, { ok: true });
    }

    if (method === "POST" && parsed.pathname === "/openFile") {
      const body = await readBody(req);
      const filePath = String(body.path || "").trim();
      if (!filePath) return jsonResponse(res, 400, { ok: false, error: "missing_path" });
      const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(filePath));
      await vscode.window.showTextDocument(doc, { preview: false });
      return jsonResponse(res, 200, { ok: true });
    }

    if (method === "POST" && parsed.pathname === "/search") {
      const body = await readBody(req);
      const query = String(body.query || "").trim();
      if (!query) return jsonResponse(res, 400, { ok: false, error: "missing_query" });
      const include = typeof body.include === "string" ? body.include : "**/*";
      const results: Array<{ path: string; line: number; text: string }> = [];
      const files = await vscode.workspace.findFiles(include, "**/{node_modules,dist,build,.git}/**", 200);
      for (const file of files) {
        const doc = await vscode.workspace.openTextDocument(file);
        for (let i = 0; i < doc.lineCount; i++) {
          const t = doc.lineAt(i).text;
          if (t.includes(query)) {
            results.push({ path: file.fsPath, line: i + 1, text: t.slice(0, 400) });
            if (results.length >= 200) break;
          }
        }
        if (results.length >= 200) break;
      }
      return jsonResponse(res, 200, { ok: true, results, truncated: results.length >= 200 });
    }

    if (method === "POST" && parsed.pathname === "/applyEdits") {
      const body = await readBody(req);
      const filePath = String(body.path || "").trim();
      const edits = Array.isArray(body.edits) ? body.edits : [];
      if (!filePath) return jsonResponse(res, 400, { ok: false, error: "missing_path" });
      const uri = vscode.Uri.file(filePath);
      const doc = await vscode.workspace.openTextDocument(uri);
      const wsEdit = new vscode.WorkspaceEdit();
      for (const e of edits) {
        const startLine = Number(e.startLine || 1) - 1;
        const startCol = Number(e.startCol || 1) - 1;
        const endLine = Number(e.endLine || e.startLine || 1) - 1;
        const endCol = Number(e.endCol || e.startCol || 1) - 1;
        const text = String(e.text || "");
        wsEdit.replace(uri, new vscode.Range(startLine, startCol, endLine, endCol), text);
      }
      const ok = await vscode.workspace.applyEdit(wsEdit);
      if (!ok) return jsonResponse(res, 500, { ok: false, error: "apply_failed" });
      await doc.save();
      return jsonResponse(res, 200, { ok: true });
    }

    if (method === "POST" && parsed.pathname === "/runTask") {
      const body = await readBody(req);
      const taskName = String(body.name || "").trim();
      if (!taskName) return jsonResponse(res, 400, { ok: false, error: "missing_task_name" });
      const tasks = await vscode.tasks.fetchTasks();
      const match = tasks.find((t) => t.name === taskName);
      if (!match) return jsonResponse(res, 404, { ok: false, error: "task_not_found" });
      await vscode.tasks.executeTask(match);
      return jsonResponse(res, 200, { ok: true });
    }

    return jsonResponse(res, 404, { ok: false, error: "not_found" });
  } catch (err: any) {
    return jsonResponse(res, 500, { ok: false, error: String(err?.message || err) });
  }
}

function startServer(context: vscode.ExtensionContext) {
  if (server) return;
  const cfg = vscode.workspace.getConfiguration();
  const port = cfg.get<number>("awarenet.operatorBridge.port", 18999);
  const host = cfg.get<string>("awarenet.operatorBridge.bindHost", "127.0.0.1");

  server = http.createServer((req, res) => {
    void handle(req, res);
  });

  server.listen(port, host, () => {
    vscode.window.setStatusBarMessage(`Awarenet bridge listening on http://${host}:${port}`, 5000);
  });

  context.subscriptions.push({
    dispose() {
      try {
        server?.close();
      } finally {
        server = null;
      }
    },
  });
}

function stopServer() {
  if (!server) return;
  try {
    server.close();
  } finally {
    server = null;
  }
}

export function activate(context: vscode.ExtensionContext) {
  context.subscriptions.push(
    vscode.commands.registerCommand("awarenet.operatorBridge.start", () => startServer(context)),
    vscode.commands.registerCommand("awarenet.operatorBridge.stop", () => stopServer())
  );

  // Auto-start for v1.
  startServer(context);
}

export function deactivate() {
  stopServer();
}

