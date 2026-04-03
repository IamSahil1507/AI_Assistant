"""
NEXUS Configuration — Calibrated to HP Victus 16
i5-11400H · 16 GB RAM · GTX 1650 4 GB VRAM
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────
# Hardware Constants (YOUR machine)
# ──────────────────────────────────────────────

TOTAL_RAM_GB = 16
GPU_VRAM_GB = 4.0
CPU_CORES = 6
CPU_THREADS = 12

# ──────────────────────────────────────────────
# Model Registry — Your Ollama Models
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class ModelSpec:
    name: str
    size_gb: float
    fits_gpu: bool          # True if fits entirely in 4GB VRAM
    role: str               # fast | think | see | code
    speed: str              # fast | medium | slow
    max_context: int = 8192
    supports_vision: bool = False
    supports_tools: bool = True


MODELS: Dict[str, ModelSpec] = {
    "phi3": ModelSpec(
        name="phi3:latest", size_gb=2.2, fits_gpu=True,
        role="fast", speed="fast", max_context=4096,
    ),
    "llama3.2": ModelSpec(
        name="llama3.2:3b", size_gb=2.0, fits_gpu=True,
        role="fast", speed="fast", max_context=8192,
    ),
    "qwen3.5": ModelSpec(
        name="qwen3.5:latest", size_gb=6.6, fits_gpu=False,
        role="think", speed="medium", max_context=32768,
    ),
    "deepseek-r1": ModelSpec(
        name="deepseek-r1:latest", size_gb=5.2, fits_gpu=False,
        role="think", speed="medium", max_context=16384,
    ),
    "llama3.2-vision": ModelSpec(
        name="llama3.2-vision:latest", size_gb=7.8, fits_gpu=False,
        role="see", speed="slow", max_context=8192,
        supports_vision=True, supports_tools=False,
    ),
    "gpt-oss": ModelSpec(
        name="gpt-oss:20b", size_gb=13.0, fits_gpu=False,
        role="code", speed="slow", max_context=8192,
    ),
    "qwen3-coder": ModelSpec(
        name="qwen3-coder:30b", size_gb=18.0, fits_gpu=False,
        role="code", speed="slow", max_context=32768,
    ),
}

# ──────────────────────────────────────────────
# Three-Brain Strategy
# ──────────────────────────────────────────────

FAST_BRAIN = "phi3"             # ~1-2s, fits fully in GPU
THINK_BRAIN = "qwen3.5"        # ~5-10s, GPU+RAM split
DEEP_BRAIN = "deepseek-r1"     # ~10-15s, for complex debug/planning
VISION_BRAIN = "llama3.2-vision"  # ~15-30s, mostly RAM

# Fallback chain: if primary fails, try next
BRAIN_FALLBACK_CHAIN = {
    "fast": ["phi3", "llama3.2"],
    "think": ["qwen3.5", "deepseek-r1"],
    "see": ["llama3.2-vision"],
    "code": ["qwen3.5", "deepseek-r1", "gpt-oss"],
}


# ──────────────────────────────────────────────
# Safety Constants (HARDCODED — NEVER configurable)
# ──────────────────────────────────────────────

KILL_SWITCH_HOTKEY = "ctrl+shift+f12"

PROTECTED_ZONES: List[str] = [
    r"C:\Windows\System32",
    r"C:\Windows\SysWOW64",
    r"C:\Windows\security",
    r"C:\Program Files\Windows Defender",
    r"C:\ProgramData\Microsoft\Windows Defender",
    r"C:\Users\Sahil\.ssh",
    r"C:\Users\Sahil\AppData\Local\1Password",
    r"C:\Users\Sahil\AppData\Local\KeePass",
    r"C:\Users\Sahil\AppData\Roaming\KeePass",
    # Windows Registry paths
    "HKEY_LOCAL_MACHINE",
    "HKEY_CURRENT_USER\\Software\\Microsoft\\Windows",
    # Banking / sensitive app data dirs
    r"C:\Users\Sahil\AppData\Local\Google\Chrome\User Data\Default\Login Data",
    r"C:\Users\Sahil\AppData\Local\Microsoft\Edge\User Data\Default\Login Data",
]

PROTECTED_COMMANDS: List[str] = [
    "format",
    "diskpart",
    "bcdedit",
    "reg delete",
    "net user",
    "netsh advfirewall",
    "schtasks /delete",
    "cipher /w",
    "takeown",
    "icacls",
]

# ──────────────────────────────────────────────
# Permission Tiers (Claude Code inspired)
# ──────────────────────────────────────────────

class PermissionTier:
    READ = "read"           # Always allowed, never asks
    WRITE = "write"         # Confirm once per session
    DESTRUCTIVE = "destructive"  # Confirm EVERY time — always


# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────

@dataclass
class NexusPaths:
    root: Path = field(default_factory=lambda: Path(r"D:\PROJECTS\AI_ASSISTANT"))
    config: Path = field(default_factory=lambda: Path(r"D:\PROJECTS\AI_ASSISTANT\config"))
    data: Path = field(default_factory=lambda: Path(r"D:\PROJECTS\AI_ASSISTANT\data"))
    logs: Path = field(default_factory=lambda: Path(r"D:\PROJECTS\AI_ASSISTANT\logs"))
    memory: Path = field(default_factory=lambda: Path(r"D:\PROJECTS\AI_ASSISTANT\memory"))
    audit: Path = field(default_factory=lambda: Path(r"D:\PROJECTS\AI_ASSISTANT\logs\audit.log"))
    vector_db: Path = field(default_factory=lambda: Path(r"D:\PROJECTS\AI_ASSISTANT\memory\chroma_db"))
    skills_db: Path = field(default_factory=lambda: Path(r"D:\PROJECTS\AI_ASSISTANT\data\skills.db"))
    temp_frames: Path = field(default_factory=lambda: Path(r"D:\PROJECTS\AI_ASSISTANT\.tmp_video_frames"))

    def ensure_dirs(self) -> None:
        for p in [self.config, self.data, self.logs, self.memory, self.vector_db, self.temp_frames]:
            p.mkdir(parents=True, exist_ok=True)


PATHS = NexusPaths()


# ──────────────────────────────────────────────
# Ollama API
# ──────────────────────────────────────────────

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_PROXY_URL = "http://127.0.0.1:11435"


# ──────────────────────────────────────────────
# SI Layer Defaults
# ──────────────────────────────────────────────

SI_POLL_INTERVAL_SECONDS = 15
SI_RAM_CRITICAL_GB = 3.0
SI_RAM_WARNING_GB = 5.0
SI_CPU_HIGH_THRESHOLD = 85
SI_VRAM_CRITICAL_GB = 0.5
SI_LATE_NIGHT_START = 22  # 10 PM
SI_LATE_NIGHT_END = 6     # 6 AM
SI_MAX_RETRIES_BEFORE_CAUTION = 3


# ──────────────────────────────────────────────
# Research Defaults
# ──────────────────────────────────────────────

RESEARCH_MAX_SOURCES = 5
RESEARCH_TIMEOUT_SECONDS = 30
RESEARCH_MAX_CONTENT_CHARS = 50_000


# ──────────────────────────────────────────────
# Debug Engine Defaults
# ──────────────────────────────────────────────

DEBUG_MAX_FIX_ATTEMPTS = 5
DEBUG_ASK_TIMEOUT_SECONDS = 60
DEBUG_SANDBOX_ENABLED = True
DEBUG_ROLLBACK_ENABLED = True
