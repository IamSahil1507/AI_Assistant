using System.Collections.ObjectModel;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using NEXUS.ControlCenter.Models;
using NEXUS.ControlCenter.Pages;
using NEXUS.ControlCenter.Services;

namespace NEXUS.ControlCenter;

public sealed partial class MainWindow : Window
{
    private readonly NexusShellCoordinator _coordinator;
    private readonly ObservableCollection<string> _intelItems = new();
    private object? _currentPage;

    public MainWindow(NexusShellCoordinator coordinator)
    {
        _coordinator = coordinator;
        InitializeComponent();
        IntelList.ItemsSource = _intelItems;
        _ = InitializeAsync();
    }

    private async Task InitializeAsync()
    {
        var snapshot = await _coordinator.InitializeAsync();
        ApplySnapshot(snapshot);
        SelectInitialPage();
    }

    private void ApplySnapshot(NexusRuntimeSnapshot snapshot)
    {
        ConnectionStateText.Text = snapshot.Connection.StatusText;
        ProfileText.Text = snapshot.Settings.ProfileName;
        BackendText.Text = snapshot.Connection.BaseUrl;

        IntelSummaryText.Text = snapshot.Connection.IsConnected
            ? "Backend link established. Overview and Chats are live; the rest of the shell is scaffolded for parity work."
            : $"Backend unavailable. NEXUS is running in degraded mode: {snapshot.Connection.LastError}";

        _intelItems.Clear();
        _intelItems.Add($"Quick actions: {string.Join(" · ", snapshot.Settings.QuickActions)}");
        _intelItems.Add($"Surfaces: tray={snapshot.Settings.EnableTray}, orb={snapshot.Settings.EnableOrb}, mission={snapshot.Settings.EnableMissionControl}, popups={snapshot.Settings.EnablePopups}");
        _intelItems.Add($"Open behavior: quick-panel={snapshot.Settings.OpenBehavior.ToggleQuickPanelWhenFocused}, minimize={snapshot.Settings.OpenBehavior.MinimizeToTrayOnRepeatedOpen}");
    }

    private void SelectInitialPage()
    {
        if (ShellNav.MenuItems.Count > 0 && ShellNav.MenuItems[0] is NavigationViewItem item)
        {
            ShellNav.SelectedItem = item;
            NavigateTo((item.Tag as string) ?? "overview");
        }
    }

    private void NavigateTo(string tag)
    {
        _currentPage = tag switch
        {
            "overview" => new OverviewPage(_coordinator),
            "chats" => new ChatsPage(_coordinator),
            "operator" => new OperatorPage(_coordinator),
            "approvals" => new ApprovalsPage(_coordinator),
            "voice" => new VoicePage(_coordinator),
            "browser" => new BrowserPage(_coordinator),
            "desktop" => new DesktopPage(_coordinator),
            "modules" => new ModulesPage(_coordinator),
            "settings" => new FeaturePlaceholderPage("Settings", "Shell configuration is isolated behind one remaining WinUI issue and will be reintroduced next."),
            _ => new FeaturePlaceholderPage("NEXUS", "This section is scaffolded and ready for its dedicated implementation slice."),
        };

        MainContentHost.Content = _currentPage;
    }

    private async Task RefreshCurrentAsync()
    {
        var snapshot = await _coordinator.RefreshAsync();
        ApplySnapshot(snapshot);

        switch (_currentPage)
        {
            case OverviewPage overviewPage:
                await overviewPage.RefreshAsync();
                break;
            case ChatsPage chatsPage:
                await chatsPage.RefreshAsync();
                break;
            case OperatorPage operatorPage:
                await operatorPage.RefreshAsync();
                break;
            case ApprovalsPage approvalsPage:
                await approvalsPage.RefreshAsync();
                break;
            case DesktopPage desktopPage:
                await desktopPage.RefreshAsync();
                break;
            case ModulesPage modulesPage:
                await modulesPage.RefreshAsync();
                break;
        }
    }

    private async void ShellNav_SelectionChanged(NavigationView sender, NavigationViewSelectionChangedEventArgs args)
    {
        if (args.IsSettingsSelected)
        {
            NavigateTo("settings");
            return;
        }

        if (args.SelectedItemContainer?.Tag is string tag)
        {
            NavigateTo(tag);
        }

        await Task.CompletedTask;
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs e)
    {
        await RefreshCurrentAsync();
    }

    private void VoiceButton_Click(object sender, RoutedEventArgs e)
    {
        IntelSummaryText.Text = "Voice runtime is planned after the shell foundation. This button is reserved for the future wake and voice layer.";
    }

    private async void SendButton_Click(object sender, RoutedEventArgs e)
    {
        var text = (CommandInputBox.Text ?? "").Trim();
        if (string.IsNullOrWhiteSpace(text))
        {
            return;
        }

        if (_currentPage is ChatsPage chatsPage)
        {
            var sent = await chatsPage.SendMessageAsync(text);
            if (sent)
            {
                CommandInputBox.Text = "";
            }
            return;
        }

        IntelSummaryText.Text = "The command dock is active on the Chats screen first. Switch to Chats to send a live request.";
    }
}
