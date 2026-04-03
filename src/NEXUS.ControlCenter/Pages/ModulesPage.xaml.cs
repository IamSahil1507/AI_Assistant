using System;
using System.Collections.ObjectModel;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using NEXUS.ControlCenter.Models;
using NEXUS.ControlCenter.Services;

namespace NEXUS.ControlCenter.Pages;

public sealed partial class ModulesPage : Page
{
    private readonly NexusShellCoordinator _coordinator;
    private readonly ObservableCollection<ModuleFeatureSummary> _modules = new();

    public ModulesPage(NexusShellCoordinator coordinator)
    {
        _coordinator = coordinator;
        InitializeComponent();
        ModulesList.ItemsSource = _modules;
        _ = RefreshAsync();
    }

    public async Task RefreshAsync()
    {
        try
        {
            var modules = await _coordinator.Backend.GetModuleFeaturesAsync();
            _modules.Clear();
            foreach (var module in modules)
            {
                _modules.Add(module);
            }

            StatusBar.Severity = InfoBarSeverity.Success;
            StatusBar.Title = "Modules loaded";
            StatusBar.Message = $"Visible modules: {_modules.Count}";
        }
        catch (Exception ex)
        {
            StatusBar.Severity = InfoBarSeverity.Error;
            StatusBar.Title = "Module load failed";
            StatusBar.Message = ex.Message;
        }
    }

    private void ModulesList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (ModulesList.SelectedItem is not ModuleFeatureSummary selected)
        {
            return;
        }

        SelectionTitleText.Text = selected.Name;
        AvailabilityText.Text = selected.Available
            ? "Capability check: available."
            : $"Capability check: unavailable. {selected.AvailabilityReason}";
        EnabledCheckBox.IsChecked = selected.Enabled;
        ModeTextBox.Text = selected.Mode;
        ScopeTextBox.Text = selected.Scope;
    }

    private async void SaveButton_Click(object sender, RoutedEventArgs e)
    {
        if (ModulesList.SelectedItem is not ModuleFeatureSummary selected)
        {
            return;
        }

        try
        {
            await _coordinator.Backend.UpdateModuleFeatureAsync(
                selected.Name,
                EnabledCheckBox.IsChecked == true,
                (ModeTextBox.Text ?? "").Trim(),
                (ScopeTextBox.Text ?? "").Trim());

            StatusBar.Severity = InfoBarSeverity.Success;
            StatusBar.Title = "Module updated";
            StatusBar.Message = $"{selected.Name} settings saved.";
            await RefreshAsync();
        }
        catch (Exception ex)
        {
            StatusBar.Severity = InfoBarSeverity.Error;
            StatusBar.Title = "Module update failed";
            StatusBar.Message = ex.Message;
        }
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs e)
    {
        await RefreshAsync();
    }
}
