using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Awarenet.ControlCenter.Services;

namespace Awarenet.ControlCenter;

public sealed partial class MainWindow : Window
{
    private readonly ObservableCollection<ChatListVm> _chatList = new();
    private readonly ObservableCollection<ChatMessageVm> _messages = new();
    private readonly List<Dictionary<string, object>> _pendingAttachments = new();
    private readonly DispatcherQueue _dispatcher = DispatcherQueue.GetForCurrentThread();
    private string _chatId = "";

    public MainWindow()
    {
        InitializeComponent();

        // Bind collections
        ChatList.ItemsSource = _chatList;
        MessagesList.ItemsSource = _messages;

        // `Loaded` is a Page/FrameworkElement concept; Window doesn't expose it.
        // Start initialization immediately after XAML is loaded.
        _ = InitAsync();
    }

    private async Task InitAsync()
    {
        await ReconnectAsync();
        await LoadChatListAsync();
        NewChat();
    }

    private async Task ReconnectAsync()
    {
        var ok = await BackendClient.AutoDiscoverAsync();
        ConnectionStatusText.Text = ok
            ? $"Connected: {BackendClient.BaseUrl}"
            : $"Not connected: {BackendClient.LastError}";
    }

    private void NewChat()
    {
        _chatId = "";
        _messages.Clear();
        _pendingAttachments.Clear();
        InputBox.Text = "";
    }

    private async Task LoadChatListAsync()
    {
        try
        {
            using var doc = await BackendClient.GetJsonAsync("/assistant/chat/list?limit=200");
            _chatList.Clear();
            if (doc.RootElement.TryGetProperty("chats", out var chats) && chats.ValueKind == JsonValueKind.Array)
            {
                foreach (var c in chats.EnumerateArray())
                {
                    var id = c.TryGetProperty("chat_id", out var i) ? (i.GetString() ?? "") : "";
                    if (!string.IsNullOrWhiteSpace(id))
                    {
                        _chatList.Add(new ChatListVm(id));
                    }
                }
            }
        }
        catch
        {
            // ignore list load failure; UI will still work for a new chat
        }
    }

    private async Task LoadHistoryAsync(string chatId)
    {
        try
        {
            using var doc = await BackendClient.GetJsonAsync($"/assistant/chat/history?chat_id={Uri.EscapeDataString(chatId)}&limit=200");
            _messages.Clear();
            if (doc.RootElement.TryGetProperty("events", out var eventsEl) && eventsEl.ValueKind == JsonValueKind.Array)
            {
                foreach (var ev in eventsEl.EnumerateArray())
                {
                    var role = ev.TryGetProperty("role", out var r) ? (r.GetString() ?? "") : "";
                    var content = ev.TryGetProperty("content", out var c) ? (c.GetString() ?? "") : "";
                    if (!string.IsNullOrWhiteSpace(role))
                    {
                        _messages.Add(ChatMessageVm.From(role, content));
                    }
                }
            }
        }
        catch
        {
            // ignore history failures
        }
    }

    // ----- Event handlers wired from XAML -----

    private async void ReconnectButton_Click(object sender, RoutedEventArgs e) => await ReconnectAsync();

    private async void NewChatButton_Click(object sender, RoutedEventArgs e)
    {
        NewChat();
        await LoadChatListAsync();
    }

