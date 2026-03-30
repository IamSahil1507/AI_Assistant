using System;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.UI.Xaml.Controls;

namespace Awarenet.ControlCenter.Pages;

public sealed partial class VoicePage : Page
{
    private const string BaseUrl = "http://127.0.0.1:8000";
    private readonly HttpClient _http = new();

    public VoicePage()
    {
        InitializeComponent();
        SpeakButton.Click += async (_, _) => await SpeakAsync();
        ListenButton.Click += async (_, _) => await ListenAsync();
    }

    private async Task SpeakAsync()
    {
        ErrorBar.IsOpen = false;
        try
        {
            var text = (SpeakBox.Text ?? "").Trim();
            if (string.IsNullOrWhiteSpace(text))
            {
                return;
            }
            var resp = await _http.PostAsJsonAsync($"{BaseUrl}/assistant/voice/speak", new { text });
            var body = await resp.Content.ReadAsStringAsync();
            if (!resp.IsSuccessStatusCode)
            {
                throw new InvalidOperationException(body);
            }
            ResultBox.Text = "Spoken.";
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
    }

    private async Task ListenAsync()
    {
        ErrorBar.IsOpen = false;
        try
        {
            var resp = await _http.PostAsJsonAsync($"{BaseUrl}/assistant/voice/listen_once", new { });
            var json = await resp.Content.ReadAsStringAsync();
            if (!resp.IsSuccessStatusCode)
            {
                throw new InvalidOperationException(json);
            }
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            var text = root.TryGetProperty("text", out var t) ? (t.GetString() ?? "") : "";
            ResultBox.Text = string.IsNullOrWhiteSpace(text) ? "(no speech recognized)" : text;
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
    }
}

