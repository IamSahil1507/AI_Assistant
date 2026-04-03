"""
Lazy module loader to defer expensive imports until actually needed.
Reduces startup time and memory footprint significantly.
"""

import sys
import importlib
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Cache for lazily loaded modules
_module_cache: Dict[str, Any] = {}


class LazyModule:
    """Wrapper that defers module import until first access."""
    
    def __init__(self, module_name: str, fallback_error: bool = False):
        self.module_name = module_name
        self.fallback_error = fallback_error
        self._module = None
        self._error = None
    
    def _load(self):
        """Load the module on first access."""
        if self._module is not None or self._error is not None:
            return
        
        try:
            if self.module_name in sys.modules:
                self._module = sys.modules[self.module_name]
            else:
                self._module = importlib.import_module(self.module_name)
            logger.debug(f"Lazy loaded: {self.module_name}")
        except ImportError as e:
            self._error = e
            logger.warning(f"Failed to lazy load {self.module_name}: {e}")
            if self.fallback_error:
                raise
    
    def __getattr__(self, name: str) -> Any:
        if self._error:
            raise self._error
        self._load()
        if self._module is None:
            raise ImportError(f"Failed to load {self.module_name}")
        return getattr(self._module, name)
    
    def __call__(self, *args, **kwargs):
        self._load()
        if self._module is None:
            raise ImportError(f"Failed to load {self.module_name}")
        return self._module(*args, **kwargs)


def lazy_import(module_name: str, required: bool = False) -> LazyModule:
    """
    Lazy import wrapper. Module is loaded only when first accessed.
    
    Args:
        module_name: Full module path (e.g., "playwright.async_api")
        required: If True, raises ImportError on load failure. If False, returns stub.
    
    Returns:
        LazyModule that loads on first access
    """
    if module_name not in _module_cache:
        _module_cache[module_name] = LazyModule(module_name, fallback_error=required)
    return _module_cache[module_name]


def get_loaded_modules() -> Dict[str, str]:
    """
    Return a dict of all lazy modules and their load status.
    Useful for diagnostics.
    """
    status = {}
    for name, lazy_mod in _module_cache.items():
        if lazy_mod._error:
            status[name] = "ERROR"
        elif lazy_mod._module:
            status[name] = "LOADED"
        else:
            status[name] = "PENDING"
    return status


# Pre-define common lazy imports to avoid repeating this everywhere
PLAYWRIGHT = lazy_import("playwright.async_api", required=False)
PYAUTOGUI = lazy_import("pyautogui", required=False)
PYWINAUTO = lazy_import("pywinauto", required=False)
PYTTSX3 = lazy_import("pyttsx3", required=False)
VOSK = lazy_import("vosk", required=False)
SOUNDDEVICE = lazy_import("sounddevice", required=False)
NUMPY = lazy_import("numpy", required=False)
PYTESSERACT = lazy_import("pytesseract", required=False)
REQUEST_HTML = lazy_import("requests_html", required=False)
BEAUTIFUL_SOUP = lazy_import("bs4", required=False)
CHROMADB = lazy_import("chromadb", required=False)
