import tkinter as tk
import subprocess
import os

processes = []

def start_services():
    # Command 1: Gateway
    p1 = subprocess.Popen([r"C:\Users\Sahil\.openclaw\gateway.cmd"], shell=True)
    # Command 2: Ollama Proxy
    p2 = subprocess.Popen(["python", "-m", "uvicorn", "api.ollama_proxy:app", "--host", "127.0.0.1", "--port", "11435"], cwd="C:\\AI_Assistant")
    # Command 3: Server
    p3 = subprocess.Popen(["python", "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", "8000"], cwd="C:\\AI_Assistant")
    
    processes.extend([p1, p2, p3])
    status_label.config(text="Status: Running", fg="green")

def stop_services():
    for p in processes:
        p.terminate()
    processes.clear()
    status_label.config(text="Status: Stopped", fg="red")

root = tk.Tk()
root.title("AI Assistant Controller")
root.geometry("300x150")

status_label = tk.Label(root, text="Status: Stopped", fg="red")
status_label.pack(pady=10)

tk.Button(root, text="START ALL", command=start_services, bg="lightgreen", width=15).pack(pady=5)
tk.Button(root, text="STOP ALL", command=stop_services, bg="salmon", width=15).pack(pady=5)

root.mainloop()