using System;
using System.IO;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using NEXUS.ControlCenter.Services;

namespace NEXUS.ControlCenter;

public sealed partial class App : Application
{
    public static MainWindow? MainWindowInstance { get; private set; }
    public static NexusShellCoordinator? ShellCoordinator { get; private set; }

    public App()
    {
        InitializeComponent();
        UnhandledException += App_UnhandledException;
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        var settingsService = new SettingsService();
        var backendService = new BackendService();
        ShellCoordinator = new NexusShellCoordinator(settingsService, backendService);

        MainWindowInstance = new MainWindow(ShellCoordinator);
        MainWindowInstance.Activate();
    }

    private async void App_UnhandledException(object sender, Microsoft.UI.Xaml.UnhandledExceptionEventArgs e)
    {
        e.Handled = true;

        try
        {
            try
            {
                var root = AppContext.BaseDirectory ?? "";
                var logPath = Path.Combine(root, "nexus-control-center-crash.log");
                var text = $"[{DateTimeOffset.Now:u}] {e.Exception}\n";
                File.AppendAllText(logPath, text);
            }
            catch
            {
            }

            var xamlRoot = (MainWindowInstance?.Content as FrameworkElement)?.XamlRoot;
            var dialog = new ContentDialog
            {
                Title = "NEXUS Mission Control recovered from a crash",
                Content = e.Exception?.ToString() ?? "Unknown error",
                CloseButtonText = "Close",
                DefaultButton = ContentDialogButton.Close,
                XamlRoot = xamlRoot,
            };

            await dialog.ShowAsync();
        }
        catch
        {
        }
    }
}
