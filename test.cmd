@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0win\test.ps1" %*
