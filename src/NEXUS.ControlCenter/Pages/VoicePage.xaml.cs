using System;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using NEXUS.ControlCenter.Models;
using NEXUS.ControlCenter.Services;

namespace NEXUS.ControlCenter.Pages;

public sealed partial class VoicePage : Page
{
    private readonly NexusShellCoordinator _coordinator;

    public VoicePage(NexusShellCoordinator coordinator)
    {
        _coordinator = coordinator;
        InitializeComponent();
    }

    private void ApplyResult(VoiceActionResult result)
    {
        ResultSummaryText.Text = result.Summary;
        ResultDetailText.Text = result.Detail;
        ArtifactPathText.Text = string.IsNullOrWhiteSpace(result.ArtifactPath) ? "" : $"Artifact: {result.ArtifactPath}";
        StatusBar.Severity = result.Ok ? InfoBarSeverity.Success : InfoBarSeverity.Warning;
        StatusBar.Title = result.Ok ? "Voice action completed" : "Voice action reported a problem";
        StatusBar.Message = result.Detail;
    }

    private async void SpeakButton_Click(object sender, RoutedEventArgs e)
    {
        var text = (SpeakTextBox.Text ?? "").Trim();
        if (string.IsNullOrWhiteSpace(text))
        {
            return;
        }

        try
        {
            ApplyResult(await _coordinator.Backend.SpeakAsync(text));
        }
        catch (Exception ex)
        {
            StatusBar.Severity = InfoBarSeverity.Error;
            StatusBar.Title = "Speak failed";
            StatusBar.Message = ex.Message;
        }
    }

    private async void VoiceCommandButton_Click(object sender, RoutedEventArgs e)
    {
        var text = (CommandTextBox.Text ?? "").Trim();
        if (string.IsNullOrWhiteSpace(text))
        {
            return;
        }

        try
        {
            ApplyResult(await _coordinator.Backend.RunVoiceCommandAsync(text));
        }
        catch (Exception ex)
        {
            StatusBar.Severity = InfoBarSeverity.Error;
            StatusBar.Title = "Voice command failed";
            StatusBar.Message = ex.Message;
        }
    }

    private async void ListenOnceButton_Click(object sender, RoutedEventArgs e)
    {
        var seconds = 5;
        int.TryParse(ListenSecondsTextBox.Text, out seconds);
        seconds = Math.Max(1, seconds);

        try
        {
            ApplyResult(await _coordinator.Backend.ListenOnceAsync(seconds));
        }
        catch (Exception ex)
        {
            StatusBar.Severity = InfoBarSeverity.Error;
            StatusBar.Title = "Listen failed";
            StatusBar.Message = ex.Message;
        }
    }
}
