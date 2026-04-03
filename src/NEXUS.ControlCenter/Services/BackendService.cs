using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using NEXUS.ControlCenter.Models;

namespace NEXUS.ControlCenter.Services;

public sealed class BackendService
{
    private static readonly int[] CommonPorts = [8000, 8001, 8002, 8003, 8004, 8005, 8006, 8010];
    private static readonly JsonSerializerOptions PrettyJsonOptions = new() { WriteIndented = true };
    private readonly HttpClient _http = new() { Timeout = TimeSpan.FromMilliseconds(1500) };

    public string BaseUrl { get; private set; } = "http://127.0.0.1:8000";

    public bool IsConnected { get; private set; }

    public string LastError { get; private set; } = "";

    public async Task<bool> AutoDiscoverAsync()
    {
        foreach (var port in CommonPorts)
        {
            var url = $"http://127.0.0.1:{port}";
            if (await ProbeAsync(url))
            {
                BaseUrl = url;
                return true;
            }
        }

        IsConnected = false;
        if (string.IsNullOrWhiteSpace(LastError))
        {
            LastError = "Backend not reachable on common ports.";
        }

        return false;
    }

    public async Task<bool> ConnectAsync(string baseUrl)
    {
        if (string.IsNullOrWhiteSpace(baseUrl))
        {
            return await AutoDiscoverAsync();
        }

        if (await ProbeAsync(baseUrl))
        {
            BaseUrl = baseUrl.TrimEnd('/');
            return true;
        }

        return false;
    }

    public BackendConnectionState CreateConnectionState()
    {
        var status = IsConnected ? "Connected" : "Disconnected";
        return new BackendConnectionState(BaseUrl, IsConnected, LastError, status);
    }

    public async Task<IReadOnlyList<ChatThreadSummary>> GetChatThreadsAsync(int limit = 40)
    {
        using var doc = await GetJsonAsync($"/assistant/chat/list?limit={limit}");
        var items = new List<ChatThreadSummary>();

        if (doc.RootElement.TryGetProperty("chats", out var chats) && chats.ValueKind == JsonValueKind.Array)
        {
            foreach (var chat in chats.EnumerateArray())
            {
                var chatId = GetString(chat, "chat_id");
                if (string.IsNullOrWhiteSpace(chatId))
                {
                    continue;
                }

                var updated = GetString(chat, "updated_at");
                items.Add(new ChatThreadSummary(
                    chatId,
                    chatId,
                    "Linked to assistant chat history",
                    string.IsNullOrWhiteSpace(updated) ? "recent" : updated));
            }
        }

        return items;
    }

    public async Task<IReadOnlyList<ChatMessageSummary>> GetChatHistoryAsync(string chatId, int limit = 80)
    {
        using var doc = await GetJsonAsync($"/assistant/chat/history?chat_id={Uri.EscapeDataString(chatId)}&limit={limit}");
        var items = new List<ChatMessageSummary>();

        if (doc.RootElement.TryGetProperty("events", out var eventsEl) && eventsEl.ValueKind == JsonValueKind.Array)
        {
            foreach (var entry in eventsEl.EnumerateArray())
            {
                var role = GetString(entry, "role", "assistant");
                var content = GetString(entry, "content");
                var ts = GetString(entry, "ts");
                items.Add(new ChatMessageSummary(role, content, string.IsNullOrWhiteSpace(ts) ? "now" : ts));
            }
        }

        return items;
    }

    public async Task<ChatSendResult> SendChatAsync(string chatId, string message)
    {
        using var doc = await PostJsonAsync("/assistant/chat/send", new
        {
            chat_id = string.IsNullOrWhiteSpace(chatId) ? null : chatId,
            model = "assistant",
            message,
        });

        var actualChatId = GetString(doc.RootElement, "chat_id", chatId);
        var reply = GetString(doc.RootElement, "response");
        return new ChatSendResult(actualChatId, reply);
    }

