@echo off
chcp 65001 >nul
title Bloquera Funez — Subir a GitHub
echo.
echo  =====================================================
echo   Subiendo dashboard actualizado a GitHub...
echo  =====================================================
echo.

cd /d "%~dp0"

git add index.html
git -c http.sslVerify=false commit -m "update: datos actualizados desde Akasia"
git -c http.sslVerify=false push

echo.
echo  =====================================================
echo   Listo! En 1 minuto el celular tendra los datos
echo   nuevos en:
echo   https://rjmendoza8977-dev.github.io/bloquera-dashboard/
echo  =====================================================
echo.
pause
