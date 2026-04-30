@echo off
chcp 65001 > nul
echo ================================================
echo   Windows 로그인 시 서버 자동 시작 등록
echo ================================================
echo.

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "TARGET=%~dp0시작.bat"
set "LINK=%STARTUP%\영상의학과업무일지.lnk"

if exist "%LINK%" del "%LINK%"

powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%LINK%'); $sc.TargetPath = '%TARGET%'; $sc.WorkingDirectory = '%~dp0'; $sc.WindowStyle = 7; $sc.Description = '영상의학과 업무일지 서버'; $sc.Save()"

if exist "%LINK%" (
    echo [완료] Windows 로그인 시 자동으로 서버가 시작됩니다.
    echo.
    echo 등록 위치: %LINK%
    echo.
    echo 해제하려면 자동시작해제.bat 를 실행하세요.
) else (
    echo [오류] 등록에 실패했습니다. 관리자에게 문의하세요.
)
echo.
pause
