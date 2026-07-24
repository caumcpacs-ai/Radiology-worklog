# 영상의학과 업무일지 웹앱

## 📋 개요
Flask + SQLite 기반 중앙대학교병원 영상의학과 내부망 전용 업무일지 시스템

---

## 🚀 실행 방법

### 1. Python 패키지 설치
```bash
pip install flask
```

### 2. 앱 실행
```bash
python app.py
```

### 3. 접속
- 본인 PC: `http://localhost:1000`
- 내부망 다른 PC: `http://[서버IP]:1000`

### 4. 초기 계정
| 아이디 | 비밀번호 | 권한 |
|--------|----------|------|
| admin | admin1234 | 관리자 |

> 운영 시 반드시 비밀번호를 변경하세요.

---

## 🗂️ 주요 화면 구성

| 메뉴 | URL | 설명 |
|------|-----|------|
| 메인 | `/` | 대시보드 (오늘 전체 현황 + KPI 툴팁) |
| 업무일지 작성 | `/write` | 날짜별 업무일지 통합 입력 |
| 업무일지 리스트 | `/worklog` | 제출된 날짜 목록 및 항목 현황 |
| 사용자 관리 | `/users` | 관리자 전용 계정 관리 |
| 인쇄 | `/print/<날짜>` | A4 인쇄용 뷰 |

---

## 🔧 기능 목록

### 1. 근무자 현황
- 근무조(오전/종일/야간), 성명, 직종, 비고 등록
- 항목별 수정 / 삭제

### 2. 휴가 현황
- 성명, 휴가 구분(연차/반차/병가/공가/기타), 날짜 등록
- 항목별 수정 / 삭제

### 3. On-call
- 모달리티(CT/MRI/일반/전체), 담당자, 시작/종료 시간, 내용 등록
- 항목별 수정 / 삭제

### 4. 연장근무
- 성명, 시작/종료 시간 (자동 시간 계산), 사유 등록
- 항목별 수정 / 삭제

### 5. 장비 이력
- 장비명, 유형(고장/점검/PM/기타), 내용, 엔지니어, 다운타임, 상태 등록
- 항목별 수정 / 삭제

### 6. 인수인계
- 근무조, 인계자, 인수자, 우선순위(일반/중요/긴급), 내용 등록
- 항목별 수정 / 삭제

### 7. 특이사항·이슈
- 구분(장비/환자/행정/기타), 심각도, 제목, 내용, 상태 등록
- 항목별 수정 / 삭제

---

## 🔐 권한 체계

| 기능 | 사용자 | 관리자 |
|------|--------|--------|
| 업무일지 작성·저장 | ✅ | ✅ |
| 업무일지 제출 | ✅ | ✅ |
| 인쇄 | ✅ | ✅ |
| 업무일지 수정 (정상) | ❌ | ✅ |
| 업무일지 반려 | ❌ | ✅ |
| 업무일지 수정 (반려 시) | ✅ (본인) | ✅ |
| 사용자 관리 | ❌ | ✅ |

- 저장: 데이터만 DB에 저장, 업무일지 리스트에는 미표시
- 제출: 리스트에 등록됨. 저장 버튼 클릭 시 "제출하시겠습니까?" 팝업으로 결정
- 관리자가 반려 시 대상 사용자를 선택 → 해당 사용자 리스트에만 반려 표시
- 반려 취소는 관리자만 가능

---

## 📊 대시보드

- KPI 6종: 미해결 이슈 / 오늘 이슈 / 오늘 인수인계 / 장비 처리중 / 오늘 휴가 / 오늘 On-call
- KPI 제목에 커서를 올리면 카운트된 항목 상세 내용 툴팁 표시
- 오늘 날짜 기준 7개 섹션 전부 표시: 근무자·휴가·On-call·연장근무·장비이력·인수인계·이슈

---

## 📁 파일 구조

