using System;
using Microsoft.UI.Xaml;
using Microsoft.Windows.ApplicationModel.DynamicDependency;

namespace Awarenet.ControlCenter;

public static class Program
{
    [STAThread]
    public static void Main(string[] args)
    {
        // Required for unpackaged WinUI 3 apps so the Windows App SDK runtime is initialized.
        // If the runtime is not present, this will throw with a helpful error.
        Bootstrap.Initialize(0x00010008); // Windows App SDK 1.8

        try
        {
            Application.Start(_ => { new App(); });
        }
        finally
        {
            Bootstrap.Shutdown();
        }
    }
}