    public async Task<AssistantOverviewDetails> GetOverviewDetailsAsync()
    {
        using var statusDoc = await GetJsonAsync("/assistant/status");
        using var gatewayDoc = await GetJsonAsync("/assistant/openclaw/health");

        var policySummary = statusDoc.RootElement.TryGetProperty("policy", out var policyEl)
            ? CompactObject(policyEl)
            : "Policy unavailable";
        var memorySummary = statusDoc.RootElement.TryGetProperty("memory", out var memoryEl)
            ? CompactObject(memoryEl)
            : "Memory summary unavailable";
        var gatewaySummary = CompactObject(gatewayDoc.RootElement);

        return new AssistantOverviewDetails(policySummary, memorySummary, gatewaySummary);
    }

    public async Task<OperatorTaskSummary> StartOperatorTaskAsync(string goal)
    {
        using var doc = await PostJsonAsync("/assistant/operator/start", new { goal });
        var taskId = GetString(doc.RootElement, "task_id");
        var artifactsDir = GetString(doc.RootElement, "artifacts_dir");
        return new OperatorTaskSummary(taskId, goal, "active", "just now", artifactsDir, "");
    }

    public async Task<OperatorStateSnapshot> GetOperatorStateAsync(bool includeHistory = true)
    {
        using var doc = await GetJsonAsync($"/assistant/operator/state?include_history={(includeHistory ? "true" : "false")}");
        var active = default(OperatorTaskSummary);
        var history = new List<OperatorTaskSummary>();

        if (doc.RootElement.TryGetProperty("operator", out var operatorEl))
        {
            if (operatorEl.TryGetProperty("active", out var activeEl) && activeEl.ValueKind == JsonValueKind.Object)
            {
                active = ParseOperatorTask(activeEl);
            }

            if (operatorEl.TryGetProperty("history", out var historyEl) && historyEl.ValueKind == JsonValueKind.Array)
            {
                foreach (var item in historyEl.EnumerateArray())
                {
                    history.Add(ParseOperatorTask(item));
                }
            }
        }

        return new OperatorStateSnapshot(active, history);
    }

    public async Task<IReadOnlyList<OperatorArtifactSummary>> GetOperatorArtifactsAsync(string taskId)
    {
        using var doc = await GetJsonAsync($"/assistant/operator/artifacts?task_id={Uri.EscapeDataString(taskId)}&tail=100");
        var items = new List<OperatorArtifactSummary>();

        if (doc.RootElement.TryGetProperty("files", out var filesEl) && filesEl.ValueKind == JsonValueKind.Array)
        {
            foreach (var file in filesEl.EnumerateArray())
            {
                var name = GetString(file, "name");
                var path = GetString(file, "path");
                var updated = FormatJsonTimestamp(file, "mtime");
                var size = FormatBytes(GetLong(file, "size"));
                items.Add(new OperatorArtifactSummary(name, path, updated, size));
            }
        }

        return items;
    }

    public async Task<ApprovalStateSnapshot> GetApprovalsAsync(bool includeHistory = true)
    {
        using var doc = await GetJsonAsync($"/assistant/approvals?include_history={(includeHistory ? "true" : "false")}");
        var pending = new List<ApprovalSummary>();
        var history = new List<ApprovalSummary>();

        if (doc.RootElement.TryGetProperty("approvals", out var approvalsEl))
        {
            if (approvalsEl.TryGetProperty("pending", out var pendingEl) && pendingEl.ValueKind == JsonValueKind.Array)
            {
                foreach (var item in pendingEl.EnumerateArray())
                {
                    pending.Add(ParseApproval(item));
                }
            }

            if (approvalsEl.TryGetProperty("history", out var historyEl) && historyEl.ValueKind == JsonValueKind.Array)
            {
                foreach (var item in historyEl.EnumerateArray())
                {
                    history.Add(ParseApproval(item));
                }
            }
        }

        return new ApprovalStateSnapshot(pending, history);
    }

