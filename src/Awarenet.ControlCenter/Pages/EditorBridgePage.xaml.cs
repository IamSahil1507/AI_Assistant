using System;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.UI.Xaml.Controls;

namespace Awarenet.ControlCenter.Pages;

public sealed partial class EditorBridgePage : Page
{
    private const string BaseUrl = "http://127.0.0.1:8000";
    private readonly HttpClient _http = new();

    public EditorBridgePage()
    {
        InitializeComponent();
        HealthButton.Click += async (_, _) => await HealthAsync();
        OpenButton.Click += async (_, _) => await OpenAsync();
    }

    private async Task HealthAsync()
    {
        ErrorBar.IsOpen = false;
        try
        {
            var json = await _http.GetStringAsync($"{BaseUrl}/assistant/editor/health");
            ResultBox.Text = json;
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
    }

    private async Task OpenAsync()
    {
        ErrorBar.IsOpen = false;
        try
        {
            var path = (PathBox.Text ?? "").Trim();
            if (string.IsNullOrWhiteSpace(path))
            {
                return;
            }

            // Reuse operator step for editor tool calls.
            // Need an active operator task id; if missing, we show a friendly message.
            var state = await _http.GetStringAsync($"{BaseUrl}/assistant/operator/state?include_history=false");
            using var doc = JsonDocument.Parse(state);
            var active = doc.RootElement.GetProperty("operator").GetProperty("active");
            var taskId = active.ValueKind == JsonValueKind.Object && active.TryGetProperty("task_id", out var tid) ? (tid.GetString() ?? "") : "";
            if (string.IsNullOrWhiteSpace(taskId))
            {
                throw new InvalidOperationException("No active operator task. Start one in Operator tab first.");
            }

            var body = new
            {
                task_id = taskId,
                tool = "editor",
                goal = "open_file",
                step_id = "open_file",
                risk = "normal",
                action = new { type = "open_file", path },
            };
            var resp = await _http.PostAsJsonAsync($"{BaseUrl}/assistant/operator/step", body);
            var text = await resp.Content.ReadAsStringAsync();
            if (!resp.IsSuccessStatusCode)
            {
                throw new InvalidOperationException(text);
            }
            ResultBox.Text = text;
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
    }
}

