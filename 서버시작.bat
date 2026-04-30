@echo off
chcp 65001 > nul
title 영상의학과 업무일지 서버

echo ==================================================
echo   중앙대학교병원 영상의학과 업무일지 서버
echo ==================================================

:: 현재 폴더로 이동
cd /d "%~dp0"

:: 포트 1000 사용 중인지 확인
netstat -ano | findstr :1000 > nul
if %errorlevel% equ 0 (
    echo [INFO] 서버가 이미 실행 중입니다. (port 1000)
    echo [INFO] 브라우저에서 http://localhost:1000 접속하세요.
    pause
    exit
)

:: 패키지 설치 확인
echo [INFO] 패키지 확인 중...
py -m pip install -r requirements.txt -q

:: 서버 시작
echo [INFO] 서버를 시작합니다...
echo [INFO] 접속 주소: http://localhost:1000
echo [INFO] 내부망 접속: http://%COMPUTERNAME%:1000
echo [INFO] 종료하려면 이 창을 닫으세요.
echo ==================================================

py app.py

pause
