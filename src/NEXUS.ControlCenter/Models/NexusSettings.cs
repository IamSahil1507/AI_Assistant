using System.Collections.Generic;

namespace NEXUS.ControlCenter.Models;

public sealed class NexusSettings
{
    public string ProfileName { get; set; } = "Ambient Assistant";

    public string PreferredBackendBaseUrl { get; set; } = "";

    public bool EnableTray { get; set; } = true;

    public bool EnableOrb { get; set; } = true;

    public bool EnableMissionControl { get; set; } = true;

    public bool EnablePopups { get; set; } = true;

    public OpenBehaviorSettings OpenBehavior { get; set; } = new();

    public ThemeSettings Theme { get; set; } = new();

    public List<string> QuickActions { get; set; } =
    [
        "Open",
        "Voice Command",
        "Statistics",
        "Report",
        "Shortcuts",
        "Configurations",
        "Pop-ups",
        "Exit",
    ];
}

public sealed class OpenBehaviorSettings
{
    public bool ToggleQuickPanelWhenFocused { get; set; } = true;

    public bool MinimizeToTrayOnRepeatedOpen { get; set; } = true;
}

public sealed class ThemeSettings
{
    public double GlowStrength { get; set; } = 0.75;

    public double Transparency { get; set; } = 0.85;
}
