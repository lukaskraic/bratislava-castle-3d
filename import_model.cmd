@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0win\import_model.ps1" %*
