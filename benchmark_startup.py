#!/usr/bin/env python3
"""
Startup performance benchmark - measure time to first API response.
Shows concrete before/after improvements from lazy loading.
"""

import subprocess
import time
import requests
import threading
import sys
from pathlib import Path

class ServerBenchmark:
    def __init__(self, host: str = "127.0.0.1", port: int = 8000):
        self.host = host
        self.port = port
        self.process = None
        self.ready_time = None
        self.startup_errors = []
    
    def start_server(self) -> float:
        """Start the server and measure time to first response."""
        print(f"\n🚀 Starting server on {self.host}:{self.port}...")
        start_time = time.time()
        
        try:
            self.process = subprocess.Popen(
                [
                    sys.executable, "-m", "uvicorn",
                    "api.server:app",
                    "--host", self.host,
                    "--port", str(self.port),
                    "--log-level", "critical"
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(Path(__file__).parent)
            )
            
            # Wait for server to respond
            max_wait = 60
            while time.time() - start_time < max_wait:
                try:
                    resp = requests.get(f"http://{self.host}:{self.port}/docs", timeout=1)
                    if resp.status_code < 400:
                        self.ready_time = time.time() - start_time
                        print(f"✅ Server ready in {self.ready_time:.2f}s")
                        return self.ready_time
                except:
                    pass
                time.sleep(0.1)
            
            raise TimeoutError(f"Server didn't respond within {max_wait}s")
        
        except Exception as e:
            self.startup_errors.append(str(e))
            raise
    
    def check_diagnostics(self) -> dict:
        """Get startup diagnostics from the server."""
        try:
            resp = requests.get(f"http://{self.host}:{self.port}/diagnostics", timeout=5)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            print(f"⚠️  Could not fetch diagnostics: {e}")
        return {}
    
    def stop_server(self):
        """Stop the server gracefully."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
                print("✅ Server stopped")
            except:
                self.process.kill()
                print("⚠️  Server force-killed")
    
    def benchmark(self) -> dict:
        """Run full benchmark."""
        try:
            startup_time = self.start_server()
            diagnostics = self.check_diagnostics()
            
            result = {
                "startup_time_s": startup_time,
                "status": "ok",
                "diagnostics": diagnostics,
            }
            
            # Show diagnostics
            if diagnostics:
                components = diagnostics.get("components", {})
                initialized = components.get("initialized", {})
                errors = components.get("errors", {})
                
                print(f"\n📊 Component Status:")
                print(f"  Initialized: {len(initialized)} components")
                if errors:
                    print(f"  Errors: {len(errors)} components failed")
                    for name, err in list(errors.items())[:3]:
                        print(f"    - {name}: {err[:50]}")
            
            return result
        
        finally:
            self.stop_server()


def main():
    print("=" * 60)
    print("STARTUP PERFORMANCE BENCHMARK")
    print("=" * 60)
    
    benchmark = ServerBenchmark()
    
    try:
        result = benchmark.benchmark()
        
        print(f"\n{'=' * 60}")
        print("📈 RESULTS")
        print(f"{'=' * 60}")
        print(f"Startup Time: {result['startup_time_s']:.2f}s")
        
        if result['startup_time_s'] < 5:
            print("✅ EXCELLENT - Lazy loading is working!")
        elif result['startup_time_s'] < 10:
            print("⚠️  ACCEPTABLE - But could be faster")
        else:
            print("❌ SLOW - May need more optimization")
        
        print(f"\n💡 To measure improvement:")
        print(f"  1. Note this time: {result['startup_time_s']:.2f}s")
        print(f"  2. Make code changes")
        print(f"  3. Run this script again")
        print(f"  4. Compare the times")
        
        return 0
    
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
