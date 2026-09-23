@echo off
rem Detached single-instance launcher. Logs stay in the git-ignored data dir.
cd /d "%~dp0"
if not exist "data" mkdir "data"
".venv\Scripts\python.exe" -m agent_app >> "data\service.log" 2>&1
