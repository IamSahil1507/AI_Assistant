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

public sealed partial class BrowserSessionsPage : Page
{
    private const string BaseUrl = "http://127.0.0.1:8000";
    private readonly HttpClient _http = new();
    private readonly ObservableCollection<string> _files = new();

    public BrowserSessionsPage()
    {
        InitializeComponent();
        ArtifactsList.ItemsSource = _files;
        LoadButton.Click += async (_, _) => await LoadArtifactsAsync();
        OpenUrlButton.Click += async (_, _) => await OpenUrlAsync();
        ArtifactsList.SelectionChanged += async (_, _) => await PreviewSelectedAsync();
    }

    private async Task LoadArtifactsAsync()
    {
        ErrorBar.IsOpen = false;
        PreviewImage.Source = null;
        try
        {
            var taskId = (TaskIdBox.Text ?? "").Trim();
            if (string.IsNullOrWhiteSpace(taskId))
            {
                return;
            }
            var json = await _http.GetStringAsync($"{BaseUrl}/assistant/operator/artifacts?task_id={Uri.EscapeDataString(taskId)}&tail=80");
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            _files.Clear();
            if (root.TryGetProperty("files", out var files) && files.ValueKind == JsonValueKind.Array)
            {
                foreach (var f in files.EnumerateArray())
                {
                    var name = f.TryGetProperty("name", out var n) ? (n.GetString() ?? "") : "";
                    if (!string.IsNullOrWhiteSpace(name))
                    {
                        _files.Add(name);
                    }
                }
            }
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
    }

    private async Task OpenUrlAsync()
    {
        ErrorBar.IsOpen = false;
        try
        {
            var taskId = (TaskIdBox.Text ?? "").Trim();
            var url = (UrlBox.Text ?? "").Trim();
            if (string.IsNullOrWhiteSpace(taskId) || string.IsNullOrWhiteSpace(url))
            {
                return;
            }
            var resp = await _http.PostAsJsonAsync($"{BaseUrl}/assistant/operator/browser/open_url", new { task_id = taskId, url });
            var body = await resp.Content.ReadAsStringAsync();
            if (!resp.IsSuccessStatusCode)
            {
                throw new InvalidOperationException(body);
            }
            await LoadArtifactsAsync();
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
    }

    private async Task PreviewSelectedAsync()
    {
        try
        {
            if (ArtifactsList.SelectedItem is not string name)
            {
                return;
            }
            if (!name.EndsWith(".png", StringComparison.OrdinalIgnoreCase) &&
                !name.EndsWith(".jpg", StringComparison.OrdinalIgnoreCase) &&
                !name.EndsWith(".jpeg", StringComparison.OrdinalIgnoreCase))
            {
                PreviewImage.Source = null;
                return;
            }

            var taskId = (TaskIdBox.Text ?? "").Trim();
            if (string.IsNullOrWhiteSpace(taskId))
            {
                return;
            }

            var bytes = await _http.GetByteArrayAsync($"{BaseUrl}/assistant/operator/artifact/file?task_id={Uri.EscapeDataString(taskId)}&name={Uri.EscapeDataString(name)}");
            using var ms = new MemoryStream(bytes);
            var bmp = new BitmapImage();
            await bmp.SetSourceAsync(ms.AsRandomAccessStream());
            PreviewImage.Source = bmp;
        }
        catch
        {
            PreviewImage.Source = null;
        }
    }
}

