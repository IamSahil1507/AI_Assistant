using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Net.Http;
using System.Net.Http.Json;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Awarenet.ControlCenter.Pages;

public sealed partial class ModulesPage : Page
{
    private const string BaseUrl = "http://127.0.0.1:8000";
    private readonly HttpClient _http = new();
    private readonly ObservableCollection<ModuleVm> _modules = new();
    private bool _suppressUi;

    public ModulesPage()
    {
        InitializeComponent();
        BackendUrlText.Text = BaseUrl;
        ModulesList.ItemsSource = _modules;
        RefreshButton.Click += async (_, _) => await RefreshAsync();
        _ = RefreshAsync();
    }

    private async Task RefreshAsync()
    {
        ErrorBar.IsOpen = false;
        try
        {
            var capsJson = await _http.GetStringAsync($"{BaseUrl}/assistant/capabilities");
            var featuresJson = await _http.GetStringAsync($"{BaseUrl}/assistant/features");

            using var capsDoc = JsonDocument.Parse(capsJson);
            using var featDoc = JsonDocument.Parse(featuresJson);

            var modulesCaps = new Dictionary<string, (bool available, string reason)>(StringComparer.OrdinalIgnoreCase);
            if (capsDoc.RootElement.TryGetProperty("modules", out var m) && m.ValueKind == JsonValueKind.Object)
            {
                foreach (var prop in m.EnumerateObject())
                {
                    var available = prop.Value.TryGetProperty("available", out var a) && a.ValueKind == JsonValueKind.True;
                    if (prop.Value.TryGetProperty("available", out var a2) && a2.ValueKind == JsonValueKind.False)
                    {
                        available = false;
                    }
                    var reason = prop.Value.TryGetProperty("reason", out var r) ? (r.GetString() ?? "") : "";
                    modulesCaps[prop.Name] = (available, reason);
                }
            }

            var modulesFeat = new Dictionary<string, JsonElement>(StringComparer.OrdinalIgnoreCase);
            if (featDoc.RootElement.TryGetProperty("features", out var f) && f.ValueKind == JsonValueKind.Object)
            {
                foreach (var prop in f.EnumerateObject())
                {
                    modulesFeat[prop.Name] = prop.Value;
                }
            }

            _suppressUi = true;
            _modules.Clear();
            foreach (var key in modulesFeat.Keys)
            {
                modulesCaps.TryGetValue(key, out var cap);
                var fe = modulesFeat[key];
                var enabled = fe.TryGetProperty("enabled", out var en) && en.ValueKind == JsonValueKind.True;
                var mode = fe.TryGetProperty("mode", out var mo) ? (mo.GetString() ?? "off") : "off";
                var scope = fe.TryGetProperty("scope", out var sc) ? (sc.GetString() ?? "everything") : "everything";

                var status = cap.available ? "available" : "unavailable";
                var reason = cap.available ? "" : cap.reason;
                _modules.Add(new ModuleVm
                {
                    Key = key,
                    Name = key,
                    Enabled = enabled,
                    Mode = mode,
                    Scope = scope,
                    StatusText = string.IsNullOrWhiteSpace(reason) ? status : $"{status} — {reason}",
                });
            }
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
        finally
        {
            _suppressUi = false;
        }
    }

    private async Task UpdateFeatureAsync(string key, object patch)
    {
        ErrorBar.IsOpen = false;
        try
        {
            var body = new Dictionary<string, object> { [key] = patch };
            var resp = await _http.PostAsJsonAsync($"{BaseUrl}/assistant/features", body);
            var text = await resp.Content.ReadAsStringAsync();
            if (!resp.IsSuccessStatusCode)
            {
                throw new InvalidOperationException(text);
            }
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
    }

    private async void Enabled_Toggled(object sender, RoutedEventArgs e)
    {
        if (_suppressUi || sender is not ToggleSwitch t || t.Tag is not string key)
        {
            return;
        }
        await UpdateFeatureAsync(key, new { enabled = t.IsOn });
    }

    private async void Mode_Changed(object sender, SelectionChangedEventArgs e)
    {
        if (_suppressUi || sender is not ComboBox cb || cb.Tag is not string key)
        {
            return;
        }
        var value = (cb.SelectedItem as ComboBoxItem)?.Content?.ToString() ?? cb.SelectedItem?.ToString() ?? "";
        if (string.IsNullOrWhiteSpace(value))
        {
            return;
        }
        await UpdateFeatureAsync(key, new { mode = value });
    }

    private async void Scope_Changed(object sender, SelectionChangedEventArgs e)
    {
        if (_suppressUi || sender is not ComboBox cb || cb.Tag is not string key)
        {
            return;
        }
        var value = (cb.SelectedItem as ComboBoxItem)?.Content?.ToString() ?? cb.SelectedItem?.ToString() ?? "";
        if (string.IsNullOrWhiteSpace(value))
        {
            return;
        }
        await UpdateFeatureAsync(key, new { scope = value });
    }

    public sealed class ModuleVm : INotifyPropertyChanged
    {
        private bool _enabled;
        private string _mode = "off";
        private string _scope = "everything";
        private string _statusText = "";

        public string Key { get; set; } = "";
        public string Name { get; set; } = "";

        public bool Enabled
        {
            get => _enabled;
            set
            {
                if (_enabled == value) return;
                _enabled = value;
                OnPropertyChanged();
            }
        }

        public string Mode
        {
            get => _mode;
            set
            {
                if (_mode == value) return;
                _mode = value;
                OnPropertyChanged();
            }
        }

        public string Scope
        {
            get => _scope;
            set
            {
                if (_scope == value) return;
                _scope = value;
                OnPropertyChanged();
            }
        }

        public string StatusText
        {
            get => _statusText;
            set
            {
                if (_statusText == value) return;
                _statusText = value;
                OnPropertyChanged();
            }
        }

        public event PropertyChangedEventHandler? PropertyChanged;

        private void OnPropertyChanged([CallerMemberName] string? name = null)
        {
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
        }
    }
}

