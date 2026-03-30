using System;
using System.Collections.ObjectModel;
using System.IO;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Imaging;

namespace Awarenet.ControlCenter.Pages;

public sealed partial class DesktopAutomationPage : Page
{
    private const string BaseUrl = "http://127.0.0.1:8000";
    private readonly HttpClient _http = new();
    private readonly ObservableCollection<string> _windows = new();

    public DesktopAutomationPage()
    {
        InitializeComponent();
        WindowsList.ItemsSource = _windows;
        ListButton.Click += async (_, _) => await ListAsync();
        ShotButton.Click += async (_, _) => await ScreenshotFullAsync();
        LaunchButton.Click += async (_, _) => await LaunchAsync();
    }

    private async Task ListAsync()
    {
        ErrorBar.IsOpen = false;
        try
        {
            var json = await _http.GetStringAsync($"{BaseUrl}/assistant/desktop/windows");
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            _windows.Clear();
            if (root.TryGetProperty("result", out var r) && r.ValueKind == JsonValueKind.Object &&
                r.TryGetProperty("windows", out var ws) && ws.ValueKind == JsonValueKind.Array)
            {
                foreach (var w in ws.EnumerateArray())
                {
                    _windows.Add(w.GetString() ?? "");
                }
            }
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
    }

    private async Task LaunchAsync()
    {
        ErrorBar.IsOpen = false;
        try
        {
            var cmd = (LaunchBox.Text ?? "").Trim();
            if (string.IsNullOrWhiteSpace(cmd))
            {
                return;
            }
            var resp = await _http.PostAsJsonAsync($"{BaseUrl}/assistant/desktop/launch", new { command = cmd });
            resp.EnsureSuccessStatusCode();
            await ListAsync();
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
    }

    private async Task ScreenshotFullAsync()
    {
        ErrorBar.IsOpen = false;
        try
        {
            var resp = await _http.PostAsJsonAsync($"{BaseUrl}/assistant/desktop/screenshot_full", new { });
            var body = await resp.Content.ReadAsStringAsync();
            if (!resp.IsSuccessStatusCode)
            {
                throw new InvalidOperationException(body);
            }

            // Result returns a path; for now we just show the returned json.
            // (We can add a safe file-serving endpoint for desktop artifacts next.)
            PreviewImage.Source = null;
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
    }
}

