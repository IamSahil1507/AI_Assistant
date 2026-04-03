"""
Startup diagnostics and error isolation for API server.
Tracks module load times and catches silent failures.
"""

import sys
import time
import traceback
import logging
from typing import Any, Dict, Callable, Optional
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

class StartupTracker:
    """Track startup events, timings, and errors."""
    
    def __init__(self):
        self.start_time = time.time()
        self.events: list[Dict[str, Any]] = []
        self.errors: list[Dict[str, Any]] = []
        self.module_loads: Dict[str, float] = {}
    
    def log_event(self, name: str, duration_ms: float = 0, status: str = "ok"):
        """Log a startup event."""
        event = {
            "time": time.time() - self.start_time,
            "name": name,
            "duration_ms": duration_ms,
            "status": status,
        }
        self.events.append(event)
        logger.info(f"[STARTUP] {name} - {duration_ms:.0f}ms")
    
    def log_error(self, component: str, error: Exception, recoverable: bool = False):
        """Log a startup error."""
        err_info = {
            "time": time.time() - self.start_time,
            "component": component,
            "error": str(error),
            "type": type(error).__name__,
            "recoverable": recoverable,
            "traceback": traceback.format_exc(),
        }
        self.errors.append(err_info)
        level = logging.WARNING if recoverable else logging.ERROR
        logger.log(level, f"[STARTUP ERROR] {component}: {error}")
    
    def log_module_load(self, module_name: str, duration_ms: float):
        """Log individual module load time."""
        self.module_loads[module_name] = duration_ms
        if duration_ms > 100:
            logger.debug(f"[SLOW LOAD] {module_name}: {duration_ms:.0f}ms")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get startup summary."""
        total_time = time.time() - self.start_time
        return {
            "total_time_s": round(total_time, 2),
            "event_count": len(self.events),
            "error_count": len(self.errors),
            "critical_errors": len([e for e in self.errors if not e["recoverable"]]),
            "slow_modules": [
                (k, v) for k, v in sorted(
                    self.module_loads.items(), 
                    key=lambda x: x[1], 
                    reverse=True
                )[:5]
            ],
            "events": self.events,
            "errors": self.errors,
        }
    
    @contextmanager
    def measure(self, name: str):
        """Context manager to measure timing of a block."""
        start = time.time()
        try:
            yield
            duration_ms = (time.time() - start) * 1000
            self.log_event(name, duration_ms=duration_ms, status="ok")
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.log_error(name, e, recoverable=True)
            logger.error(f"Error in {name}: {e}")
            raise


# Global tracker instance
_tracker: Optional[StartupTracker] = None


def get_startup_tracker() -> StartupTracker:
    """Get or create the global startup tracker."""
    global _tracker
    if _tracker is None:
        _tracker = StartupTracker()
    return _tracker


def safe_import(module_path: str, fallback_fn: Optional[Callable[[], Any]] = None) -> Any:
    """
    Safely import a module, catching errors and returning fallback if needed.
    
    Args:
        module_path: Full module path
        fallback_fn: Function to call if import fails, returns fallback object
    
    Returns:
        Imported module or fallback value
    """
    tracker = get_startup_tracker()
    start = time.time()
    
    try:
        parts = module_path.rsplit(".", 1)
        if len(parts) == 2:
            mod_name, attr_name = parts
            module = __import__(mod_name, fromlist=[attr_name])
            obj = getattr(module, attr_name)
        else:
            obj = __import__(module_path)
        
        duration_ms = (time.time() - start) * 1000
        tracker.log_module_load(module_path, duration_ms)
        return obj
    except ImportError as e:
        tracker.log_error(module_path, e, recoverable=True)
        if fallback_fn:
            return fallback_fn()
        raise


def print_startup_report():
    """Print a formatted startup report."""
    tracker = get_startup_tracker()
    summary = tracker.get_summary()
    
    print("\n" + "="*60)
    print("STARTUP DIAGNOSTICS")
    print("="*60)
    print(f"Total Time: {summary['total_time_s']}s")
    print(f"Events: {summary['event_count']} | Errors: {summary['error_count']} | Critical: {summary['critical_errors']}")
    
    if summary["slow_modules"]:
        print("\nTop 5 Slowest Modules:")
        for mod, duration in summary["slow_modules"]:
            print(f"  {mod}: {duration:.0f}ms")
    
    if summary["errors"]:
        print("\nErrors:")
        for err in summary["errors"]:
            print(f"  [{err['type']}] {err['component']}: {err['error'][:80]}")
    
    print("="*60 + "\n")


# Install to check at exit
import atexit
def _exit_handler():
    if _tracker:
        print_startup_report()

# Uncomment to enable exit report:
# atexit.register(_exit_handler)
