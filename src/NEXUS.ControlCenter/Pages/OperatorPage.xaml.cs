using System;
using System.Collections.ObjectModel;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using NEXUS.ControlCenter.Models;
using NEXUS.ControlCenter.Services;

namespace NEXUS.ControlCenter.Pages;

public sealed partial class OperatorPage : Page
{
    private readonly NexusShellCoordinator _coordinator;
    private readonly ObservableCollection<OperatorTaskSummary> _history = new();
    private readonly ObservableCollection<OperatorArtifactSummary> _artifacts = new();

    public OperatorPage(NexusShellCoordinator coordinator)
    {
        _coordinator = coordinator;
        InitializeComponent();
        HistoryList.ItemsSource = _history;
        ArtifactsList.ItemsSource = _artifacts;
        _ = RefreshAsync();
    }

    public async Task RefreshAsync()
    {
        ErrorBar.IsOpen = false;

        try
        {
            var state = await _coordinator.Backend.GetOperatorStateAsync(includeHistory: true);

            _history.Clear();
            foreach (var item in state.History)
            {
                _history.Add(item);
            }

            _artifacts.Clear();
            if (state.Active is null)
            {
                ActiveStatusText.Text = "No active task.";
                ActiveGoalText.Text = "The operator is idle.";
                ActiveTaskIdText.Text = "";
                ActiveArtifactsText.Text = "";
                ActiveObservationText.Text = "Start a task to populate the live operator panel.";
                return;
            }

            ActiveStatusText.Text = $"Active: {state.Active.Status}";
            ActiveGoalText.Text = state.Active.Goal;
            ActiveTaskIdText.Text = $"Task ID: {state.Active.TaskId}";
            ActiveArtifactsText.Text = $"Artifacts: {state.Active.ArtifactsDirectory}";
            ActiveObservationText.Text = state.Active.LastObservationSummary;

            var artifacts = await _coordinator.Backend.GetOperatorArtifactsAsync(state.Active.TaskId);
            foreach (var artifact in artifacts)
            {
                _artifacts.Add(artifact);
            }
        }
        catch (Exception ex)
        {
            ErrorBar.Message = ex.Message;
            ErrorBar.IsOpen = true;
        }
    }

    private async void StartTaskButton_Click(object sender, RoutedEventArgs e)
    {
        var goal = (GoalTextBox.Text ?? "").Trim();
        if (string.IsNullOrWhiteSpace(goal))
        {
            return;
        }

        try
        {
            ErrorBar.IsOpen = false;
            await _coordinator.Backend.StartOperatorTaskAsync(goal);
            GoalTextBox.Text = "";
            await RefreshAsync();
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
}
