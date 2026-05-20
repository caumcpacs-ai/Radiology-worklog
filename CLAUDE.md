영상의학과 업무일지 웹앱 

📋 개요 

Flask + SQLite 기반 중앙대학교병원 영상의학과 내부망 전용 업무일지 시스템 

근무자 현황, 휴가 현황, On-call, 연장근무, 장비 이력, 특이사항·이슈를 날짜 기준으로 통합 관리하며, 

사용자 관리와 휴가 코드 관리, 업무일지 저장·제출·반려·확정 워크플로우를 지원합니다. 

 

 

🚀 실행 방법 

1. Python 패키지 설치 

pip install flask  

2. 앱 실행 

python app.py  

3. 접속 

본인 PC: http://localhost:1000 

내부망 다른 PC: http://[서버IP]:1000 

4. 초기 계정 

아이디 

비밀번호 

권한 

admin 

admin1234 

관리자 

운영 시 반드시 비밀번호를 변경하세요. 

 

 

🗂️ 주요 화면 구성 

메뉴 

URL 

설명 

메인 

/ 

대시보드 (오늘 현황, KPI, 근무자 현황 요약) 

업무일지 작성 

/write 

날짜별 업무일지 통합 입력 

업무일지 리스트 

/worklog 

제출된 업무일지 목록 및 상태/버튼 관리 

사용자 관리 

/users 

관리자 전용 사용자 관리 + 휴가 코드 관리 

인쇄 

/print/<날짜> 

A4 인쇄용 뷰 

 

 

🔧 기능 목록 

1. 근무자 현황 

근무조: 야간 기본값, 오전, 종일 선택 

파트: GR, CT, MR, 인터벤션, 간호 선택 

성명 등록 

직종, 비고 항목 삭제 

대시보드 및 출력 시 근무조 + 파트 기준으로 묶고 성명을 나열하여 표시 

예) 

야간 일반촬영 - 김철수, 홍길동 

야간 CT - 홍철수, 김길동 

종일 일반촬영 - 김수철, 홍동길 

종일 CT - 김하나, 이하나 

오전 일반촬영 - 김두나, 김세나 

오전 CT - 김넷, 홍둘 

2. 휴가 현황 

성명: 사용자 관리 정보 기준 가나다순 선택 

구분: 등록된 휴가 코드 선택 

날짜 등록 

항목별 수정 / 삭제 

3. On-call 

모달리티 → 파트로 변경 

파트는 사용자 관리의 파트 정보 기준 사용 

담당자 → 성명으로 변경 

성명은 사용자 관리의 사용자 목록에서 선택 가능 

성명 입력 항목 하단에 직접 입력 추가 가능 

시간 → 전화받은 시각 

내용 → 사유로 변경 

항목별 수정 / 삭제 

4. 연장근무 

성명, 시작 시간, 종료 시간, 총시간, 사유 등록 

총시간은 종료시간 - 시작시간으로 자동 계산 

항목별 수정 / 삭제 

5. 장비 이력 

장비 → 장비명으로 변경 

장비명, 유형(고장/점검/수리완료/PM), 내용 등록 

시작, 종료 시간을 엔지니어, 다운타임 사이에 추가 

상태 등록 

항목별 수정 / 삭제 

6. 특이사항·이슈 

구분(장비/환자/행정/기타), 심각도, 제목, 내용, 상태 등록 

항목별 수정 / 삭제 

7. 사용자 관리 / 휴가 코드 관리 

사용자 관리에서 아이디를 사번 기준으로 관리 

이름과 권한 사이에 파트 추가 

파트는 GR, CT, MR, 인터벤션, 간호 중 선택 

등록일 다음에 입사일자, 퇴사일자 추가 

퇴사일자는 기본값 빈칸 

사용자 관리 화면은 기본적으로 퇴사일자가 빈칸인 재직자만 조회 

상단에 재직자 / 퇴사자 / 전체 선택 체크 영역 제공 

사용자 관리 하단에 휴가 코드 관리 추가 

휴가 코드는 코드, 근무정보, 출근시간, 퇴근시간 등록 가능 

 

 

🔐 권한 체계 

기능 

사용자 

관리자 

업무일지 저장 

✅ 

✅ 

업무일지 제출 

✅ 

✅ 

인쇄 

✅ 

✅ 

사용자 관리 

❌ 

✅ 

제출 상태에서 수정 

❌ 

✅ 

제출 상태에서 회수 

✅ 

❌ 

제출 상태에서 반려 

❌ 

✅ 

제출 상태에서 확정 

버튼 표시만 / 동작 없음 

✅ 

반려 상태에서 수정 

✅ 

✅ 

반려 상태에서 삭제 

✅ 

✅ 

반려 상태에서 재제출 

✅ 

✅ 

저장 / 제출 동작 

작성 페이지에서 저장 버튼 클릭 시 데이터 임시저장 

저장 이후에만 제출 버튼 활성화 

제출된 일자만 업무일지 리스트에 표시 

이미 해당 작성일자가 제출 상태인 경우 저장 시 아래 안내 문구 표시 후 임시저장만 가능 

해당일자의 업무일지가 제출되었습니다. 업무일지 리스트에서 확인하시기 바랍니다. 

업무일지 상태별 버튼 규칙 

사용자 권한 

제출 상태  

회수, 인쇄 버튼만 활성화 

회수를 누르면 수정 버튼이 활성화되어 수정 가능 

확정 상태  

확정, 인쇄 버튼만 활성화 

사용자 권한에서 확정 버튼은 동작 없음 

반려 상태  

수정, 삭제, 회수, 제출, 확정, 인쇄 버튼 활성화 

관리자 권한 

사용자가 제출한 상태  

