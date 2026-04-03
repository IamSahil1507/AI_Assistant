using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using NEXUS.ControlCenter.Models;
using NEXUS.ControlCenter.Services;

namespace NEXUS.ControlCenter.Pages;

public sealed partial class ShellSettingsPage : Page
{
    private readonly NexusShellCoordinator _coordinator;
    private readonly ObservableCollection<ConfigSnapshotSummary> _snapshots = new();

    public ShellSettingsPage(NexusShellCoordinator coordinator)
    {
        _coordinator = coordinator;
        InitializeComponent();
        SnapshotsList.ItemsSource = _snapshots;
        PopulateFromSettings(_coordinator.Settings);
        _ = RefreshBackendConfigAsync();
    }

    private void PopulateFromSettings(NexusSettings settings)
    {
        ProfileNameTextBox.Text = settings.ProfileName;
        BackendUrlTextBox.Text = settings.PreferredBackendBaseUrl;
        EnableTrayCheckBox.IsChecked = settings.EnableTray;
        EnableOrbCheckBox.IsChecked = settings.EnableOrb;
        EnableMissionControlCheckBox.IsChecked = settings.EnableMissionControl;
        EnablePopupsCheckBox.IsChecked = settings.EnablePopups;
        ToggleQuickPanelCheckBox.IsChecked = settings.OpenBehavior.ToggleQuickPanelWhenFocused;
        MinimizeToTrayCheckBox.IsChecked = settings.OpenBehavior.MinimizeToTrayOnRepeatedOpen;
        GlowStrengthTextBox.Text = settings.Theme.GlowStrength.ToString("0.##");
        TransparencyTextBox.Text = settings.Theme.Transparency.ToString("0.##");
        QuickActionsTextBox.Text = string.Join(Environment.NewLine, settings.QuickActions);
    }

    private async Task RefreshBackendConfigAsync()
    {
        try
        {
            var config = await _coordinator.Backend.GetBackendConfigAsync();
            ConfigJsonTextBox.Text = config.PrettyJson;
            _snapshots.Clear();
            foreach (var snapshot in config.Snapshots)
            {
                _snapshots.Add(snapshot);
            }

            StatusBar.Severity = InfoBarSeverity.Success;
            StatusBar.Title = "Settings loaded";
            StatusBar.Message = $"Snapshots: {_snapshots.Count}";
        }
        catch (Exception ex)
        {
            StatusBar.Severity = InfoBarSeverity.Error;
            StatusBar.Title = "Config load failed";
            StatusBar.Message = ex.Message;
        }
    }

    private NexusSettings BuildSettingsFromForm()
    {
        var glow = 0.75;
        var transparency = 0.85;
        double.TryParse(GlowStrengthTextBox.Text, out glow);
        double.TryParse(TransparencyTextBox.Text, out transparency);

        var separators = new[] { ',', '\r', '\n' };
        var quickActions = (QuickActionsTextBox.Text ?? "")
            .Split(separators, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

        return new NexusSettings
        {
            ProfileName = (ProfileNameTextBox.Text ?? "").Trim(),
            PreferredBackendBaseUrl = (BackendUrlTextBox.Text ?? "").Trim(),
            EnableTray = EnableTrayCheckBox.IsChecked == true,
            EnableOrb = EnableOrbCheckBox.IsChecked == true,
            EnableMissionControl = EnableMissionControlCheckBox.IsChecked == true,
            EnablePopups = EnablePopupsCheckBox.IsChecked == true,
            OpenBehavior = new OpenBehaviorSettings
            {
                ToggleQuickPanelWhenFocused = ToggleQuickPanelCheckBox.IsChecked == true,
                MinimizeToTrayOnRepeatedOpen = MinimizeToTrayCheckBox.IsChecked == true,
            },
            Theme = new ThemeSettings
            {
                GlowStrength = glow,
                Transparency = transparency,
            },
            QuickActions = quickActions.Length > 0
                ? new List<string>(quickActions)
                : new List<string> { "Open", "Voice Command", "Statistics", "Report", "Shortcuts", "Configurations", "Pop-ups", "Exit" },
        };
    }

    private async void SaveButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var settings = BuildSettingsFromForm();
            await _coordinator.SaveSettingsAsync(settings);
            PopulateFromSettings(_coordinator.Settings);
            StatusBar.Severity = InfoBarSeverity.Success;
            StatusBar.Title = "Settings saved";
            StatusBar.Message = "Shell configuration updated and backend connection refreshed.";
        }
        catch (Exception ex)
        {
            StatusBar.Severity = InfoBarSeverity.Error;
            StatusBar.Title = "Save failed";
            StatusBar.Message = ex.Message;
        }
    }

    private async void ReloadConfigButton_Click(object sender, RoutedEventArgs e)
    {
        await RefreshBackendConfigAsync();
    }

    private async void SnapshotButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var snapshot = await _coordinator.Backend.CreateConfigSnapshotAsync();
            _snapshots.Insert(0, snapshot);
            StatusBar.Severity = InfoBarSeverity.Success;
            StatusBar.Title = "Snapshot created";
            StatusBar.Message = snapshot.CreatedLabel;
        }
        catch (Exception ex)
        {
            StatusBar.Severity = InfoBarSeverity.Error;
            StatusBar.Title = "Snapshot failed";
            StatusBar.Message = ex.Message;
        }
    }
}
