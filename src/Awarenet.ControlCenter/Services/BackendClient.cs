using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Awarenet.ControlCenter.Services;

public static class BackendClient
{
    private static readonly HttpClient Http = new()
    {
        Timeout = TimeSpan.FromMilliseconds(900),
    };
    private static readonly int[] CommonPorts = { 8000, 8001, 8002, 8003, 8004, 8005, 8006, 8010 };

    public static string BaseUrl { get; private set; } = "http://127.0.0.1:8000";
    public static bool IsConnected { get; private set; }
    public static string LastError { get; private set; } = "";

    public static async Task<bool> AutoDiscoverAsync()
    {
        foreach (var port in CommonPorts)
        {
            var url = $"http://127.0.0.1:{port}";
            if (await ProbeAsync(url))
            {
                BaseUrl = url;
                IsConnected = true;
                LastError = "";
                return true;
            }
        }

        IsConnected = false;
        if (string.IsNullOrWhiteSpace(LastError))
        {
            LastError = "Backend not reachable on common ports.";
        }
        return false;
    }

    public static async Task<bool> ProbeAsync(string baseUrl)
    {
        try
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromMilliseconds(900));
            using var resp = await Http.GetAsync($"{baseUrl}/assistant/health", cts.Token);
            if (!resp.IsSuccessStatusCode)
            {
                LastError = $"health_http_{(int)resp.StatusCode}";
                return false;
            }
            IsConnected = true;
            LastError = "";
            return true;
        }
        catch (Exception ex)
        {
            LastError = ex.Message;
            return false;
        }
    }

    public static Task<string> GetStringAsync(string pathAndQuery)
    {
        return Http.GetStringAsync($"{BaseUrl}{pathAndQuery}");
    }

    public static Task<byte[]> GetBytesAsync(string pathAndQuery)
    {
        return Http.GetByteArrayAsync($"{BaseUrl}{pathAndQuery}");
    }

    public static Task<HttpResponseMessage> PostJsonAsync(string path, object body)
    {
        return Http.PostAsJsonAsync($"{BaseUrl}{path}", body);
    }

    public static async Task<JsonDocument> GetJsonAsync(string pathAndQuery)
    {
        var json = await GetStringAsync(pathAndQuery);
        return JsonDocument.Parse(json);
    }
}

