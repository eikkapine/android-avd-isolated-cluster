@echo off
title Android Virtual Device Cluster Launcher
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File ".\scripts\launch_avd_cluster.ps1"
pause
