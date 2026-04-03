using System;
using System.IO;
using System.Text.Json;
using System.Threading.Tasks;
using NEXUS.ControlCenter.Models;

namespace NEXUS.ControlCenter.Services;

public sealed class SettingsService
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        PropertyNameCaseInsensitive = true,
    };

    public string SettingsPath { get; }

    public SettingsService()
    {
        var root = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "NEXUS",
            "ControlCenter");
        Directory.CreateDirectory(root);
        SettingsPath = Path.Combine(root, "settings.json");
    }

    public async Task<NexusSettings> LoadAsync()
    {
        if (!File.Exists(SettingsPath))
        {
            var defaults = new NexusSettings();
            await SaveAsync(defaults);
            return defaults;
        }

        try
        {
            await using var stream = File.OpenRead(SettingsPath);
            var settings = await JsonSerializer.DeserializeAsync<NexusSettings>(stream, JsonOptions);
            return settings ?? new NexusSettings();
        }
        catch
        {
            return new NexusSettings();
        }
    }

    public async Task SaveAsync(NexusSettings settings)
    {
        await using var stream = File.Create(SettingsPath);
        await JsonSerializer.SerializeAsync(stream, settings, JsonOptions);
    }
}
