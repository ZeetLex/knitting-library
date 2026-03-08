@echo off
setlocal enabledelayedexpansion

:: ============================================================
::  Knitting Library - Build & Push Script
::  Place this file in the root of your project folder
::  (same folder as docker-compose.yml)
::  Run it by double-clicking or from a terminal: deploy.bat
:: ============================================================

set BACKEND_IMAGE=zeetlex/knitting-library-backend:latest
set FRONTEND_IMAGE=zeetlex/knitting-library-frontend:latest
set BACKEND_PATH=app\backend
set FRONTEND_PATH=app\frontend

:: Fancy header
echo.
echo  ==========================================
echo   Knitting Library - Build and Push
echo  ==========================================
echo.

:: Check Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Docker is not running!
    echo  Please start Docker Desktop and try again.
    echo.
    pause
    exit /b 1
)
echo  [OK] Docker is running
echo.

:: ── STEP 1: Build Backend ─────────────────────────────────
echo  [1/4] Building backend image...
echo        %BACKEND_IMAGE%
echo.
docker build -t %BACKEND_IMAGE% %BACKEND_PATH%
if errorlevel 1 (
    echo.
    echo  [FAILED] Backend build failed. See errors above.
    pause
    exit /b 1
)
echo.
echo  [OK] Backend build complete
echo.

:: ── STEP 2: Build Frontend ────────────────────────────────
echo  [2/4] Building frontend image...
echo        %FRONTEND_IMAGE%
echo        ^(This takes a few minutes - React is compiling^)
echo.
docker build -t %FRONTEND_IMAGE% %FRONTEND_PATH%
if errorlevel 1 (
    echo.
    echo  [FAILED] Frontend build failed. See errors above.
    pause
    exit /b 1
)
echo.
echo  [OK] Frontend build complete
echo.

:: ── STEP 3: Push Backend ──────────────────────────────────
echo  [3/4] Pushing backend to Docker Hub...
echo.
docker push %BACKEND_IMAGE%
if errorlevel 1 (
    echo.
    echo  [FAILED] Backend push failed.
    echo  Are you logged in? Run: docker login
    pause
    exit /b 1
)
echo.
echo  [OK] Backend pushed successfully
echo.

:: ── STEP 4: Push Frontend ─────────────────────────────────
echo  [4/4] Pushing frontend to Docker Hub...
echo.
docker push %FRONTEND_IMAGE%
if errorlevel 1 (
    echo.
    echo  [FAILED] Frontend push failed.
    echo  Are you logged in? Run: docker login
    pause
    exit /b 1
)
echo.
echo  [OK] Frontend pushed successfully
echo.

:: ── Done ──────────────────────────────────────────────────
echo  ==========================================
echo   All done! Both images are live on
echo   Docker Hub and ready to pull.
echo  ==========================================
echo.
echo  To update your server, run:
echo    docker-compose pull
echo    docker-compose up -d
echo.
pause
