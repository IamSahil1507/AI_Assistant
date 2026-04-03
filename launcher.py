import tkinter as tk
import subprocess
import os
import threading
import time
import requests
from pathlib import Path

processes = []
status_label = None  # Global ref to update

def check_service_health(host: str, port: int, timeout: int = 5) -> bool:
    """Check if a service is responding."""
    try:
        response = requests.get(f"http://{host}:{port}/docs", timeout=timeout)
        return response.status_code < 400
    except:
        return False

def wait_for_service(host: str, port: int, name: str, timeout: int = 30):
    """Wait for a service to become healthy."""
    start = time.time()
    while time.time() - start < timeout:
        if check_service_health(host, port):
            return True
        time.sleep(0.5)
    return False

def start_services():
    """Start all services with health checks."""
    global processes, status_label
    
    try:
        status_label.config(text="Status: Starting...", fg="orange")
        root.update()
        
        # Command 1: Gateway (if available)
        try:
            gateway_ready = False
            p1 = subprocess.Popen(
                [r"C:\Users\Sahil\.openclaw\gateway.cmd"],
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            processes.append(("gateway", p1))
            # Don't wait for gateway, it's optional
            gateway_ready = True
        except Exception as e:
            print(f"Warning: Failed to start gateway: {e}")
        
        # Command 2: Ollama Proxy (11435)
        try:
            p2 = subprocess.Popen(
                ["python", "-m", "uvicorn", "api.ollama_proxy:app", "--host", "127.0.0.1", "--port", "11435"],
                cwd=os.getcwd(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            processes.append(("ollama_proxy", p2))
            status_label.config(text="Status: Waiting for Ollama Proxy...", fg="orange")
            root.update()
            if wait_for_service("127.0.0.1", 11435, "Ollama Proxy"):
                print("✓ Ollama Proxy ready")
            else:
                print("⚠ Ollama Proxy not responding (may still be starting...)")
        except Exception as e:
            status_label.config(text=f"Status: Ollama Proxy Error - {e}", fg="red")
            root.update()
            raise
        
        # Command 3: Main Server (8000)
        try:
            p3 = subprocess.Popen(
                ["python", "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", "8000"],
                cwd=os.getcwd(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            processes.append(("server", p3))
            status_label.config(text="Status: Waiting for Main Server...", fg="orange")
            root.update()
            if wait_for_service("127.0.0.1", 8000, "Server"):
                print("✓ Main Server ready")
                status_label.config(text="Status: Running", fg="green")
                root.update()
            else:
                print("⚠ Main Server not responding (may still be starting...)")
                status_label.config(text="Status: Running (startup in progress)", fg="yellow")
                root.update()
        except Exception as e:
            status_label.config(text=f"Status: Server Error - {e}", fg="red")
            root.update()
            raise
            
    except Exception as e:
        status_label.config(text=f"Status: Failed - {e}", fg="red")
        root.update()
        print(f"ERROR: Failed to start services: {e}")

def stop_services():
    """Stop all services gracefully."""
    global processes, status_label
    
    status_label.config(text="Status: Stopping...", fg="orange")
    root.update()
    
    for name, p in processes:
        try:
            p.terminate()
            p.wait(timeout=5)
            print(f"✓ {name} stopped")
        except subprocess.TimeoutExpired:
            p.kill()
            print(f"✗ {name} force-killed (timeout)")
        except Exception as e:
            print(f"✗ Error stopping {name}: {e}")
    
    processes.clear()
    status_label.config(text="Status: Stopped", fg="red")
    root.update()

def on_closing():
    """Handle window close."""
    stop_services()
    root.destroy()

root = tk.Tk()
root.title("AI Assistant Controller")
root.geometry("350x180")

status_label = tk.Label(root, text="Status: Stopped", fg="red")
status_label.pack(pady=10)

tk.Button(root, text="START ALL", command=start_services, bg="lightgreen", width=15, font=("Arial", 10, "bold")).pack(pady=5)
tk.Button(root, text="STOP ALL", command=stop_services, bg="salmon", width=15, font=("Arial", 10, "bold")).pack(pady=5)
tk.Button(root, text="Check Health", command=lambda: print(f"Bridge: {check_service_health('127.0.0.1', 8000)}"), width=15).pack(pady=5)

root.protocol("WM_DELETE_WINDOW", on_closing)
root.mainloop()