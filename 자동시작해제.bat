@echo off
chcp 65001 > nul
set "LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\영상의학과업무일지.lnk"
if exist "%LINK%" (
    del "%LINK%"
    echo [완료] 자동 시작이 해제되었습니다.
) else (
    echo [안내] 등록된 자동 시작 항목이 없습니다.
)
pause