    public async Task<ApprovalSummary> ResolveApprovalAsync(string approvalId, bool approved, string note = "")
    {
        using var doc = await PostJsonAsync("/assistant/approvals/resolve", new
        {
            id = approvalId,
            approved,
            note,
        });

        if (doc.RootElement.TryGetProperty("approval", out var approvalEl) && approvalEl.ValueKind == JsonValueKind.Object)
        {
            return ParseApproval(approvalEl);
        }

        return new ApprovalSummary(approvalId, approvalId, "", approved ? "approved" : "rejected", "", "", "just now");
    }

    public async Task<string> ContinueApprovalAsync(string approvalId, string note = "")
    {
        using var doc = await PostJsonAsync("/assistant/approvals/continue", new
        {
            id = approvalId,
            note,
        });

        var executed = GetBoolean(doc.RootElement, "executed");
        var result = doc.RootElement.TryGetProperty("result", out var resultEl)
            ? CompactObject(resultEl)
            : "";
        return executed ? $"Approved and continued. {result}" : GetString(doc.RootElement, "error", "Approved, but no executable step was attached.");
    }

    public async Task<IReadOnlyList<DesktopWindowSummary>> GetDesktopWindowsAsync()
    {
        using var doc = await GetJsonAsync("/assistant/desktop/windows");
        var items = new List<DesktopWindowSummary>();

        if (doc.RootElement.TryGetProperty("result", out var resultEl)
            && resultEl.TryGetProperty("windows", out var windowsEl)
            && windowsEl.ValueKind == JsonValueKind.Array)
        {
            foreach (var window in windowsEl.EnumerateArray())
            {
                items.Add(new DesktopWindowSummary(
                    GetString(window, "title", "(untitled)"),
                    GetString(window, "class_name"),
                    $"Handle {GetString(window, "handle")}"));
            }
        }

        return items;
    }

    public async Task<DesktopActionResult> LaunchDesktopAppAsync(string command)
    {
        using var doc = await PostJsonAsync("/assistant/desktop/launch", new { command });
        return ParseDesktopAction(doc.RootElement);
    }

    public async Task<DesktopActionResult> ScreenshotDesktopFullAsync()
    {
        using var doc = await PostJsonAsync("/assistant/desktop/screenshot_full", new { });
        return ParseDesktopAction(doc.RootElement);
    }

    public async Task<DesktopActionResult> ScreenshotDesktopWindowAsync(string title)
    {
        using var doc = await PostJsonAsync("/assistant/desktop/screenshot_window_title", new { title });
        return ParseDesktopAction(doc.RootElement);
    }

    public async Task<VoiceActionResult> SpeakAsync(string text)
    {
        using var doc = await PostJsonAsync("/assistant/voice/speak", new { text });
        return ParseVoiceAction(doc.RootElement, "Spoke text through the configured runtime.");
    }

    public async Task<VoiceActionResult> ListenOnceAsync(int seconds)
    {
        using var doc = await PostJsonAsync("/assistant/voice/listen_once", new { seconds });
        return ParseVoiceAction(doc.RootElement, "Captured a single listen pass.");
    }

    public async Task<VoiceActionResult> RunVoiceCommandAsync(string text, int maxSteps = 8)
    {
        using var doc = await PostJsonAsync("/assistant/voice/command", new { text, max_steps = maxSteps });
        return ParseVoiceAction(doc.RootElement, "Ran the voice command through the operator loop.");
    }

