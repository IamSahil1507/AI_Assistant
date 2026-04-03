using System;

namespace NEXUS.ControlCenter.Models;

public sealed record BackendConnectionState(
    string BaseUrl,
    bool IsConnected,
    string LastError,
    string StatusText);

public sealed record NexusRuntimeSnapshot(
    NexusSettings Settings,
    BackendConnectionState Connection,
    DateTimeOffset RefreshedAt);

public sealed record ChatThreadSummary(
    string ChatId,
    string Title,
    string Preview,
    string UpdatedLabel);

public sealed record ChatMessageSummary(
    string Role,
    string Content,
    string TimestampLabel);

public sealed record ChatSendResult(
    string ChatId,
    string Response);
