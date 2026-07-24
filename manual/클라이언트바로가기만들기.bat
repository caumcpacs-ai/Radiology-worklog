@echo off
chcp 65001 > nul
echo ================================================
echo   다른 PC용 바탕화면 바로가기 생성
echo ================================================
echo.

setlocal enabledelayedexpansion

set "SERVER_IP="
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr "IPv4"') do (
    set "IP=%%a"
    set "IP=!IP: =!"
    echo     !IP!
    if not defined SERVER_IP set "SERVER_IP=!IP!"
)

echo.
echo 위 목록에서 서버(이 PC)의 IP 주소를 입력하세요.
echo (예: 192.168.1.100)
echo.
set /p "INPUT_IP=서버 IP 입력: "

if "%INPUT_IP%"=="" (
    echo IP를 입력하지 않았습니다.
    pause
    exit
)

set "URL=http://%INPUT_IP%:1000/app"
set "DESKTOP=%USERPROFILE%\Desktop"
set "LINK=%DESKTOP%\영상의학과업무일지.lnk"

powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%LINK%'); $sc.TargetPath = '%URL%'; $sc.Description = '영상의학과 업무일지 - %URL%'; $sc.Save()"

echo.
echo [완료] 바탕화면에 바로가기가 생성되었습니다.
echo 주소: %URL%
echo.
echo 이 .bat 파일과 만들어진 바로가기를
echo 다른 PC로 복사해서 사용하세요.
echo.
pause