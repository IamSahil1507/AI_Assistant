"""
Server bootstrap module - handles lazy initialization of heavy components.
This defers loading of expensive modules until actually needed.
"""

import logging
from typing import Any, Dict, Optional, Callable
from functools import lru_cache

logger = logging.getLogger(__name__)

# Lazy component cache
_components: Dict[str, Any] = {}
_errors: Dict[str, Exception] = {}


class LazyProxy:
    """Proxy object that defers initialization of the real component."""
    
    def __init__(self, name: str, init_fn: Callable):
        self._name = name
        self._init_fn = init_fn
        self._instance = None
        self._initialized = False
    
    def _ensure_initialized(self):
        if self._initialized:
            return
        self._initialized = True
        try:
            logger.debug(f"Lazy-initializing {self._name}...")
            self._instance = self._init_fn()
            logger.debug(f"✓ {self._name} initialized")
        except Exception as e:
            logger.error(f"✗ Failed to initialize {self._name}: {e}")
            _errors[self._name] = e
            if self._instance is None:
                raise
    
    def __getattr__(self, name):
        self._ensure_initialized()
        if self._instance is None:
            raise RuntimeError(f"{self._name} failed to initialize")
        return getattr(self._instance, name)
    
    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            self._ensure_initialized()
            if self._instance is None:
                raise RuntimeError(f"{self._name} failed to initialize")
            setattr(self._instance, name, value)
    
    def __await__(self):
        self._ensure_initialized()
        if hasattr(self._instance, '__await__'):
            return self._instance.__await__()
        else:
            # Return a coroutine that returns self
            async def _coro():
                return self._instance
            return _coro().__await__()


def _safe_init(name: str, init_fn: Callable) -> Any:
    """
    Safely initialize a component, catching and logging errors.
    
    Args:
        name: Component name
        init_fn: Function that returns the initialized component
    
    Returns:
        Initialized component or None if initialization failed
    """
    if name in _components:
        return _components[name]
    
    if name in _errors:
        logger.error(f"Component {name} failed before: {_errors[name]}")
        return None
    
    try:
        logger.info(f"Initializing {name}...")
        result = init_fn()
        _components[name] = result
        logger.info(f"✓ {name} initialized")
        return result
    except Exception as e:
        _errors[name] = e
        logger.error(f"✗ Failed to initialize {name}: {e}")
        return None


def _init_bridge():
    from tools.openclaw_bridge import OpenClawBridge
    return OpenClawBridge()


def _init_operator():
    from tools.operator_controller import OperatorController
    bridge = bridge_proxy._instance if bridge_proxy._initialized else _init_bridge()
    return OperatorController(bridge)


def _init_skills_manager():
    from tools.skills_manager import SkillsManager
    bridge = bridge_proxy._instance if bridge_proxy._initialized else _init_bridge()
    return SkillsManager(lambda: bridge.config_manager.config)


def _init_proactive():
    from tools.proactive_engine import ProactiveEngine
    bridge = bridge_proxy._instance if bridge_proxy._initialized else _init_bridge()
    skills_mgr = skills_manager_proxy._instance if skills_manager_proxy._initialized else _init_skills_manager()
    return ProactiveEngine(
        lambda: bridge.config_manager.config,
        tick_callbacks=[skills_mgr.scheduled_tick] if skills_mgr else []
    )


# Create lazy proxies for all major components
bridge_proxy = LazyProxy("bridge", _init_bridge)
operator_proxy = LazyProxy("operator", _init_operator)
skills_manager_proxy = LazyProxy("skills_manager", _init_skills_manager)
proactive_proxy = LazyProxy("proactive", _init_proactive)


def get_bridge():
    """Get bridge component (lazy-loaded)."""
    return bridge_proxy


def get_operator():
    """Get operator component (lazy-loaded)."""
    return operator_proxy


def get_skills_manager():
    """Get skills_manager component (lazy-loaded)."""
    return skills_manager_proxy


def get_proactive():
    """Get proactive component (lazy-loaded)."""
    return proactive_proxy


def get_voice():
    """Lazy-load voice module."""
    def _init():
        from tools import voice
        return voice
    return _safe_init("voice", _init)


def get_recipes():
    """Lazy-load recipes."""
    def _init():
        from tools.operator_tools import recipes
        return recipes
    return _safe_init("recipes", _init)


def get_chat_store():
    """Lazy-load chat store."""
    def _init():
        from tools import chat_store
        return chat_store
    return _safe_init("chat_store", _init)


def get_assistant_state():
    """Lazy-load assistant_state."""
    def _init():
        from tools import assistant_state
        return assistant_state
    return _safe_init("assistant_state", _init)


def get_config_store():
    """Lazy-load config_store."""
    def _init():
        from tools import config_store
        return config_store
    return _safe_init("config_store", _init)


def get_all_components() -> Dict[str, Any]:
    """Get status of all initialized components."""
    return {
        "initialized": dict(_components),
        "errors": {k: str(v) for k, v in _errors.items()},
    }