수정, 반려, 확정, 인쇄 버튼 활성화 

삭제, 회수, 제출 버튼 비활성화 

반려 처리 시  

사용자 화면에서 수정, 삭제, 회수, 제출, 확정, 인쇄 버튼 활성화 

회수 상태일 때  

사용자 화면에서는 수정 버튼만 활성화되도록 처리 

 

 

📊 대시보드 

KPI 6종: 

오늘 휴가 

오늘 On-call 

오늘 연장근무 

장비 처리중 

오늘 이슈 

미해결 이슈 

기존 인수인계 KPI는 삭제 

KPI 제목에 커서를 올리면 카운트된 항목 상세 내용 툴팁 표시 

오늘 날짜 기준 아래 섹션 표시 

근무자 현황 

휴가 현황 

On-call 현황 

연장근무 현황 

장비 이력 

특이사항·이슈 

근무자 현황은 근무조 + 파트로 그룹화하고 성명 나열 방식으로 표시 

 

 

📁 파일 구조 

radiology_worklog/ ├── app.py ← 메인 Flask 앱 (라우트 및 DB 로직) ├── requirements.txt ← 패키지 목록 ├── README.md ← 프로젝트 문서 ├── CLAUDE.md ← Claude Code 프로젝트 문서 (README와 동기화) ├── instance/ │ └── worklog.db ← SQLite DB (자동 생성) └── templates/ ├── base.html ← 공통 레이아웃 (사이드바, 상단바) ├── login.html ← 로그인 페이지 ├── dashboard.html ← 메인 대시보드 ├── write.html ← 날짜별 통합 입력 페이지 ├── worklog_list.html ← 업무일지 날짜 목록 ├── print_view.html ← A4 인쇄 전용 뷰 ├── users.html ← 사용자 관리 + 재직/퇴사/전체 필터 + 휴가 코드 관리 ├── user_form.html ← 사용자 추가/수정 폼 ├── vacation_code_form.html ← 휴가 코드 추가/수정 폼 ├── issues.html / issue_form.html ├── equipment.html / equipment_form.html ├── vacation.html / vacation_form.html ├── oncall.html / oncall_form.html └── overtime.html / overtime_form.html  

 

🗄️ DB 테이블 구조 

테이블 

설명 

users 

로그인 계정 및 사용자 정보 (employee_id, password, name, part, role, created_at, hire_date, retired_date) 

staff_roster 

근무자 현황 (date, shift, part, staff_name) 

vacation 

휴가 현황 (date, staff_name, vacation_code) 

vacation_codes 

휴가 코드 관리 (code, work_info, start_time, end_time) 

oncall 

On-call (date, part, staff_name, received_time, reason) 

overtime 

연장근무 (date, staff_name, start_time, end_time, hours, reason) 

equipment_log 

장비 이력 (date, equipment_name, log_type, description, engineer, start_time, end_time, downtime, status) 

issues 

특이사항·이슈 (date, category, severity, title, content, status) 

worklog_status 

업무일지 상태 (date, status, submitted_by, submitted_at, rejected_by, rejected_to, rejected_at, confirmed_by, confirmed_at) 

 

 

🔄 개발 이력 

초기 구축 

Flask + SQLite 기반 내부망 전용 웹앱 구축 

포트 1000으로 설정 (host='0.0.0.0') 

SHA-256 해시 기반 로그인 인증 

관리자(admin) / 사용자(user) 2단계 권한 

화면 통합 개선 

분산된 입력 화면을 하나의 날짜 기반 통합 작성 페이지로 통합 

아코디언(accordion) UI 기반 업무 입력 구조 적용 

인쇄(A4) 기능 및 업무일지 리스트 화면 구성 

저장 / 제출 워크플로우 개선 

저장 후 제출 가능한 구조로 변경 

제출된 일자만 업무일지 리스트에 표시 

반려/확정/회수 등 상태 기반 워크플로우 반영 

사용자/관리자 권한에 따라 버튼 활성화 규칙 분리 

최신 요구사항 반영 

인수인계 기능 전면 삭제 

대시보드 KPI를 오늘 휴가 / 오늘 On-call / 오늘 연장근무 / 장비 처리중 / 오늘 이슈 / 미해결 이슈 기준으로 재구성 

근무자 현황에서 직종, 비고 삭제 및 근무조 + 파트 + 성명 구조로 변경 

근무조 기본값을 야간으로 변경 

On-call 항목을 파트, 성명, 전화받은 시각, 사유 기준으로 개편 

연장근무에 총시간 자동 계산 항목 추가 

장비이력에 장비명, 시작, 종료 시간 추가 

업무일지 리스트에 작성자 컬럼 추가 

사용자 관리를 사번, 파트, 입사일자, 퇴사일자 기준으로 확장 

재직자 / 퇴사자 / 전체 필터 기능 추가 

사용자 관리 하단에 휴가 코드 관리 기능 추가 

모든 시간 입력 형식을 HH:MM 형식으로 통일 

 

 

💾 데이터 백업 

instance/worklog.db 파일을 복사하면 전체 데이터가 백업됩니다. 

 

 

⚙️ 커스터마이징 

포트 변경: app.py 마지막 줄 port=1000 수정 

보안 키: 운영 환경에서 SECRET_KEY 환경변수로 설정 

초기 관리자 비밀번호: init_db() 내 admin1234 변경 후 instance/worklog.db 삭제 후 재실행 

파트 목록 및 휴가 코드는 운영 정책에 맞춰 추가/수정 가능 

시간 입력은 전 구간 HH:MM 형식으로 통일 

 

 

🌐 GitHub 

저장소: https://github.com/caumcpacs-ai/Radiology-worklog 