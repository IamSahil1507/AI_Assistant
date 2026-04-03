using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using NEXUS.ControlCenter.Models;

namespace NEXUS.ControlCenter.Services;

public sealed class NexusShellCoordinator
{
    private readonly SettingsService _settingsService;
    private readonly BackendService _backendService;

    public NexusSettings Settings { get; private set; } = new();

    public NexusRuntimeSnapshot? CurrentSnapshot { get; private set; }

    public BackendService Backend => _backendService;

    public NexusShellCoordinator(SettingsService settingsService, BackendService backendService)
    {
        _settingsService = settingsService;
        _backendService = backendService;
    }

    public async Task<NexusRuntimeSnapshot> InitializeAsync()
    {
        Settings = await _settingsService.LoadAsync();
        await ConnectAsync();
        return RefreshSnapshot();
    }

    public async Task<NexusRuntimeSnapshot> RefreshAsync()
    {
        await ConnectAsync();
        return RefreshSnapshot();
    }

    public async Task<IReadOnlyList<ChatThreadSummary>> LoadChatsAsync(int limit = 40)
    {
        return await _backendService.GetChatThreadsAsync(limit);
    }

    public async Task<IReadOnlyList<ChatMessageSummary>> LoadChatHistoryAsync(string chatId, int limit = 80)
    {
        return await _backendService.GetChatHistoryAsync(chatId, limit);
    }

    public async Task<ChatSendResult> SendChatAsync(string chatId, string message)
    {
        return await _backendService.SendChatAsync(chatId, message);
    }

    public async Task<NexusRuntimeSnapshot> SaveSettingsAsync(NexusSettings settings)
    {
        Settings = settings ?? new NexusSettings();
        await _settingsService.SaveAsync(Settings);
        await ConnectAsync();
        return RefreshSnapshot();
    }

    private async Task ConnectAsync()
    {
        if (!string.IsNullOrWhiteSpace(Settings.PreferredBackendBaseUrl))
        {
            await _backendService.ConnectAsync(Settings.PreferredBackendBaseUrl);
        }
        else
        {
            await _backendService.AutoDiscoverAsync();
        }
    }

    private NexusRuntimeSnapshot RefreshSnapshot()
    {
        CurrentSnapshot = new NexusRuntimeSnapshot(Settings, _backendService.CreateConnectionState(), DateTimeOffset.Now);
        return CurrentSnapshot;
    }
}