```
radiology_worklog/
├── app.py                  ← 메인 Flask 앱 (라우트 및 DB 로직)
├── backup_db.py            ← DB 자동 백업 스크립트 (작업 스케줄러로 매일 08:00 실행)
├── requirements.txt        ← 패키지 목록
├── README.md               ← 이 파일
├── CLAUDE.md               ← Claude Code 프로젝트 문서 (README와 동기화)
├── instance/
│   └── worklog.db         ← SQLite DB (자동 생성)
├── backups/                ← 날짜별 DB 백업 + backup.log (자동 생성)
└── templates/
    ├── base.html           ← 공통 레이아웃 (사이드바, 상단바)
    ├── login.html          ← 로그인 페이지
    ├── dashboard.html      ← 메인 대시보드
    ├── write.html          ← 날짜별 통합 입력 페이지
    ├── worklog_list.html   ← 업무일지 날짜 목록
    ├── print_view.html     ← A4 인쇄 전용 뷰
    ├── users.html          ← 사용자 관리 (관리자)
    ├── user_form.html      ← 사용자 추가 폼
    ├── issues.html / issue_form.html
    ├── handover.html / handover_form.html
    ├── equipment.html / equipment_form.html
    ├── vacation.html / vacation_form.html
    ├── oncall.html / oncall_form.html
    └── overtime.html / overtime_form.html
```

---

## 🗄️ DB 테이블 구조

| 테이블 | 설명 |
|--------|------|
| `users` | 로그인 계정 (username, password, name, role) |
| `staff_roster` | 근무자 현황 (date, shift, staff_name, role, note) |
| `vacation` | 휴가 현황 (staff_name, vacation_type, start_date, end_date) |
| `oncall` | On-call (date, modality, staff_name, start_time, end_time, note) |
| `overtime` | 연장근무 (date, staff_name, start_time, end_time, hours, reason) |
| `equipment_log` | 장비 이력 (date, equipment, log_type, description, engineer, status) |
| `handover` | 인수인계 (date, shift, from_person, to_person, content, priority) |
| `issues` | 특이사항·이슈 (date, category, severity, title, content, status) |
| `worklog_status` | 업무일지 상태 (date, status, submitted_by, submitted_at, rejected_by, rejected_to, rejected_at) |

---

## 🔄 개발 이력

### 초기 구축
- Flask + SQLite 기반 내부망 전용 웹앱 구축
- 포트 1000으로 설정 (`host='0.0.0.0'`)
- SHA-256 해시 기반 로그인 인증
- 관리자(`admin`) / 사용자(`user`) 2단계 권한

### 화면 통합 개선
- 근무현황·업무기록 등 분산된 페이지를 **하나의 날짜 기반 통합 작성 페이지**로 통합
- 아코디언(accordion) UI로 7개 섹션 구성, 기본 전체 펼침 상태
- 인쇄(A4) 버튼 및 초기화(날짜 전체 삭제) 기능 추가
- 업무일지 리스트: 날짜별 항목 수 도트 배지 표시

### 입력 폼 개선
- 모든 섹션에 인라인 수정 폼 추가 (수정 버튼 클릭 시 노란 편집 폼 표시)
- 날짜 바 버튼 순서: 초기화 → 인쇄 순으로 정렬

### 필드 간소화
- 휴가현황: 종료일, 일수, 사유, 상태 제거 → 성명/구분/날짜만 유지
- On-call: 연락처 제거, 비고 → 내용으로 이름 변경
- 연장근무: 승인자 제거

### 권한 및 UI 개선
- 업무일지 리스트 수정/삭제 버튼: 관리자만 표시
- 반려 기능 추가: 관리자가 반려 → 작성자 수정 버튼 활성화
- 사이드바 하단 고정, 이름 옆 역할 표시 (관리자/사용자)
- 사용자 관리 페이지 권한 표시 한국어화

### 입력 항목 추가 및 UI 개선
- 근무자 현황 근무조: `오후` → `종일` 로 변경
- On-call: 담당자와 내용 사이에 **시작/종료 시간** 입력 추가 (기존 DB 자동 마이그레이션 호환)
- 인쇄 뷰 On-call 테이블에 시간 컬럼 추가

### 인쇄 뷰 결재란 추가
- 인쇄 페이지 우측 상단에 **결재칸** 추가 (파트장 / 팀장 / 진료과장)
- 1행: 직책명, 2행: 사인용 공란
- 제목 좌측 정렬, 결재란 우측 정렬로 레이아웃 개선

