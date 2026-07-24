@echo off
chcp 65001 > nul
cd /d "%~dp0"

:: 포트 1000이 이미 LISTENING 상태인지 확인
netstat -ano | findstr ":1000" | findstr "LISTENING" > nul 2>&1
if %errorlevel% equ 0 goto :open

:: 서버가 없으면 백그라운드로 시작 (창 없음)
echo 서버 시작 중...
start "" /B pythonw app.py

:: 서버 준비 대기 (최대 8초)
set /a i=0
:wait
timeout /t 1 /nobreak > nul
netstat -ano | findstr ":1000" | findstr "LISTENING" > nul 2>&1
if %errorlevel% equ 0 goto :open
set /a i+=1
if %i% lss 8 goto :wait

:open
start "" "http://localhost:1000/app"
exit
