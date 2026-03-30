@echo off
start "Gateway" /min "C:\Users\Sahil\.openclaw\gateway.cmd"
cd /d C:\AI_Assistant
start "Ollama Proxy" /min python -m uvicorn api.ollama_proxy:app --host 127.0.0.1 --port 11435
start "Server" /min python -m uvicorn api.server:app --host 127.0.0.1 --port 8000
echo Services starting...
pause