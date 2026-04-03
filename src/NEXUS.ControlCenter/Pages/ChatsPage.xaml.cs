using System;
using System.Collections.ObjectModel;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using NEXUS.ControlCenter.Models;
using NEXUS.ControlCenter.Services;

namespace NEXUS.ControlCenter.Pages;

public sealed partial class ChatsPage : Page
{
    private readonly NexusShellCoordinator _coordinator;
    private readonly ObservableCollection<ChatThreadSummary> _threads = new();
    private readonly ObservableCollection<ChatMessageSummary> _messages = new();
    private string _currentChatId = "";

    public ChatsPage(NexusShellCoordinator coordinator)
    {
        _coordinator = coordinator;
        InitializeComponent();
        ThreadsList.ItemsSource = _threads;
        MessagesList.ItemsSource = _messages;
        _ = RefreshAsync();
    }

    public async Task RefreshAsync()
    {
        ErrorBar.IsOpen = false;
        try
        {
            var chats = await _coordinator.LoadChatsAsync();
            _threads.Clear();
            foreach (var chat in chats)
            {
                _threads.Add(chat);
            }

            if (_threads.Count > 0 && string.IsNullOrWhiteSpace(_currentChatId))
            {
                ThreadsList.SelectedIndex = 0;
            }
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
    }

    public async Task<bool> SendMessageAsync(string message)
    {
        var cleaned = (message ?? "").Trim();
        if (string.IsNullOrWhiteSpace(cleaned))
        {
            return false;
        }

        try
        {
            ErrorBar.IsOpen = false;
            _messages.Add(new ChatMessageSummary("user", cleaned, "now"));
            var result = await _coordinator.SendChatAsync(_currentChatId, cleaned);
            _currentChatId = result.ChatId;
            _messages.Add(new ChatMessageSummary("assistant", result.Response, "now"));
            ConversationHintText.Text = $"Active session: {_currentChatId}";
            await RefreshAsync();
            return true;
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
            return false;
        }
    }

    private async Task LoadHistoryAsync(string chatId)
    {
        try
        {
            var messages = await _coordinator.LoadChatHistoryAsync(chatId);
            _messages.Clear();
            foreach (var message in messages)
            {
                _messages.Add(message);
            }

            _currentChatId = chatId;
            ConversationHintText.Text = $"Active session: {chatId}";
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs e)
    {
        await RefreshAsync();
    }

    private void NewChatButton_Click(object sender, RoutedEventArgs e)
    {
        _currentChatId = "";
        _messages.Clear();
        ConversationHintText.Text = "A new session will be created when you send the next message.";
        ThreadsList.SelectedItem = null;
    }

    private async void ThreadsList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (ThreadsList.SelectedItem is ChatThreadSummary selected)
        {
            await LoadHistoryAsync(selected.ChatId);
        }
    }
}
