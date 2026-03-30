using Microsoft.UI.Xaml;
using Awarenet.ControlCenter.Services;
using System;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI;
using System.IO;

namespace Awarenet.ControlCenter;

public sealed partial class App : Application
{
    public static Window? MainWindowInstance { get; private set; }

    public App()
    {
        InitializeComponent();
        UnhandledException += App_UnhandledException;
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        _ = BackendClient.AutoDiscoverAsync();
        MainWindowInstance = new MainWindow();
        MainWindowInstance.Activate();
    }

    private async void App_UnhandledException(object sender, Microsoft.UI.Xaml.UnhandledExceptionEventArgs e)
    {
        // Prevent silent app-close; show the error.
        e.Handled = true;
        try
        {
            // Write crash details to a simple log so we can debug issues that
            // happen before UI is fully ready or when dialogs fail.
            try
            {
                var root = AppContext.BaseDirectory ?? "";
                var logPath = Path.Combine(root, "awarenet-control-center-crash.log");
                var text = $"[{DateTimeOffset.Now:u}] {e.Exception}\n";
                File.AppendAllText(logPath, text);
            }
            catch
            {
                // Ignore logging failures – crash handler must never throw.
            }

            var xamlRoot = (MainWindowInstance?.Content as FrameworkElement)?.XamlRoot;
            var dlg = new ContentDialog
            {
                Title = "Awarenet Control Center crashed (handled)",
                Content = e.Exception?.ToString() ?? "Unknown error",
                CloseButtonText = "Close",
                DefaultButton = ContentDialogButton.Close,
                XamlRoot = xamlRoot,
            };
            await dlg.ShowAsync();
        }
        catch
        {
            // If dialog fails, let it crash normally next time.
        }
    }
}

