using System;
using Microsoft.UI.Xaml;
using Microsoft.Windows.ApplicationModel.DynamicDependency;

namespace NEXUS.ControlCenter;

public static class Program
{
    [STAThread]
    public static void Main(string[] args)
    {
        Bootstrap.Initialize(0x00010008);

        try
        {
            Application.Start(_ => new App());
        }
        finally
        {
            Bootstrap.Shutdown();
        }
    }
}
