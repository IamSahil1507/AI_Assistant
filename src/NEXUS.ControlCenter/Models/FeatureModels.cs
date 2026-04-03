using System;
using System.Collections.Generic;

namespace NEXUS.ControlCenter.Models;

public sealed record AssistantOverviewDetails(
    string PolicySummary,
    string MemorySummary,
    string GatewaySummary);

public sealed record OperatorTaskSummary(
    string TaskId,
    string Goal,
    string Status,
    string StartedLabel,
    string ArtifactsDirectory,
    string LastObservationSummary);

public sealed record OperatorStateSnapshot(
    OperatorTaskSummary? Active,
    IReadOnlyList<OperatorTaskSummary> History);

public sealed record OperatorArtifactSummary(
    string Name,
    string Path,
    string UpdatedLabel,
    string SizeLabel);

public sealed record ApprovalSummary(
    string Id,
    string Title,
    string Detail,
    string Status,
    string Risk,
    string Tool,
    string TimestampLabel);

public sealed record ApprovalStateSnapshot(
    IReadOnlyList<ApprovalSummary> Pending,
    IReadOnlyList<ApprovalSummary> History);

public sealed record DesktopWindowSummary(
    string Title,
    string ClassName,
    string HandleLabel);

public sealed record DesktopActionResult(
    bool Ok,
    string Summary,
    string Detail,
    string ArtifactPath);

public sealed record VoiceActionResult(
    bool Ok,
    string Summary,
    string Detail,
    string ArtifactPath);

public sealed record BrowserActionSummary(
    bool Ok,
    string TaskId,
    string Summary,
    string Detail,
    string ArtifactPath);

public sealed record ModuleFeatureSummary(
    string Name,
    bool Available,
    string AvailabilityReason,
    bool Enabled,
    string Mode,
    string Scope);

public sealed record ConfigSnapshotSummary(
    string Id,
    string CreatedLabel,
    string Summary);

public sealed record BackendConfigSummary(
    string PrettyJson,
    IReadOnlyList<ConfigSnapshotSummary> Snapshots);
