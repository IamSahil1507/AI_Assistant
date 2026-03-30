using System;
using System.Collections.ObjectModel;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.UI.Xaml.Controls;

namespace Awarenet.ControlCenter.Pages;

public sealed partial class LessonsPage : Page
{
    private const string BaseUrl = "http://127.0.0.1:8000";
    private readonly HttpClient _http = new();
    private readonly ObservableCollection<LessonVm> _items = new();

    public LessonsPage()
    {
        InitializeComponent();
        LessonsList.ItemsSource = _items;
        RefreshButton.Click += async (_, _) => await RefreshAsync();
        _ = RefreshAsync();
    }

    private async Task RefreshAsync()
    {
        ErrorBar.IsOpen = false;
        try
        {
            var tail = 50;
            _ = int.TryParse((TailBox.Text ?? "").Trim(), out tail);
            tail = Math.Clamp(tail, 1, 500);
            var json = await _http.GetStringAsync($"{BaseUrl}/assistant/lessons?tail={tail}");
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            if (!root.TryGetProperty("lessons", out var lessons) || lessons.ValueKind != JsonValueKind.Array)
            {
                return;
            }
            _items.Clear();
            foreach (var l in lessons.EnumerateArray())
            {
                var rc = l.TryGetProperty("root_cause", out var r) ? (r.GetString() ?? "") : "";
                var fix = l.TryGetProperty("fix", out var f) ? (f.GetString() ?? "") : "";
                var prev = l.TryGetProperty("prevention", out var p) ? (p.GetString() ?? "") : "";
                var title = string.IsNullOrWhiteSpace(rc) ? "Lesson" : rc;
                var detail = $"Fix: {fix}\nPrevention: {prev}".Trim();
                _items.Add(new LessonVm(title, detail));
            }
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
    }

    private sealed record LessonVm(string Title, string Detail);
}

