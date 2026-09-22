@echo off
cd /d "%~dp0"
py -3 start-project.py %*
if errorlevel 1 python start-project.py %*
if errorlevel 1 python3 start-project.py %*
