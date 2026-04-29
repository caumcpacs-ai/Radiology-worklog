@echo off
chcp 65001 > nul
:: 관리자 권한 확인
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [오류] 이 파일은 관리자 권한으로 실행해야 합니다.
    echo 파일을 우클릭 후 "관리자 권한으로 실행"을 선택하세요.
    pause
    exit
)

echo [INFO] 방화벽 규칙을 추가합니다 (port 1000)...
netsh advfirewall firewall add rule name="Radiology Worklog 1000" dir=in action=allow protocol=TCP localport=1000

echo ==================================================
echo   완료! 이제 내부망에서 접속 가능합니다.
echo   접속 주소: http://[이 컴퓨터 IP]:1000
echo ==================================================
pause
