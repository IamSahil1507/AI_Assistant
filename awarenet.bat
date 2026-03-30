@echo off
set "OLLAMA_HOST=http://127.0.0.1:8000"
ollama run awarenet-model:v1 %*