### 저장/제출 워크플로우 개선
- 작성 페이지 하단 "저장 완료" 버튼 → **저장** 버튼 하나로 통합
- 저장 버튼 클릭 시 팝업: "업무일지가 저장되었습니다. 제출하시겠습니까?"
  - 예: 제출 처리 → 업무일지 리스트에 등록
  - 아니오: 현재 작성 페이지 유지 (데이터는 저장됨)
- 제출 상태/반려 상태 배지 작성 페이지 상단에 표시

### 업무일지 제출·반려 시스템 개편
- **제출된 일자만** 업무일지 리스트에 표시 (단순 저장된 일자는 미표시)
- `worklog_status` 테이블 확장: `submitted_by`, `submitted_at`, `rejected_to` 컬럼 추가
- 관리자 반려 시 **대상 사용자 선택 모달** 표시
  - 선택된 사용자의 리스트에만 반려 항목 표시
- 사용자별 리스트 필터링: 본인이 제출한 항목 + 본인에게 반려된 항목만 조회
- 관리자는 전체 제출·반려 항목 조회

### 대시보드 전면 개편
- KPI "이번주 휴가" → **"오늘 휴가"** 로 변경 (오늘 날짜 기준)
- KPI 제목 호버 시 카운트된 항목 **상세 툴팁** 표시
- 대시보드에 **오늘 날짜 기준 7개 섹션 전부** 표시
  - 근무자현황 / 휴가현황 / On-call / 연장근무 / 장비이력 / 인수인계 / 이슈
  - 각 섹션에 오늘 날짜로 업무일지 작성 페이지 바로가기 버튼
- 사이드바 메뉴: "작성" → **"업무일지 작성"** 으로 변경

---

## 💾 데이터 백업
`instance/` 폴더의 DB 파일을 복사하면 전체 데이터가 백업됩니다. (`worklog.db` 외에 `calendar.db`, `radiation_device.db`, `special_equipment.db`, `maintenance.db` 포함)

### 자동 백업 (매일 08:00)
- `backup_db.py` 스크립트가 `instance/` 폴더의 **모든 파일**을 백업합니다. `.db`는 SQLite 온라인 백업 API로 **앱 실행 중에도 안전하게**, 그 외 파일은 그대로 복사.
- 백업 파일: `backups/<원본이름>_YYYY-MM-DD.db` (예: `worklog_2026-07-24.db`, `calendar_2026-07-24.db`) — 날짜별로 **계속 누적**되며 자동 삭제하지 않음 (backups 폴더 용량 증가에 유의)
- 실행 로그: `backups/backup.log`
- Windows 작업 스케줄러에 `RadiologyWorklog_DB_Backup` 작업으로 등록되어 매일 08:00 실행 (08:00에 PC가 꺼져 있었다면 켜진 후 자동 실행)

```powershell
# 수동 백업 실행
python backup_db.py

# 스케줄러 작업 확인
Get-ScheduledTaskInfo -TaskName "RadiologyWorklog_DB_Backup"

# 스케줄러 작업 삭제
Unregister-ScheduledTask -TaskName "RadiologyWorklog_DB_Backup"
```

> 작업은 현재 사용자 계정으로 등록되어 **로그온 상태에서만** 실행됩니다. 로그아웃 상태에서도 실행하려면 작업 스케줄러(`taskschd.msc`)에서 "사용자의 로그온 여부에 관계없이 실행" 옵션으로 변경하세요.

### 복원
1. 앱 종료 후 `instance/worklog.db`를 백업 파일로 교체
2. 앱 재실행

## ⚙️ 커스터마이징
- 포트 변경: `app.py` 마지막 줄 `port=1000` 수정
- 보안 키: 운영 환경에서 `SECRET_KEY` 환경변수로 설정
- 초기 관리자 비밀번호: `init_db()` 내 `admin1234` 변경 후 `instance/worklog.db` 삭제 후 재실행

## 🌐 GitHub
- 저장소: https://github.com/caumcpacs-ai/Radiology-worklog
