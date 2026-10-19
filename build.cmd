@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0win\build.ps1" %*
