# 영상의학과 업무일지 - 설치 및 배포 가이드

## 목차

1. [구성 개요](#1-구성-개요)
2. [서버 PC 세팅](#2-서버-pc-세팅)
   - [2-1. Python 설치](#2-1-python-설치)
   - [2-2. 프로그램 파일 배치](#2-2-프로그램-파일-배치)
   - [2-3. 패키지 설치](#2-3-패키지-설치)
   - [2-4. 방화벽 포트 허용 (관리자 권한 필요)](#2-4-방화벽-포트-허용-관리자-권한-필요)
   - [2-5. 서버 실행 테스트](#2-5-서버-실행-테스트)
   - [2-6. 로그인 시 서버 자동 시작 등록](#2-6-로그인-시-서버-자동-시작-등록)
3. [배포 PC (클라이언트) 세팅](#3-배포-pc-클라이언트-세팅)
   - [3-1. 서버 IP 확인](#3-1-서버-ip-확인)
   - [3-2. 바탕화면 바로가기 생성](#3-2-바탕화면-바로가기-생성)
4. [초기 계정 및 비밀번호 변경](#4-초기-계정-및-비밀번호-변경)
5. [자동 시작 해제](#5-자동-시작-해제)
6. [데이터 백업](#6-데이터-백업)
7. [문제 해결](#7-문제-해결)

---

## 1. 구성 개요

```
[서버 PC] ──내부망──> [배포 PC / 클라이언트 PC]
  - Python + Flask 실행         - 브라우저로 접속
  - 포트 1000 Listen            - http://<서버IP>:1000
  - worklog.db (SQLite)
```

- **서버 PC 1대**에서 Flask 앱을 실행합니다.
- **같은 내부망에 연결된 모든 PC**에서 브라우저를 통해 접속합니다.
- 인터넷 연결 없이 병원 내부망만으로 동작합니다.

---

## 2. 서버 PC 세팅

### 2-1. Python 설치

1. [https://www.python.org/downloads/](https://www.python.org/downloads/) 에서 **Python 3.10 이상** 다운로드
2. 설치 시 반드시 **"Add Python to PATH"** 체크 후 설치

설치 확인:
```
Win + R → cmd → python --version
```
버전 번호가 출력되면 정상입니다.

---

### 2-2. 프로그램 파일 배치

프로그램 파일을 서버 PC의 원하는 폴더에 복사합니다.

권장 경로 예시:
```
C:\radiology_worklog\
  ├── app.py
  ├── requirements.txt
  ├── templates\
  └── instance\        ← DB가 여기에 자동 생성됨
```

> **주의:** OneDrive, 네트워크 드라이브(\\server\...) 경로는 DB 파일 잠금 오류가 발생할 수 있습니다.
> 반드시 로컬 드라이브(C:\, D:\)에 배치하세요.

---

### 2-3. 패키지 설치

명령 프롬프트(cmd)를 열고 프로그램 폴더로 이동 후 실행:

```cmd
cd C:\radiology_worklog
pip install -r requirements.txt
```

설치되는 패키지: `flask`, `werkzeug` 등

---

### 2-4. 방화벽 포트 허용 (관리자 권한 필요)

내부망의 다른 PC에서 접속하려면 방화벽에서 포트 1000을 열어야 합니다.

**PowerShell을 관리자 권한으로 실행** 후 아래 명령어 입력:

```powershell
netsh advfirewall firewall add rule name="Radiology Worklog 1000" dir=in action=allow protocol=TCP localport=1000
```

확인:
```powershell
netsh advfirewall firewall show rule name="Radiology Worklog 1000"
```

> 이 설정은 **영구 적용**되며, 재부팅 후에도 유지됩니다. 한 번만 실행하면 됩니다.

---

### 2-5. 서버 실행 테스트

명령 프롬프트에서 아래 명령어로 서버를 실행합니다:

```cmd
cd C:\radiology_worklog
python app.py
```

아래와 같이 출력되면 정상:
```
 * Running on http://0.0.0.0:1000
```

브라우저에서 `http://localhost:1000` 접속 후 로그인 화면이 나오면 성공입니다.

서버를 종료하려면 해당 창에서 `Ctrl + C`를 누르세요.

---

### 2-6. 로그인 시 서버 자동 시작 등록

서버 PC에 로그인하면 자동으로 서버가 백그라운드에서 실행되도록 **작업 스케줄러**에 등록합니다.

**PowerShell을 관리자 권한으로 실행** 후 아래 명령어를 한 번에 실행합니다.
`C:\radiology_worklog` 부분을 실제 설치 경로로 바꿔주세요.

```powershell
$dir = "C:\radiology_worklog"
$exe = Join-Path $dir "app.py"
$a = New-ScheduledTaskAction -Execute "pythonw.exe" -Argument $exe -WorkingDirectory $dir
$t = New-ScheduledTaskTrigger -AtLogOn
$s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit 0 -StartWhenAvailable $true
$p = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -RunLevel Highest -LogonType Interactive
Register-ScheduledTask -TaskName "영상의학과업무일지_서버" -Action $a -Trigger $t -Settings $s -Principal $p -Force
```

등록 확인:
```powershell
Get-ScheduledTask -TaskName "영상의학과업무일지_서버"
```

등록 완료 후 **PC를 재부팅**하면, 로그인 시 서버가 자동으로 백그라운드에서 시작됩니다.

> `pythonw.exe`는 콘솔 창 없이 백그라운드로 실행합니다.
> 서버가 실행 중인지 확인하려면 브라우저에서 `http://localhost:1000` 접속하거나,
> 작업 관리자에서 `pythonw.exe` 프로세스를 확인하세요.

---

## 3. 배포 PC (클라이언트) 세팅

별도 프로그램 설치 없이 **브라우저**만 있으면 됩니다.

### 3-1. 서버 IP 확인

서버 PC에서 명령 프롬프트를 열고 실행:

```cmd
ipconfig
```

`IPv4 주소` 항목의 값이 서버 IP입니다. 예: `192.168.1.100`

> 내부망 IP는 보통 `192.168.x.x` 또는 `10.x.x.x` 대역입니다.

---

### 3-2. 바탕화면 바로가기 생성

배포 PC의 바탕화면에 접속 바로가기를 만듭니다.
아래 명령어에서 `서버IP` 부분을 실제 서버 IP로 바꿔주세요.

**PowerShell 실행** 후 아래 명령어 입력:

```powershell
$url = "http://192.168.1.100:1000"   # 서버 IP로 변경
$link = "$env:USERPROFILE\Desktop\영상의학과업무일지.lnk"
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($link)
$sc.TargetPath = $url
$sc.Description = "영상의학과 업무일지"
$sc.Save()
Write-Host "바탕화면에 바로가기가 생성되었습니다: $link"
```

생성된 바로가기를 더블클릭하면 기본 브라우저로 업무일지가 열립니다.

> 여러 PC에 배포할 경우: 위 PowerShell 명령어를 `.ps1` 파일로 저장하거나,
> 서버 IP만 바꿔서 각 PC에서 실행하면 됩니다.

---

## 4. 초기 계정 및 비밀번호 변경

| 아이디 | 비밀번호 | 권한 |
|--------|----------|------|
| admin | admin1234 | 관리자 |

**운영 시작 전 반드시 관리자 비밀번호를 변경하세요.**

비밀번호 변경 방법:
1. 브라우저에서 `http://localhost:1000` 접속 후 admin 로그인
2. 사용자 관리 → admin 계정 수정 → 새 비밀번호 입력

초기 관리자 비밀번호를 코드에서 변경하려면:
- `app.py`의 `init_db()` 함수 내 `admin1234` 변경
- `instance/worklog.db` 파일 삭제 후 서버 재실행

---

## 5. 자동 시작 해제

작업 스케줄러에서 자동 시작 등록을 해제하려면:

```powershell
Unregister-ScheduledTask -TaskName "영상의학과업무일지_서버" -Confirm:$false
```

또는 작업 스케줄러 GUI에서:
- `Win + R` → `taskschd.msc` → **작업 스케줄러 라이브러리** → `영상의학과업무일지_서버` → 우클릭 → **삭제**

---

## 6. 데이터 백업

모든 데이터는 `instance/worklog.db` 파일 하나에 저장됩니다.

백업 방법:
```cmd
copy C:\radiology_worklog\instance\worklog.db D:\backup\worklog_백업날짜.db
```

복원 방법:
1. 서버 서비스 중지 (작업 관리자에서 `pythonw.exe` 종료)
2. `instance/worklog.db`를 백업 파일로 교체
3. 서버 재시작

---

## 7. 문제 해결

### 다른 PC에서 접속이 안 될 때

1. 서버 PC에서 서버가 실행 중인지 확인 → `http://localhost:1000`
2. 방화벽 포트 1000이 열려 있는지 확인 ([2-4 항목](#2-4-방화벽-포트-허용-관리자-권한-필요) 재실행)
3. 클라이언트 PC와 서버 PC가 같은 네트워크(내부망)에 연결되어 있는지 확인
4. 서버 IP가 변경되었다면 바로가기의 URL 업데이트 필요

### 서버가 시작되지 않을 때

1. Python이 설치되어 있는지 확인: `python --version`
2. 패키지가 설치되어 있는지 확인: `pip list | findstr flask`
3. 포트 1000이 이미 사용 중인지 확인:
   ```cmd
   netstat -ano | findstr ":1000"
   ```
   다른 프로세스가 사용 중이면 `app.py` 마지막 줄의 `port=1000`을 다른 번호로 변경

### DB 오류가 발생할 때

- `instance/` 폴더가 없으면 수동으로 생성 후 서버 재실행
- OneDrive 또는 네트워크 드라이브에 설치된 경우 로컬 드라이브로 이동




방법 1: NSSM으로 Windows 서비스 등록 (권장)
장점: 시스템 시작 시 자동 실행, 창 없이 백그라운드 동작, 크래시 시 자동 재시작

설치 및 등록 절차
NSSM 다운로드 — nssm.cc/download 에서 다운로드 후 C:\nssm\ 폴더에 압축 해제

PowerShell을 관리자 권한으로 실행 후 서비스 등록:


C:\nssm\win64\nssm.exe install RadiologyWorklog
GUI 창이 뜨면:

Path: C:\Users\vmfort\AppData\Local\Programs\Python\Python3xx\python.exe (본인 Python 경로)
Startup directory: c:\vmfort\OneDrive - 중앙대학교 병원\Individual\hospital\Claude Code\radiology_worklog
Arguments: app.py
서비스 시작:

C:\nssm\win64\nssm.exe start RadiologyWorklog
방법 2: 배치파일에 pythonw.exe + 작업 스케줄러 사용
장점: NSSM 설치 불필요

start_server.bat 수정

@echo off
cd /d "c:\vmfort\OneDrive - 중앙대학교 병원\Individual\hospital\Claude Code\radiology_worklog"
start "" pythonw.exe app.py
pythonw.exe는 콘솔 창 없이 Python을 실행합니다.

작업 스케줄러 등록
작업 스케줄러 열기
작업 만들기 → 이름: RadiologyWorklog
트리거 → 컴퓨터 시작 시
동작 → 위 bat 파일 실행
조건 → "AC 전원에 연결된 경우에만" 체크 해제
일반 → "사용자 로그온 여부에 관계없이 실행" 선택
어떤 방법이 적합한가?
상황	권장 방법
서버 PC가 항상 켜져 있음	NSSM 서비스
설치 없이 간단하게	방법 2 (작업 스케줄러)
크래시 자동 재시작 필요	NSSM 서비스
NSSM 방법을 추천합니다. 설치가 필요하지만 가장 안정적으로 백그라운드에서 서버가 동작합니다. 진행할 방법을 선택하시면 상세한 단계를 안내드리겠습니다.
