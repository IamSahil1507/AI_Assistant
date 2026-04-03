using Microsoft.UI.Xaml.Controls;

namespace NEXUS.ControlCenter.Pages;

public sealed partial class FeaturePlaceholderPage : Page
{
    public FeaturePlaceholderPage(string title, string description)
    {
        InitializeComponent();
        EyebrowText.Text = $"NEXUS / {title.ToUpperInvariant()}";
        TitleText.Text = title;
        DescriptionText.Text = description;
    }
}
