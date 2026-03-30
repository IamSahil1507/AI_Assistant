using System;
using System.Collections.ObjectModel;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.UI.Xaml.Controls;

namespace Awarenet.ControlCenter.Pages;

public sealed partial class OperatorPage : Page
{
    private readonly HttpClient _http = new();
    private readonly ObservableCollection<HistoryVm> _history = new();
    private readonly ObservableCollection<string> _artifacts = new();
    private string _activeTaskId = "";

    public OperatorPage()
    {
        InitializeComponent();
        HistoryList.ItemsSource = _history;
        ArtifactsList.ItemsSource = _artifacts;
        StartButton.Click += async (_, _) => await StartAsync();
        RefreshButton.Click += async (_, _) => await RefreshAsync(includeHistory: true);

        _ = RefreshAsync(includeHistory: false);
    }

    private async Task StartAsync()
    {
        var goal = (GoalBox.Text ?? "").Trim();
        if (string.IsNullOrWhiteSpace(goal))
        {
            return;
        }

        OpErrorBar.IsOpen = false;
        try
        {
            var resp = await _http.PostAsJsonAsync("http://127.0.0.1:8000/assistant/operator/start", new { goal });
            var text = await resp.Content.ReadAsStringAsync();
            if (!resp.IsSuccessStatusCode)
            {
                throw new InvalidOperationException(text);
            }

            await RefreshAsync(includeHistory: true);
        }
        catch (Exception ex)
        {
            OpErrorBar.Message = ex.Message;
            OpErrorBar.IsOpen = true;
        }
    }

    private async Task RefreshAsync(bool includeHistory)
    {
        OpErrorBar.IsOpen = false;
        try
        {
            var url = $"http://127.0.0.1:8000/assistant/operator/state?include_history={(includeHistory ? "true" : "false")}";
            var json = await _http.GetStringAsync(url);
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            if (!root.TryGetProperty("operator", out var op))
            {
                return;
            }

            var active = op.TryGetProperty("active", out var a) ? a : default;
            if (active.ValueKind == JsonValueKind.Object)
            {
                var taskId = active.TryGetProperty("task_id", out var tid) ? (tid.GetString() ?? "") : "";
                var goal = active.TryGetProperty("goal", out var g) ? (g.GetString() ?? "") : "";
                var status = active.TryGetProperty("status", out var s) ? (s.GetString() ?? "") : "";
                ActiveSummary.Text = $"task_id: {taskId}\nstatus: {status}\ngoal: {goal}";
                _activeTaskId = taskId;
                await RefreshArtifactsAsync(taskId);
            }
            else
            {
                ActiveSummary.Text = "No active operator task.";
                _activeTaskId = "";
                _artifacts.Clear();
            }

            if (includeHistory && op.TryGetProperty("history", out var hist) && hist.ValueKind == JsonValueKind.Array)
            {
                _history.Clear();
                foreach (var item in hist.EnumerateArray())
                {
                    var taskId = item.TryGetProperty("task_id", out var tid) ? (tid.GetString() ?? "") : "";
                    var goal = item.TryGetProperty("goal", out var g) ? (g.GetString() ?? "") : "";
                    var status = item.TryGetProperty("status", out var s) ? (s.GetString() ?? "") : "";
                    _history.Add(new HistoryVm($"Task {taskId}", $"{status} — {goal}"));
                }
            }
        }
        catch (Exception ex)
        {
            OpErrorBar.Message = ex.Message;
            OpErrorBar.IsOpen = true;
        }
    }

    private async Task RefreshArtifactsAsync(string taskId)
    {
        if (string.IsNullOrWhiteSpace(taskId))
        {
            _artifacts.Clear();
            return;
        }
        try
        {
            var json = await _http.GetStringAsync($"http://127.0.0.1:8000/assistant/operator/artifacts?task_id={Uri.EscapeDataString(taskId)}&tail=30");
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            if (!root.TryGetProperty("files", out var files) || files.ValueKind != JsonValueKind.Array)
            {
                return;
            }
            _artifacts.Clear();
            foreach (var f in files.EnumerateArray())
            {
                var name = f.TryGetProperty("name", out var n) ? (n.GetString() ?? "") : "";
                if (!string.IsNullOrWhiteSpace(name))
                {
                    _artifacts.Add(name);
                }
            }
        }
        catch
        {
            // best effort
        }
    }

    private sealed record HistoryVm(string Title, string Detail);
}

