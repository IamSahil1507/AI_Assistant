using System;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using NEXUS.ControlCenter.Services;

namespace NEXUS.ControlCenter.Pages;

public sealed partial class BrowserPage : Page
{
    private readonly NexusShellCoordinator _coordinator;

    public BrowserPage(NexusShellCoordinator coordinator)
    {
        _coordinator = coordinator;
        InitializeComponent();
    }

    private async void OpenUrlButton_Click(object sender, RoutedEventArgs e)
    {
        var url = (UrlTextBox.Text ?? "").Trim();
        if (string.IsNullOrWhiteSpace(url))
        {
            return;
        }

        try
        {
            var result = await _coordinator.Backend.OpenBrowserUrlAsync(url);
            TaskIdText.Text = $"Task ID: {result.TaskId}";
            ResultSummaryText.Text = result.Summary;
            ResultDetailText.Text = result.Detail;
            ArtifactPathText.Text = string.IsNullOrWhiteSpace(result.ArtifactPath) ? "" : $"Artifact: {result.ArtifactPath}";
            StatusBar.Severity = result.Ok ? InfoBarSeverity.Success : InfoBarSeverity.Warning;
            StatusBar.Title = result.Ok ? "Browser action completed" : "Browser action reported a problem";
            StatusBar.Message = result.Detail;
        }
        catch (Exception ex)
        {
            StatusBar.Severity = InfoBarSeverity.Error;
            StatusBar.Title = "Open URL failed";
            StatusBar.Message = ex.Message;
        }
    }
}