    private async void ChatList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (ChatList.SelectedItem is not ChatListVm vm || string.IsNullOrWhiteSpace(vm.ChatId))
        {
            return;
        }
        _chatId = vm.ChatId;
        _pendingAttachments.Clear();
        await LoadHistoryAsync(vm.ChatId);
    }

    private async void SendButton_Click(object sender, RoutedEventArgs e) => await SendAsync();

    private async void MicButton_Click(object sender, RoutedEventArgs e) => await VoiceListenAsync();

    private async void VoiceCmdButton_Click(object sender, RoutedEventArgs e) => await VoiceCommandAsync();

    private async void AttachButton_Click(object sender, RoutedEventArgs e) => await AttachAsync();

    private void ModeButton_Click(object sender, RoutedEventArgs e)
    {
        if (sender is not Button b || b.Tag is not string mode)
        {
            return;
        }
        ContextModeText.Text = mode switch
        {
            "operator" => "Operator",
            "voice" => "Voice",
            "desktop" => "Desktop",
            "browser" => "Browser",
            "logs" => "Logs",
            _ => "Chat",
        };
        // Future: swap contextual content based on mode.
    }

    // ----- Chat / voice logic -----

    private async Task SendAsync()
    {
        var text = (InputBox.Text ?? "").Trim();
        if (string.IsNullOrWhiteSpace(text))
        {
            return;
        }

        ErrorBar.IsOpen = false;
        InputBox.Text = "";
        _messages.Add(ChatMessageVm.From("user", text));

        try
        {
            // Operator-style command from chat
            if (text.StartsWith("/op ", StringComparison.OrdinalIgnoreCase))
            {
                var goal = text[4..].Trim();
                if (!string.IsNullOrWhiteSpace(goal))
                {
                    var resp = await BackendClient.PostJsonAsync("/assistant/operator/execute", new { goal, max_steps = 12 });
                    var body = await resp.Content.ReadAsStringAsync();
                    _messages.Add(ChatMessageVm.From("assistant", body));
                    return;
                }
            }

            // Streaming chat via SSE
            var assistantVm = new ChatMessageVm("assistant", "");
            _messages.Add(assistantVm);

            using var http = new HttpClient();
            var req = new HttpRequestMessage(HttpMethod.Post, $"{BackendClient.BaseUrl}/assistant/chat/send_stream");
            req.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("text/event-stream"));
            req.Content = JsonContent.Create(new
            {
                chat_id = string.IsNullOrWhiteSpace(_chatId) ? null : _chatId,
                model = "awarenet",
                message = text,
                attachments = _pendingAttachments,
            });

            using var resp2 = await http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead);
            if (!resp2.IsSuccessStatusCode)
            {
                var err = await resp2.Content.ReadAsStringAsync();
                throw new InvalidOperationException(err);
            }

            await using var stream = await resp2.Content.ReadAsStreamAsync();
            using var reader = new StreamReader(stream);
            while (!reader.EndOfStream)
            {
                var line = await reader.ReadLineAsync();
                if (line is null)
                {
                    break;
                }
                if (!line.StartsWith("data: ", StringComparison.Ordinal))
                {
                    continue;
                }
                var payload = line[6..].Trim();
                if (string.IsNullOrWhiteSpace(payload))
                {
                    continue;
                }
                using var doc = JsonDocument.Parse(payload);
                var root = doc.RootElement;
                var typ = root.TryGetProperty("type", out var te) ? (te.GetString() ?? "") : "";
                if (typ == "meta")
                {
                    var cid = root.TryGetProperty("chat_id", out var ce) ? (ce.GetString() ?? "") : "";
                    if (!string.IsNullOrWhiteSpace(cid))
                    {
                        _chatId = cid;
                    }
                    continue;
                }
                if (typ == "delta")
                {
                    var delta = root.TryGetProperty("delta", out var de) ? (de.GetString() ?? "") : "";
                    if (!string.IsNullOrEmpty(delta))
                    {
                        _dispatcher.TryEnqueue(() => { assistantVm.Append(delta); });
                    }
                }
                if (typ == "final")
                {
                    break;
                }
            }

            _pendingAttachments.Clear();
            await LoadChatListAsync();
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
    }

    private async Task VoiceListenAsync()
    {
        try
        {
            var resp = await BackendClient.PostJsonAsync("/assistant/voice/listen_once", new { });
            var json = await resp.Content.ReadAsStringAsync();
            if (!resp.IsSuccessStatusCode)
            {
                throw new InvalidOperationException(json);
            }
            using var doc = JsonDocument.Parse(json);
            var text = doc.RootElement.TryGetProperty("text", out var t) ? (t.GetString() ?? "") : "";
            if (!string.IsNullOrWhiteSpace(text))
            {
                InputBox.Text = text;
            }
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
    }

    private async Task VoiceCommandAsync()
    {
        try
        {
            var text = (InputBox.Text ?? "").Trim();
            if (string.IsNullOrWhiteSpace(text))
            {
                return;
            }
            var resp = await BackendClient.PostJsonAsync("/assistant/voice/command", new { text, max_steps = 12 });
            var body = await resp.Content.ReadAsStringAsync();
            if (!resp.IsSuccessStatusCode)
            {
                throw new InvalidOperationException(body);
            }
            _messages.Add(ChatMessageVm.From("assistant", body));
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
    }

    private async Task AttachAsync()
    {
        // For now: path typed as @C:\path\file.ext in the input box.
        var text = (InputBox.Text ?? "").Trim();
        if (!text.StartsWith("@", StringComparison.Ordinal))
        {
            return;
        }
        var path = text[1..].Trim().Trim('"');
        try
        {
            if (!File.Exists(path))
            {
                throw new FileNotFoundException("Attachment file not found", path);
            }

            using var content = new MultipartFormDataContent();
            content.Add(new StringContent(string.IsNullOrWhiteSpace(_chatId) ? "" : _chatId), "chat_id");
            content.Add(new StreamContent(File.OpenRead(path)), "upload", Path.GetFileName(path));

            var resp = await new HttpClient().PostAsync($"{BackendClient.BaseUrl}/assistant/chat/attachments", content);
            var json = await resp.Content.ReadAsStringAsync();
            if (!resp.IsSuccessStatusCode)
            {
                throw new InvalidOperationException(json);
            }
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            _chatId = root.TryGetProperty("chat_id", out var cid) ? (cid.GetString() ?? _chatId) : _chatId;
            if (root.TryGetProperty("attachment", out var att) && att.ValueKind == JsonValueKind.Object)
            {
                var id = att.TryGetProperty("id", out var i) ? (i.GetString() ?? "") : "";
                var name = att.TryGetProperty("name", out var n) ? (n.GetString() ?? "") : "";
                _pendingAttachments.Add(new Dictionary<string, object> { ["id"] = id, ["name"] = name });
                InputBox.Text = "";
                _messages.Add(ChatMessageVm.From("system", $"Attached: {name}"));
            }
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
    }

    // ----- VMs -----

    private sealed record ChatListVm(string ChatId);

    private sealed class ChatMessageVm : INotifyPropertyChanged
    {
        private string _content;

        public ChatMessageVm(string role, string content)
        {
            Role = role;
            _content = content;
            Align = role == "user" ? HorizontalAlignment.Right : HorizontalAlignment.Left;
        }

        public string Role { get; }
        public HorizontalAlignment Align { get; }

        public string Content
        {
            get => _content;
            private set
            {
                if (_content == value) return;
                _content = value;
                OnPropertyChanged();
            }
        }

        public void Append(string delta)
        {
            Content = Content + delta;
        }

        public static ChatMessageVm From(string role, string content) => new(role, content);

        public event PropertyChangedEventHandler? PropertyChanged;

        private void OnPropertyChanged([CallerMemberName] string? name = null)
        {
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
        }
    }
}

