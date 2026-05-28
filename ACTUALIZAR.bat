@echo off
chcp 65001 >nul
title Bloquera Funez — Actualizador
echo.
echo  =====================================================
echo   Bloquera Funez — Actualizador de Dashboard
echo  =====================================================
echo.

:: Ir a la carpeta del script
cd /d "%~dp0"

:: Correr el script Python
python actualizar.py

:: Si Python no está en PATH, intentar con py
if errorlevel 1 (
    py actualizar.py
)

pause
