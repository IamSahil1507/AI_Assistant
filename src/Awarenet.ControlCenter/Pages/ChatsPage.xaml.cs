using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.IO;
using System.Net.Http;
using System.Net.Http.Json;
using System.Net.Http.Headers;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml;
using Awarenet.ControlCenter.Services;
using Microsoft.UI.Dispatching;

namespace Awarenet.ControlCenter.Pages;

public sealed partial class ChatsPage : Page
{
    private readonly ObservableCollection<ChatListVm> _chatList = new();
    private readonly ObservableCollection<ChatMessageVm> _messages = new();
    private string _chatId = "";
    private readonly List<Dictionary<string, object>> _pendingAttachments = new();
    private readonly DispatcherQueue _dispatcher = DispatcherQueue.GetForCurrentThread();

    public ChatsPage()
    {
        InitializeComponent();
        ChatList.ItemsSource = _chatList;
        MessagesList.ItemsSource = _messages;

        SendButton.Click += async (_, _) => await SendAsync();
        NewChatButton.Click += (_, _) => NewChat();
        RefreshChatsButton.Click += async (_, _) => await LoadChatListAsync();
        ReconnectButton.Click += async (_, _) => await ReconnectAsync();
        ChatList.SelectionChanged += async (_, _) => await OnChatSelectedAsync();

        MicButton.Click += async (_, _) => await VoiceListenAsync();
        VoiceCmdButton.Click += async (_, _) => await VoiceCommandAsync();
        AttachButton.Click += async (_, _) => await AttachAsync();

        Loaded += async (_, _) => await InitAsync();
    }

    private async Task InitAsync()
    {
        await ReconnectAsync();
        await LoadChatListAsync();
        NewChat();
    }

    private async Task ReconnectAsync()
    {
        ErrorBar.IsOpen = false;
        var ok = await BackendClient.AutoDiscoverAsync();
        ConnectionText.Text = ok
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
            // ignore
        }
    }

    private async Task OnChatSelectedAsync()
    {
        if (ChatList.SelectedItem is not ChatListVm vm || string.IsNullOrWhiteSpace(vm.ChatId))
        {
            return;
        }
        _chatId = vm.ChatId;
        _pendingAttachments.Clear();
        await LoadHistoryAsync(vm.ChatId);
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
        catch { }
    }

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
            // Operator commands inside chat (video-style)
            if (text.StartsWith("/op ", StringComparison.OrdinalIgnoreCase))
            {
                var goal = text.Substring(4).Trim();
                if (!string.IsNullOrWhiteSpace(goal))
                {
                    var resp = await BackendClient.PostJsonAsync("/assistant/operator/execute", new { goal, max_steps = 12 });
                    var body = await resp.Content.ReadAsStringAsync();
                    _messages.Add(ChatMessageVm.From("assistant", body));
                    return;
                }
            }

            // Streaming chat (SSE)
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
                var payload = line.Substring(6).Trim();
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
                        _dispatcher.TryEnqueue(() =>
                        {
                            assistantVm.Append(delta);
                        });
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
        // Lightweight attachment support: user provides file path for now (full picker next).
        // If they paste a path into the input starting with @, upload it.
        var text = (InputBox.Text ?? "").Trim();
        if (!text.StartsWith("@", StringComparison.Ordinal))
        {
            return;
        }
        var path = text.Substring(1).Trim().Trim('"');
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

