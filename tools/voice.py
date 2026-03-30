from __future__ import annotations

import json
import time
import wave
from pathlib import Path
from typing import Any, Dict, Optional


class VoiceDependencyError(RuntimeError):
    pass


def _require_pyttsx3():
    try:
        import pyttsx3  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise VoiceDependencyError("pyttsx3 not installed (pip install pyttsx3)") from exc
    return pyttsx3


def _require_vosk():
    try:
        from vosk import KaldiRecognizer, Model  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise VoiceDependencyError("vosk not installed (pip install vosk)") from exc
    return KaldiRecognizer, Model


def _require_sounddevice():
    try:
        import sounddevice as sd  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise VoiceDependencyError("sounddevice not installed (pip install sounddevice)") from exc
    return sd


def speak(
    *,
    text: str,
    artifacts_dir: str | Path,
    rate: Optional[int] = None,
    voice_name_contains: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Offline TTS via Windows SAPI through pyttsx3.
    """
    if not text or not text.strip():
        return {"ok": False, "error": "missing_text"}
    out_dir = Path(artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pyttsx3 = _require_pyttsx3()
    engine = pyttsx3.init()
    if rate is not None:
        try:
            engine.setProperty("rate", int(rate))
        except Exception:
            pass
    if voice_name_contains:
        try:
            voices = engine.getProperty("voices") or []
            needle = voice_name_contains.lower()
            for v in voices:
                name = getattr(v, "name", "") or ""
                if needle in name.lower():
                    engine.setProperty("voice", getattr(v, "id", ""))
                    break
        except Exception:
            pass

    start = time.monotonic()
    engine.say(text)
    engine.runAndWait()
    duration_ms = int((time.monotonic() - start) * 1000)
    return {"ok": True, "duration_ms": duration_ms}


def listen_once(
    *,
    artifacts_dir: str | Path,
    vosk_model_path: str,
    seconds: int = 5,
    sample_rate: int = 16000,
) -> Dict[str, Any]:
    """
    Offline STT using Vosk model + microphone capture.

    Requires a downloaded Vosk model directory.
    """
    out_dir = Path(artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not vosk_model_path:
        return {"ok": False, "error": "missing_vosk_model_path"}
    model_dir = Path(vosk_model_path)
    if not model_dir.exists():
        return {"ok": False, "error": "vosk_model_not_found", "path": str(model_dir)}

    sd = _require_sounddevice()
    KaldiRecognizer, Model = _require_vosk()

    seconds = max(1, min(int(seconds), 30))
    sample_rate = int(sample_rate) if sample_rate else 16000

    start = time.monotonic()
    audio = sd.rec(int(seconds * sample_rate), samplerate=sample_rate, channels=1, dtype="int16")
    sd.wait()

    wav_path = out_dir / f"voice_{int(time.time())}.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())

    model = Model(str(model_dir))
    rec = KaldiRecognizer(model, sample_rate)
    rec.AcceptWaveform(audio.tobytes())
    result = rec.FinalResult()
    try:
        data = json.loads(result)
    except Exception:
        data = {"text": ""}
    text = str(data.get("text") or "").strip()
    duration_ms = int((time.monotonic() - start) * 1000)
    return {"ok": True, "text": text, "duration_ms": duration_ms, "wav_path": str(wav_path)}

