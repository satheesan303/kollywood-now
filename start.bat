@echo off
title Kollywood Now
cd /d "%~dp0"
echo Starting Kollywood Now...
start "" http://localhost:8080
python server.py --port 8080
pause
