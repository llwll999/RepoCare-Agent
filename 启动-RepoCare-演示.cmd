@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -m uvicorn repocare.multi_agent_demo:app --app-dir src --host 127.0.0.1 --port 8012
