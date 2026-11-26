@echo off
title VoltX Solar Intelligence Platform - FastAPI Server
color 0A

echo.
echo  =========================================================
echo   VoltX Solar Power Plant Anomaly Intelligence Platform
echo   FastAPI + SVR Calibration Model + MySQL solar_monitoring_db
echo  =========================================================
echo.
echo  Starting Uvicorn server on http://127.0.0.1:8000 ...
echo  Root URL automatically redirects to Operator Dashboard.
echo.
echo  Pages available after startup:
echo    [1] http://127.0.0.1:8000/                       (auto-redirects to Operator Dashboard)
echo    [2] http://127.0.0.1:8000/static/index.html      (Plant Operator - Live Estimator)
echo    [3] http://127.0.0.1:8000/static/deviations.html (Renewable Energy Co - Inverter Explorer)
echo    [4] http://127.0.0.1:8000/static/investigations.html (Auditor - MySQL CRUD Triage)
echo    [5] http://127.0.0.1:8000/static/research.html   (Researcher - ML Methodology Sandbox)
echo    [6] http://127.0.0.1:8000/docs                   (Interactive FastAPI Documentation)
echo.
echo  Press Ctrl+C to stop the server.
echo  =========================================================
echo.

cd /d "%~dp0"
uvicorn main:app --host 127.0.0.1 --port 8000 --reload

pause
