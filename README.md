# 영상의학과 업무일지 웹앱

## 📋 개요
Flask + SQLite 기반 내부망 전용 업무일지 시스템

## 🔧 기능
- ⚠️ **특이사항·이슈** 기록 (구분/심각도/상태 관리)
- 🔄 **인수인계** 메모 (교대별/우선순위)
- 🔧 **장비 고장·점검** 이력 (다운타임 추적)
- 🌴 **휴가 현황** 관리 (승인 상태)
- 📱 **On-call** 담당자 등록
- ⏰ **연장근무** 기록 (자동 시간 계산)
- 👥 사용자 관리 (관리자 전용)

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
- 본인 PC: http://localhost:5000
- 내부망 다른 PC: http://[서버IP]:5000

## 🔑 초기 계정
- 아이디: `admin`
- 비밀번호: `admin1234`
> ⚠️ 운영 시 반드시 비밀번호를 변경하세요!

## 📁 파일 구조
```
radiology_worklog/
├── app.py              ← 메인 Flask 앱
├── requirements.txt    ← 패키지 목록
├── instance/
│   └── worklog.db     ← SQLite DB (자동 생성)
└── templates/         ← HTML 템플릿
    ├── base.html
    ├── login.html
    ├── dashboard.html
    ├── issues.html / issue_form.html
    ├── handover.html / handover_form.html
    ├── equipment.html / equipment_form.html
    ├── vacation.html / vacation_form.html
    ├── oncall.html / oncall_form.html
    ├── overtime.html / overtime_form.html
    └── users.html
```

## ⚙️ 커스터마이징 포인트
- `app.py` > `equipment_form.html`: 장비 목록 수정
- `app.secret_key`: 운영 환경에서 복잡한 값으로 교체
- 포트 변경: `app.run(port=8080)` 등으로 수정

## 💾 데이터 백업
`instance/worklog.db` 파일을 복사하면 전체 데이터 백업됩니다.
