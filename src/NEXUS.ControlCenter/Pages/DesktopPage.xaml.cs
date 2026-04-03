using System;
using System.Collections.ObjectModel;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using NEXUS.ControlCenter.Models;
using NEXUS.ControlCenter.Services;

namespace NEXUS.ControlCenter.Pages;

public sealed partial class DesktopPage : Page
{
    private readonly NexusShellCoordinator _coordinator;
    private readonly ObservableCollection<DesktopWindowSummary> _windows = new();

    public DesktopPage(NexusShellCoordinator coordinator)
    {
        _coordinator = coordinator;
        InitializeComponent();
        WindowsList.ItemsSource = _windows;
        _ = RefreshAsync();
    }

    public async Task RefreshAsync()
    {
        try
        {
            var windows = await _coordinator.Backend.GetDesktopWindowsAsync();
            _windows.Clear();
            foreach (var window in windows)
            {
                _windows.Add(window);
            }

            StatusBar.Severity = InfoBarSeverity.Success;
            StatusBar.Title = "Desktop bridge available";
            StatusBar.Message = $"Visible windows: {_windows.Count}";
        }
        catch (Exception ex)
        {
            StatusBar.Severity = InfoBarSeverity.Error;
            StatusBar.Title = "Desktop refresh failed";
            StatusBar.Message = ex.Message;
        }
    }

    private void ApplyResult(DesktopActionResult result)
    {
        ResultSummaryText.Text = result.Summary;
        ResultDetailText.Text = result.Detail;
        ArtifactPathText.Text = string.IsNullOrWhiteSpace(result.ArtifactPath) ? "" : $"Artifact: {result.ArtifactPath}";
        StatusBar.Severity = result.Ok ? InfoBarSeverity.Success : InfoBarSeverity.Warning;
        StatusBar.Title = result.Ok ? "Desktop action completed" : "Desktop action reported a problem";
        StatusBar.Message = result.Detail;
    }

    private async void LaunchButton_Click(object sender, RoutedEventArgs e)
    {
        var command = (LaunchCommandTextBox.Text ?? "").Trim();
        if (string.IsNullOrWhiteSpace(command))
        {
            return;
        }

        try
        {
            var result = await _coordinator.Backend.LaunchDesktopAppAsync(command);
            ApplyResult(result);
            await RefreshAsync();
        }
        catch (Exception ex)
        {
            StatusBar.Severity = InfoBarSeverity.Error;
            StatusBar.Title = "Launch failed";
            StatusBar.Message = ex.Message;
        }
    }

    private async void FullScreenshotButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var result = await _coordinator.Backend.ScreenshotDesktopFullAsync();
            ApplyResult(result);
        }
        catch (Exception ex)
        {
            StatusBar.Severity = InfoBarSeverity.Error;
            StatusBar.Title = "Screenshot failed";
            StatusBar.Message = ex.Message;
        }
    }

    private async void WindowScreenshotButton_Click(object sender, RoutedEventArgs e)
    {
        var title = (WindowTitleTextBox.Text ?? "").Trim();
        if (string.IsNullOrWhiteSpace(title))
        {
            return;
        }

        try
        {
            var result = await _coordinator.Backend.ScreenshotDesktopWindowAsync(title);
            ApplyResult(result);
        }
        catch (Exception ex)
        {
            StatusBar.Severity = InfoBarSeverity.Error;
            StatusBar.Title = "Window capture failed";
            StatusBar.Message = ex.Message;
        }
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs e)
    {
        await RefreshAsync();
    }
}
