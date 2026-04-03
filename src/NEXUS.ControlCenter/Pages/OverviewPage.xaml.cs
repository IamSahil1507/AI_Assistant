using System;
using System.Collections.ObjectModel;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using NEXUS.ControlCenter.Models;
using NEXUS.ControlCenter.Services;

namespace NEXUS.ControlCenter.Pages;

public sealed partial class OverviewPage : Page
{
    private readonly NexusShellCoordinator _coordinator;
    private readonly ObservableCollection<string> _quickActions = new();

    public OverviewPage(NexusShellCoordinator coordinator)
    {
        _coordinator = coordinator;
        InitializeComponent();
        QuickActionsList.ItemsSource = _quickActions;
        _ = RefreshAsync();
    }

    public async Task RefreshAsync()
    {
        try
        {
            var snapshot = await _coordinator.RefreshAsync();
            ApplySnapshot(snapshot);
            var details = await _coordinator.Backend.GetOverviewDetailsAsync();
            PolicySummaryText.Text = details.PolicySummary;
            MemorySummaryText.Text = details.MemorySummary;
            GatewaySummaryText.Text = details.GatewaySummary;
        }
        catch (Exception ex)
        {
            StatusBar.Severity = InfoBarSeverity.Error;
            StatusBar.Title = "Backend refresh failed";
            StatusBar.Message = ex.Message;
            StatusBar.IsOpen = true;
        }
    }

    private void ApplySnapshot(NexusRuntimeSnapshot snapshot)
    {
        StatusBar.Severity = snapshot.Connection.IsConnected ? InfoBarSeverity.Success : InfoBarSeverity.Warning;
        StatusBar.Title = snapshot.Connection.IsConnected ? "Connected" : "Running in degraded mode";
        StatusBar.Message = snapshot.Connection.IsConnected
            ? "NEXUS is ready to use the assistant backend."
            : $"Backend unavailable: {snapshot.Connection.LastError}";
        StatusBar.IsOpen = true;

        ConnectionStateText.Text = $"State: {snapshot.Connection.StatusText}";
        BackendUrlText.Text = $"Backend: {snapshot.Connection.BaseUrl}";
        RefreshedAtText.Text = $"Refreshed: {snapshot.RefreshedAt:yyyy-MM-dd HH:mm:ss}";
        ProfileText.Text = $"Profile: {snapshot.Settings.ProfileName}";
        SurfaceText.Text = $"Surfaces: tray={snapshot.Settings.EnableTray}, orb={snapshot.Settings.EnableOrb}, mission={snapshot.Settings.EnableMissionControl}";
        OpenBehaviorText.Text = $"Open behavior: quick-panel={snapshot.Settings.OpenBehavior.ToggleQuickPanelWhenFocused}, minimize={snapshot.Settings.OpenBehavior.MinimizeToTrayOnRepeatedOpen}";

        _quickActions.Clear();
        foreach (var action in snapshot.Settings.QuickActions)
        {
            _quickActions.Add(action);
        }
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs e)
    {
        await RefreshAsync();
    }
}
