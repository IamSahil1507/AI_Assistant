using System;
using System.Collections.ObjectModel;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Awarenet.ControlCenter.Pages;

public sealed partial class ApprovalsPage : Page
{
    private readonly HttpClient _http = new();
    private readonly ObservableCollection<ApprovalVm> _items = new();

    public ApprovalsPage()
    {
        InitializeComponent();
        ApprovalsList.ItemsSource = _items;
        RefreshButton.Click += async (_, _) => await RefreshAsync();
        _ = RefreshAsync();
    }

    private async Task RefreshAsync()
    {
        ErrorBar.IsOpen = false;
        try
        {
            var include = IncludeHistoryCheck.IsChecked == true;
            var url = $"http://127.0.0.1:8000/assistant/approvals?include_history={(include ? "true" : "false")}";
            var json = await _http.GetStringAsync(url);
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            if (!root.TryGetProperty("approvals", out var approvals))
            {
                return;
            }

            _items.Clear();
            if (approvals.TryGetProperty("pending", out var pending) && pending.ValueKind == JsonValueKind.Array)
            {
                foreach (var a in pending.EnumerateArray())
                {
                    _items.Add(ToVm(a, pending: true));
                }
            }
            if (include && approvals.TryGetProperty("history", out var hist) && hist.ValueKind == JsonValueKind.Array)
            {
                foreach (var a in hist.EnumerateArray())
                {
                    _items.Add(ToVm(a, pending: false));
                }
            }
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
    }

    private static ApprovalVm ToVm(JsonElement a, bool pending)
    {
        var id = a.TryGetProperty("id", out var i) ? (i.GetString() ?? "") : "";
        var status = a.TryGetProperty("status", out var s) ? (s.GetString() ?? "") : (pending ? "pending" : "");
        var title = a.TryGetProperty("title", out var t) ? (t.GetString() ?? "") : "Approval";
        var reason = a.TryGetProperty("reason", out var r) ? (r.GetString() ?? "") : "";
        var detail = a.TryGetProperty("detail", out var d) ? (d.GetString() ?? "") : "";
        var risk = a.TryGetProperty("risk", out var rk) ? (rk.GetString() ?? "") : "";
        var meta = $"{status} {risk}".Trim();
        return new ApprovalVm(id, $"{title} ({meta})", $"{reason}\n{detail}".Trim());
    }

    private async void Approve_Click(object sender, RoutedEventArgs e)
    {
        if (sender is not Button b || b.Tag is not string id || string.IsNullOrWhiteSpace(id))
        {
            return;
        }
        await ResolveAsync(id, approved: true, continueStep: false);
    }

    private async void ApproveContinue_Click(object sender, RoutedEventArgs e)
    {
        if (sender is not Button b || b.Tag is not string id || string.IsNullOrWhiteSpace(id))
        {
            return;
        }
        await ResolveAsync(id, approved: true, continueStep: true);
    }

    private async void Reject_Click(object sender, RoutedEventArgs e)
    {
        if (sender is not Button b || b.Tag is not string id || string.IsNullOrWhiteSpace(id))
        {
            return;
        }
        await ResolveAsync(id, approved: false, continueStep: false);
    }

    private async Task ResolveAsync(string id, bool approved, bool continueStep)
    {
        ErrorBar.IsOpen = false;
        try
        {
            if (continueStep && approved)
            {
                var resp = await _http.PostAsJsonAsync("http://127.0.0.1:8000/assistant/approvals/continue", new { id });
                resp.EnsureSuccessStatusCode();
            }
            else
            {
                var resp = await _http.PostAsJsonAsync("http://127.0.0.1:8000/assistant/approvals/resolve", new { id, approved });
                resp.EnsureSuccessStatusCode();
            }

            await RefreshAsync();
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
    }

    private sealed record ApprovalVm(string Id, string Title, string Detail);
}