    public async Task<BrowserActionSummary> OpenBrowserUrlAsync(string url)
    {
        var task = await StartOperatorTaskAsync($"Open {url}");
        using var doc = await PostJsonAsync("/assistant/operator/browser/open_url", new
        {
            task_id = task.TaskId,
            url,
        });

        var artifactPath = "";
        if (doc.RootElement.TryGetProperty("artifact_paths", out var artifactsEl) && artifactsEl.ValueKind == JsonValueKind.Array)
        {
            foreach (var path in artifactsEl.EnumerateArray())
            {
                artifactPath = path.ToString();
                if (!string.IsNullOrWhiteSpace(artifactPath))
                {
                    break;
                }
            }
        }

        return new BrowserActionSummary(
            GetString(doc.RootElement, "status", "ok").Equals("ok", StringComparison.OrdinalIgnoreCase),
            task.TaskId,
            $"Opened {url}",
            CompactObject(doc.RootElement),
            artifactPath);
    }

    public async Task<IReadOnlyList<ModuleFeatureSummary>> GetModuleFeaturesAsync()
    {
        using var capabilitiesDoc = await GetJsonAsync("/assistant/capabilities");
        using var featuresDoc = await GetJsonAsync("/assistant/features");

        var names = new SortedSet<string>(StringComparer.OrdinalIgnoreCase);
        if (capabilitiesDoc.RootElement.TryGetProperty("modules", out var capabilitiesEl) && capabilitiesEl.ValueKind == JsonValueKind.Object)
        {
            foreach (var property in capabilitiesEl.EnumerateObject())
            {
                names.Add(property.Name);
            }
        }

        if (featuresDoc.RootElement.TryGetProperty("features", out var featuresEl) && featuresEl.ValueKind == JsonValueKind.Object)
        {
            foreach (var property in featuresEl.EnumerateObject())
            {
                names.Add(property.Name);
            }
        }

        var items = new List<ModuleFeatureSummary>();
        foreach (var name in names)
        {
            var available = false;
            var availabilityReason = "";
            var enabled = false;
            var mode = "";
            var scope = "";

            if (capabilitiesDoc.RootElement.TryGetProperty("modules", out var modulesEl)
                && modulesEl.ValueKind == JsonValueKind.Object
                && modulesEl.TryGetProperty(name, out var moduleEl))
            {
                available = GetBoolean(moduleEl, "available");
                availabilityReason = GetString(moduleEl, "reason");
            }

            if (featuresDoc.RootElement.TryGetProperty("features", out var rootFeaturesEl)
                && rootFeaturesEl.ValueKind == JsonValueKind.Object
                && rootFeaturesEl.TryGetProperty(name, out var featureEl))
            {
                enabled = GetBoolean(featureEl, "enabled");
                mode = GetString(featureEl, "mode");
                scope = GetString(featureEl, "scope");
            }

            items.Add(new ModuleFeatureSummary(name, available, availabilityReason, enabled, mode, scope));
        }

        return items;
    }

    public async Task UpdateModuleFeatureAsync(string name, bool enabled, string mode, string scope)
    {
        var payload = new Dictionary<string, object?>
        {
            [name] = new Dictionary<string, object?>
            {
                ["enabled"] = enabled,
                ["mode"] = mode,
                ["scope"] = scope,
            },
        };

        using var _ = await PostJsonAsync("/assistant/features", payload);
    }

    public async Task<BackendConfigSummary> GetBackendConfigAsync()
    {
        using var doc = await GetJsonAsync("/assistant/config");
        var pretty = doc.RootElement.TryGetProperty("config", out var configEl)
            ? PrettyJson(configEl)
            : "{}";
        var snapshots = new List<ConfigSnapshotSummary>();

        if (doc.RootElement.TryGetProperty("snapshots", out var snapshotsEl) && snapshotsEl.ValueKind == JsonValueKind.Array)
        {
            foreach (var snapshot in snapshotsEl.EnumerateArray())
            {
                snapshots.Add(ParseSnapshot(snapshot));
            }
        }

        return new BackendConfigSummary(pretty, snapshots);
    }

    public async Task<ConfigSnapshotSummary> CreateConfigSnapshotAsync()
    {
        using var doc = await PostJsonAsync("/assistant/config/snapshot", new { });
        if (doc.RootElement.TryGetProperty("snapshot", out var snapshotEl) && snapshotEl.ValueKind == JsonValueKind.Object)
        {
            return ParseSnapshot(snapshotEl);
        }

        return new ConfigSnapshotSummary("", "just now", "Snapshot created");
    }

