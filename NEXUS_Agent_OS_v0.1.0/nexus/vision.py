"""
NEXUS Layer 2: Vision — Eyes that see your screen
Screenshot capture + OCR + LLM vision understanding

Converts raw screen pixels into structured scene descriptions
the Brain can reason about.
"""

from __future__ import annotations

import base64
import io
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from nexus.config import PATHS

logger = logging.getLogger("nexus.vision")


# ──────────────────────────────────────────────
# Screenshot Capture
# ──────────────────────────────────────────────

def capture_screenshot(
    *,
    region: Optional[Tuple[int, int, int, int]] = None,
    save_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Capture a screenshot of the entire screen or a region.
    Returns: {"ok": bool, "image_base64": str, "path": str, "size": (w,h)}
    """
    try:
        import mss
        from PIL import Image
    except ImportError:
        # Fallback to PIL only
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab(bbox=region)
        except ImportError:
            return {"ok": False, "error": "Neither mss+PIL nor PIL.ImageGrab available"}
    else:
        with mss.mss() as sct:
            if region:
                monitor = {"top": region[1], "left": region[0],
                          "width": region[2] - region[0], "height": region[3] - region[1]}
            else:
                monitor = sct.monitors[0]  # Full screen
            raw = sct.grab(monitor)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    # Save to file if requested
    if save_path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(save_path), "PNG")

    # Convert to base64 for LLM vision
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return {
        "ok": True,
        "image_base64": img_base64,
        "path": str(save_path) if save_path else None,
        "size": img.size,
        "timestamp": time.time(),
    }


def capture_window(title_contains: str, *, save_path: Optional[Path] = None) -> Dict[str, Any]:
    """Capture a specific window by title."""
    try:
        import pywinauto
        from PIL import Image
    except ImportError:
        return {"ok": False, "error": "pywinauto not installed"}

    try:
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
        windows = desktop.windows()
        target = None
        for w in windows:
            if title_contains.lower() in w.window_text().lower():
                target = w
                break

        if not target:
            return {"ok": False, "error": f"Window '{title_contains}' not found"}

        rect = target.rectangle()
        region = (rect.left, rect.top, rect.right, rect.bottom)
        return capture_screenshot(region=region, save_path=save_path)
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ──────────────────────────────────────────────
# OCR — Text Extraction
# ──────────────────────────────────────────────

def extract_text_ocr(
    image_base64: Optional[str] = None,
    image_path: Optional[Path] = None,
    *,
    lang: str = "eng",
) -> Dict[str, Any]:
    """
    Extract text from screenshot via pytesseract OCR.
    Returns: {"ok": bool, "text": str, "blocks": list}
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return {"ok": False, "error": "pytesseract not installed (pip install pytesseract)"}

    try:
        if image_base64:
            import base64 as b64
            img_data = b64.b64decode(image_base64)
            img = Image.open(io.BytesIO(img_data))
        elif image_path:
            img = Image.open(str(image_path))
        else:
            return {"ok": False, "error": "No image provided"}

        # Full text extraction
        full_text = pytesseract.image_to_string(img, lang=lang)

        # Block-level data (with bounding boxes)
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, lang=lang)
        blocks = []
        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            if text:
                blocks.append({
                    "text": text,
                    "x": data["left"][i],
                    "y": data["top"][i],
                    "w": data["width"][i],
                    "h": data["height"][i],
                    "confidence": data["conf"][i],
                })

        return {
            "ok": True,
            "text": full_text.strip(),
            "blocks": blocks,
            "block_count": len(blocks),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ──────────────────────────────────────────────
# LLM Vision Understanding
# ──────────────────────────────────────────────

def understand_screen(
    image_base64: str,
    prompt: str = "Describe what you see on this screen. Identify UI elements, buttons, dialogs, error messages, and text fields.",
    *,
    brain: Optional[Any] = None,  # nexus.brain.Brain instance
) -> Dict[str, Any]:
    """
    Send a screenshot to llama3.2-vision for UI understanding.
    Returns structured scene description.
    """
    if not brain:
        return {"ok": False, "error": "Brain instance required for vision understanding"}

    try:
        response = brain.see(prompt, images=[image_base64])
        return {
            "ok": True,
            "description": response.content,
            "model_used": response.model_used,
            "duration_ms": response.duration_ms,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ──────────────────────────────────────────────
# Vision Pipeline — Full Perceive Step
# ──────────────────────────────────────────────

class VisionPipeline:
    """
    Complete vision pipeline for the agent loop's PERCEIVE step.
    
    1. Capture screenshot
    2. Extract text via OCR
    3. (Optional) Understand UI via vision LLM
    4. Return structured perception
    """

    def __init__(self, brain: Optional[Any] = None):
        self.brain = brain
        self._frame_dir = PATHS.temp_frames
        self._frame_dir.mkdir(parents=True, exist_ok=True)

    def perceive(
        self,
        *,
        use_ocr: bool = True,
        use_vision_llm: bool = False,
        vision_prompt: str = "Describe this screen. Identify any errors, dialogs, or important UI elements.",
        window_title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Full perception step — screenshot + OCR + optional LLM vision.
        """
        start = time.monotonic()

        # Step 1: Capture
        frame_path = self._frame_dir / f"frame_{int(time.time())}.png"
        if window_title:
            screenshot = capture_window(window_title, save_path=frame_path)
        else:
            screenshot = capture_screenshot(save_path=frame_path)

        if not screenshot.get("ok"):
            return {"ok": False, "error": screenshot.get("error"), "step": "capture"}

        result: Dict[str, Any] = {
            "ok": True,
            "screenshot": {
                "path": screenshot.get("path"),
                "size": screenshot.get("size"),
            },
            "timestamp": time.time(),
        }

        # Step 2: OCR
        if use_ocr:
            ocr_result = extract_text_ocr(image_base64=screenshot["image_base64"])
            result["ocr"] = {
                "text": ocr_result.get("text", ""),
                "block_count": ocr_result.get("block_count", 0),
                "ok": ocr_result.get("ok", False),
            }

        # Step 3: Vision LLM (only if requested — expensive)
        if use_vision_llm and self.brain:
            vision_result = understand_screen(
                screenshot["image_base64"],
                vision_prompt,
                brain=self.brain,
            )
            result["vision"] = {
                "description": vision_result.get("description", ""),
                "model_used": vision_result.get("model_used", ""),
                "ok": vision_result.get("ok", False),
            }

        result["duration_ms"] = int((time.monotonic() - start) * 1000)
        return result

    def detect_error(
        self,
        ocr_text: str = "",
        vision_description: str = "",
    ) -> Dict[str, Any]:
        """
        Detect if the current screen shows an error.
        Uses pattern matching on OCR text + optional LLM analysis.
        """
        error_patterns = [
            "error", "exception", "traceback", "failed", "fatal",
            "cannot", "unable to", "denied", "not found", "crash",
            "stopped working", "not responding", "syntax error",
            "modulenotfounderror", "importerror", "typeerror",
            "valueerror", "keyerror", "attributeerror",
            "connectionerror", "timeout", "refused",
        ]

        combined = (ocr_text + " " + vision_description).lower()
        detected_errors = [p for p in error_patterns if p in combined]

        if detected_errors:
            return {
                "has_error": True,
                "error_patterns": detected_errors,
                "raw_text": ocr_text[:2000],
            }
        return {"has_error": False, "error_patterns": [], "raw_text": ""}
