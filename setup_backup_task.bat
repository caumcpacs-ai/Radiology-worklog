@echo off
chcp 65001 >nul
setlocal

rem ============================================================
rem  영상의학과 업무일지 - DB 자동 백업 스케줄 등록
rem  이 파일을 backup_db.py 와 같은 폴더에 두고 더블클릭하세요.
rem  (서버 PC 예: C:\radiology\radiology_worklog\)
rem  매일 08:00 에 backup_db.py 를 실행하도록 작업 스케줄러에 등록합니다.
rem ============================================================

set "TASKNAME=RadiologyWorklog_DB_Backup"
set "SCRIPTDIR=%~dp0"

rem --- 관리자 권한 확인, 없으면 UAC 승격 후 재실행 ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo 관리자 권한이 필요합니다. 권한 상승 창에서 [예]를 눌러주세요...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo.
echo [1/3] backup_db.py 확인 중...
if not exist "%SCRIPTDIR%backup_db.py" (
    echo   [오류] 이 폴더에 backup_db.py 가 없습니다:
    echo          %SCRIPTDIR%
    echo   backup_db.py 와 같은 폴더에 이 파일을 두고 실행하세요.
    goto :fail
)
echo   확인: %SCRIPTDIR%backup_db.py

echo.
echo [2/3] Python 실행기 탐지 중...
set "PYEXE="
for /f "delims=" %%i in ('where pythonw.exe 2^>nul') do (
    if not defined PYEXE set "PYEXE=%%i"
)
if not defined PYEXE (
    for /f "delims=" %%i in ('where python.exe 2^>nul') do (
        if not defined PYEXE set "PYEXE=%%i"
    )
)
if not defined PYEXE (
    echo   [오류] python 을 찾을 수 없습니다. Python 설치 여부와 PATH 를 확인하세요.
    goto :fail
)
echo   사용할 실행기: %PYEXE%

echo.
echo [3/3] 작업 스케줄러에 "%TASKNAME%" 등록 중... (매일 08:00)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$py='%PYEXE%';" ^
  "$script=(Join-Path '%SCRIPTDIR%' 'backup_db.py');" ^
  "$wdir='%SCRIPTDIR%'.TrimEnd('\');" ^
  "$action=New-ScheduledTaskAction -Execute $py -Argument ('\"'+$script+'\"') -WorkingDirectory $wdir;" ^
  "$trigger=New-ScheduledTaskTrigger -Daily -At 8:00am;" ^
  "$settings=New-ScheduledTaskSettingsSet -StartWhenAvailable;" ^
  "Register-ScheduledTask -TaskName '%TASKNAME%' -Action $action -Trigger $trigger -Settings $settings -Description '영상의학과 업무일지 DB 매일 백업' -Force | Out-Null;"

if %errorlevel% neq 0 goto :fail

echo.
echo ============================================================
echo  등록 완료!  매일 오전 08:00 자동 백업됩니다.
echo  (PC가 꺼져 있었으면 켜진 후 놓친 백업을 자동 실행)
echo ============================================================
echo.

set /p RUNNOW="지금 백업을 한 번 테스트 실행할까요? (Y/N): "
if /i "%RUNNOW%"=="Y" (
    echo 테스트 실행 중...
    schtasks /run /tn "%TASKNAME%" >nul 2>&1
    timeout /t 3 >nul
    echo backups\backup.log 를 확인하세요. "성공" 줄이 있으면 정상입니다.
)
goto :done

:fail
echo.
echo [실패] 등록에 실패했습니다. 위 메시지를 확인하세요.

:done
echo.
pause
endlocal