    public async Task<JsonDocument> GetHealthAsync()
    {
        return await GetJsonAsync("/assistant/health");
    }

    private async Task<JsonDocument> GetJsonAsync(string pathAndQuery)
    {
        var json = await _http.GetStringAsync($"{BaseUrl}{pathAndQuery}");
        return JsonDocument.Parse(json);
    }

    private async Task<JsonDocument> PostJsonAsync(string path, object payload)
    {
        using var response = await _http.PostAsJsonAsync($"{BaseUrl}{path}", payload);
        var body = await response.Content.ReadAsStringAsync();
        if (!response.IsSuccessStatusCode)
        {
            throw new InvalidOperationException(body);
        }

        return JsonDocument.Parse(body);
    }

    private async Task<bool> ProbeAsync(string baseUrl)
    {
        try
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromMilliseconds(1200));
            using var response = await _http.GetAsync($"{baseUrl.TrimEnd('/')}/assistant/health", cts.Token);
            if (!response.IsSuccessStatusCode)
            {
                IsConnected = false;
                LastError = $"health_http_{(int)response.StatusCode}";
                return false;
            }

            BaseUrl = baseUrl.TrimEnd('/');
            IsConnected = true;
            LastError = "";
            return true;
        }
        catch (Exception ex)
        {
            IsConnected = false;
            LastError = ex.Message;
            return false;
        }
    }

    private static OperatorTaskSummary ParseOperatorTask(JsonElement element)
    {
        var startedAt = GetString(element, "started_at");
        var completedAt = GetString(element, "completed_at");
        var lastObservation = element.TryGetProperty("last_observation", out var observationEl)
            ? GetString(observationEl, "summary")
            : "";

        return new OperatorTaskSummary(
            GetString(element, "task_id"),
            GetString(element, "goal", "Untitled task"),
            GetString(element, "status", "unknown"),
            NormalizeTimestamp(!string.IsNullOrWhiteSpace(completedAt) ? completedAt : startedAt),
            GetString(element, "artifacts_dir"),
            string.IsNullOrWhiteSpace(lastObservation) ? "No observation captured yet." : lastObservation);
    }

    private static ApprovalSummary ParseApproval(JsonElement element)
    {
        var resolved = GetString(element, "resolved_at");
        var created = GetString(element, "ts");
        return new ApprovalSummary(
            GetString(element, "id"),
            GetString(element, "title", "Approval request"),
            GetString(element, "detail"),
            GetString(element, "status", "pending"),
            GetString(element, "risk", "normal"),
            GetString(element, "tool", "operator"),
            NormalizeTimestamp(!string.IsNullOrWhiteSpace(resolved) ? resolved : created));
    }

    private static DesktopActionResult ParseDesktopAction(JsonElement root)
    {
        if (!root.TryGetProperty("result", out var resultEl) || resultEl.ValueKind != JsonValueKind.Object)
        {
            return new DesktopActionResult(false, "Desktop action failed", CompactObject(root), "");
        }

        var ok = GetBoolean(resultEl, "ok");
        var artifactPath = GetString(resultEl, "screenshot_path");
        var summary = ok ? "Desktop action completed." : "Desktop action failed.";
        return new DesktopActionResult(ok, summary, CompactObject(resultEl), artifactPath);
    }

    private static VoiceActionResult ParseVoiceAction(JsonElement root, string successSummary)
    {
        if (!root.TryGetProperty("result", out var resultEl) || resultEl.ValueKind != JsonValueKind.Object)
        {
            return new VoiceActionResult(false, "Voice action failed", CompactObject(root), "");
        }

        var ok = GetBoolean(resultEl, "ok", true);
        var artifactPath = GetString(resultEl, "audio_path");
        if (string.IsNullOrWhiteSpace(artifactPath))
        {
            artifactPath = GetString(resultEl, "artifact_path");
        }

        return new VoiceActionResult(
            ok,
            ok ? successSummary : "Voice action failed.",
            CompactObject(resultEl),
            artifactPath);
    }

    private static ConfigSnapshotSummary ParseSnapshot(JsonElement snapshot)
    {
        return new ConfigSnapshotSummary(
            GetString(snapshot, "id"),
            NormalizeTimestamp(GetString(snapshot, "ts", GetString(snapshot, "created_at"))),
            CompactObject(snapshot));
    }

    private static string PrettyJson(JsonElement element)
    {
        return JsonSerializer.Serialize(element, PrettyJsonOptions);
    }

    private static string CompactObject(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            var parts = new List<string>();
            foreach (var property in element.EnumerateObject())
            {
                if (property.Value.ValueKind is JsonValueKind.Object or JsonValueKind.Array)
                {
                    parts.Add($"{property.Name}={property.Value.ValueKind.ToString().ToLowerInvariant()}");
                }
                else
                {
                    parts.Add($"{property.Name}={property.Value}");
                }
            }

            return string.Join(" | ", parts);
        }

        if (element.ValueKind == JsonValueKind.Array)
        {
            return $"array[{element.GetArrayLength()}]";
        }

        return element.ToString();
    }

    private static string GetString(JsonElement element, string property, string defaultValue = "")
    {
        if (element.ValueKind != JsonValueKind.Object || !element.TryGetProperty(property, out var value))
        {
            return defaultValue;
        }

        return value.ValueKind switch
        {
            JsonValueKind.String => value.GetString() ?? defaultValue,
            JsonValueKind.Number => value.ToString(),
            JsonValueKind.True => "true",
            JsonValueKind.False => "false",
            JsonValueKind.Null => defaultValue,
            _ => value.ToString(),
        };
    }

    private static bool GetBoolean(JsonElement element, string property, bool defaultValue = false)
    {
        if (element.ValueKind != JsonValueKind.Object || !element.TryGetProperty(property, out var value))
        {
            return defaultValue;
        }

        return value.ValueKind switch
        {
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            JsonValueKind.String when bool.TryParse(value.GetString(), out var parsed) => parsed,
            _ => defaultValue,
        };
    }

    private static long GetLong(JsonElement element, string property)
    {
        if (element.ValueKind != JsonValueKind.Object || !element.TryGetProperty(property, out var value))
        {
            return 0;
        }

        if (value.ValueKind == JsonValueKind.Number && value.TryGetInt64(out var parsed))
        {
            return parsed;
        }

        if (value.ValueKind == JsonValueKind.String && long.TryParse(value.GetString(), out parsed))
        {
            return parsed;
        }

        return 0;
    }

    private static string FormatJsonTimestamp(JsonElement element, string property)
    {
        if (element.ValueKind != JsonValueKind.Object || !element.TryGetProperty(property, out var value))
        {
            return "";
        }

        if (value.ValueKind == JsonValueKind.Number && value.TryGetDouble(out var unixSeconds))
        {
            return DateTimeOffset.FromUnixTimeSeconds((long)unixSeconds).ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss");
        }

        return NormalizeTimestamp(value.ToString());
    }

    private static string NormalizeTimestamp(string raw)
    {
        if (string.IsNullOrWhiteSpace(raw))
        {
            return "just now";
        }

        if (DateTimeOffset.TryParse(raw, out var parsed))
        {
            return parsed.ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss");
        }

        return raw;
    }

    private static string FormatBytes(long bytes)
    {
        if (bytes <= 0)
        {
            return "0 B";
        }

        string[] suffixes = ["B", "KB", "MB", "GB"];
        double size = bytes;
        var index = 0;
        while (size >= 1024 && index < suffixes.Length - 1)
        {
            size /= 1024;
            index++;
        }

        return $"{size:0.#} {suffixes[index]}";
    }
}
