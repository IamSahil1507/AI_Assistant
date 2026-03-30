using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.UI.Xaml.Controls;

namespace Awarenet.ControlCenter.Pages;

public sealed partial class LogsPage : Page
{
    private readonly HttpClient _http = new();

    public LogsPage()
    {
        InitializeComponent();
        RefreshButton.Click += async (_, _) => await RefreshAsync();
        _ = RefreshAsync();
    }

    private async Task RefreshAsync()
    {
        ErrorBar.IsOpen = false;
        try
        {
            var kind = (LogKindBox.SelectedItem as ComboBoxItem)?.Content?.ToString() ?? "system";
            var baseUrl = Awarenet.ControlCenter.Services.BackendClient.BaseUrl;
            var url = kind switch
            {
                "action" => $"{baseUrl}/assistant/logs/action?limit=500",
                "proactive" => $"{baseUrl}/assistant/logs/proactive?limit=500",
                "files" => $"{baseUrl}/assistant/logs/files",
                _ => $"{baseUrl}/assistant/logs/system?limit=500",
            };

            if (kind == "files")
            {
                var file = (FileNameBox.Text ?? "").Trim();
                if (!string.IsNullOrWhiteSpace(file))
                {
                    url = $"{baseUrl}/assistant/logs/files?path={Uri.EscapeDataString(file)}&tail=200";
                }
            }

            var json = await _http.GetStringAsync(url);
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;

            var sb = new StringBuilder();
            if (kind == "files")
            {
                if (root.TryGetProperty("files", out var files) && files.ValueKind == JsonValueKind.Array)
                {
                    foreach (var f in files.EnumerateArray())
                    {
                        var name = f.TryGetProperty("name", out var n) ? (n.GetString() ?? "") : "";
                        var size = f.TryGetProperty("size", out var s) ? s.GetInt64() : 0;
                        sb.AppendLine($"{name}\t{size} bytes");
                    }
                }
                else if (root.TryGetProperty("lines", out var lines) && lines.ValueKind == JsonValueKind.Array)
                {
                    foreach (var line in lines.EnumerateArray())
                    {
                        sb.AppendLine(line.GetString() ?? "");
                    }
                }
            }
            else if (root.TryGetProperty("logs", out var logs) && logs.ValueKind == JsonValueKind.Array)
            {
                foreach (var ev in logs.EnumerateArray())
                {
                    var ts = ev.TryGetProperty("ts", out var t) ? (t.GetString() ?? "") : "";
                    var level = ev.TryGetProperty("level", out var l) ? (l.GetString() ?? "") : "";
                    var msg = ev.TryGetProperty("message", out var m) ? (m.GetString() ?? "") : "";
                    var src = ev.TryGetProperty("source", out var s) ? (s.GetString() ?? "") : "";
                    sb.AppendLine($"{ts} [{level}] ({src}) {msg}");
                }
            }

            LogText.Text = sb.ToString();
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
    }
}

