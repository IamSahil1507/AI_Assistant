using System;
using System.Collections.ObjectModel;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using NEXUS.ControlCenter.Models;
using NEXUS.ControlCenter.Services;

namespace NEXUS.ControlCenter.Pages;

public sealed partial class ApprovalsPage : Page
{
    private readonly NexusShellCoordinator _coordinator;
    private readonly ObservableCollection<ApprovalSummary> _pending = new();
    private readonly ObservableCollection<ApprovalSummary> _history = new();

    public ApprovalsPage(NexusShellCoordinator coordinator)
    {
        _coordinator = coordinator;
        InitializeComponent();
        PendingList.ItemsSource = _pending;
        HistoryList.ItemsSource = _history;
        _ = RefreshAsync();
    }

    public async Task RefreshAsync()
    {
        try
        {
            var state = await _coordinator.Backend.GetApprovalsAsync(includeHistory: true);

            _pending.Clear();
            foreach (var approval in state.Pending)
            {
                _pending.Add(approval);
            }

            _history.Clear();
            foreach (var approval in state.History)
            {
                _history.Add(approval);
            }

            StatusBar.Severity = _pending.Count > 0 ? InfoBarSeverity.Warning : InfoBarSeverity.Success;
            StatusBar.Title = _pending.Count > 0 ? "Pending approvals require attention" : "No pending approvals";
            StatusBar.Message = $"Pending: {_pending.Count} | History: {_history.Count}";
        }
        catch (Exception ex)
        {
            StatusBar.Severity = InfoBarSeverity.Error;
            StatusBar.Title = "Approvals load failed";
            StatusBar.Message = ex.Message;
        }
    }

    private async Task ResolveSelectedAsync(bool approved, bool continueExecution)
    {
        if (PendingList.SelectedItem is not ApprovalSummary selected)
        {
            return;
        }

        try
        {
            if (continueExecution)
            {
                var result = await _coordinator.Backend.ContinueApprovalAsync(selected.Id);
                SelectedApprovalText.Text = result;
            }
            else
            {
                var updated = await _coordinator.Backend.ResolveApprovalAsync(selected.Id, approved);
                SelectedApprovalText.Text = $"Approval {updated.Status}: {updated.Title}";
            }

            await RefreshAsync();
        }
        catch (Exception ex)
        {
            StatusBar.Severity = InfoBarSeverity.Error;
            StatusBar.Title = "Approval action failed";
            StatusBar.Message = ex.Message;
        }
    }

    private void PendingList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (PendingList.SelectedItem is ApprovalSummary selected)
        {
            SelectedApprovalText.Text = $"{selected.Title}\n{selected.Detail}\nRisk: {selected.Risk} | Tool: {selected.Tool}";
        }
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs e)
    {
        await RefreshAsync();
    }

    private async void ApproveButton_Click(object sender, RoutedEventArgs e)
    {
        await ResolveSelectedAsync(approved: true, continueExecution: false);
    }

    private async void RejectButton_Click(object sender, RoutedEventArgs e)
    {
        await ResolveSelectedAsync(approved: false, continueExecution: false);
    }

    private async void ContinueButton_Click(object sender, RoutedEventArgs e)
    {
        await ResolveSelectedAsync(approved: true, continueExecution: true);
    }
}
