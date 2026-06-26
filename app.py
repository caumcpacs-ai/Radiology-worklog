"""
영상의학과 업무일지 웹앱
Flask + SQLite 기반 내부망 전용
"""
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from datetime import datetime, date, timedelta
import sqlite3
import os
import hashlib
import logging
from logging.handlers import TimedRotatingFileHandler

app = Flask(__name__)

app.secret_key = os.environ.get('SECRET_KEY', 'caumc-radiology-2024-!@#internal')

# ── 로그 설정 (날짜별 파일) ──
_LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(_LOG_DIR, exist_ok=True)
_log_handler = TimedRotatingFileHandler(
    os.path.join(_LOG_DIR, 'app.log'),
    when='midnight', interval=1, backupCount=0, encoding='utf-8'
)
_log_handler.suffix = '%Y-%m-%d'
_log_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
_logger = logging.getLogger('worklog')
_logger.setLevel(logging.INFO)
_logger.addHandler(_log_handler)

@app.context_processor
def inject_now():
    def format_hh_mm(hours_float):
        if not hours_float:
            return "0h 00m"
        total_minutes = int(round(hours_float * 60))
        h = total_minutes // 60
        m = total_minutes % 60
        return f"{h}h {m:02d}m"
    return {
        'now': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'format_hh_mm': format_hh_mm
    }

DB_PATH          = os.path.join(os.path.dirname(__file__), 'instance', 'worklog.db')
SPECIAL_EQ_DB    = os.path.join(os.path.dirname(__file__), 'instance', 'special_equipment.db')
RADIATION_DB     = os.path.join(os.path.dirname(__file__), 'instance', 'radiation_device.db')

PARTS = ['GR', 'CT', 'MR', '인터벤션', '간호']

def _calc_hours(t1: str, t2: str) -> float:
    """HH:MM 두 시각의 차이(시간)를 반환. t2 < t1이면 익일로 간주."""
    try:
        sm = int(t1[:2]) * 60 + int(t1[3:5])
        em = int(t2[:2]) * 60 + int(t2[3:5])
        if em < sm:
            em += 24 * 60
        return (em - sm) / 60.0
    except Exception:
        return 0.0
SHIFTS = ['야간', '오전', '종일']

NIGHT_CHECKLIST_ITEMS = [
    {'no':  1, 'name': '접 수',                       'default_remark': ''},
    {'no':  2, 'name': '투시촬영실(1번)',              'default_remark': ''},
    {'no':  3, 'name': '일반촬영실(2,3,4,5번)',        'default_remark': ''},
    {'no':  4, 'name': '초음파실(6번)',                'default_remark': ''},
    {'no':  5, 'name': 'CT 검사실(7,8번)',             'default_remark': ''},
    {'no':  6, 'name': 'MRI 검사실(9번)',              'default_remark': ''},
    {'no':  7, 'name': '진정회복실(10번)',             'default_remark': ''},
    {'no':  8, 'name': '처치실(11번)',                 'default_remark': ''},
    {'no':  9, 'name': '일반촬영실 탈의실',            'default_remark': ''},
    {'no': 10, 'name': '대회의실',                     'default_remark': '빔프로젝터'},
    {'no': 11, 'name': '소회의실',                     'default_remark': ''},
    {'no': 12, 'name': '팀장실',                       'default_remark': ''},
    {'no': 13, 'name': 'PACS실',                       'default_remark': ''},
    {'no': 14, 'name': '탕비실',                       'default_remark': ''},
    {'no': 15, 'name': 'CT 기계실',                    'default_remark': ''},
    {'no': 16, 'name': '여직원 탈의실',                'default_remark': ''},
    {'no': 17, 'name': '남직원 탈의실',                'default_remark': ''},
    {'no': 18, 'name': 'MRI 기계실',                   'default_remark': ''},
    {'no': 19, 'name': 'CT, MRI 탈의실',               'default_remark': ''},
    {'no': 20, 'name': '판독실(신경,두경부)',           'default_remark': ''},
    {'no': 21, 'name': '판독실(흉부,근골격)',           'default_remark': ''},
    {'no': 22, 'name': '판독실(복부,비뇨생식기)',       'default_remark': ''},
    {'no': 23, 'name': '의사당직실',                   'default_remark': ''},
    {'no': 24, 'name': '교수연구실',                   'default_remark': ''},
    {'no': 25, 'name': '의 국',                        'default_remark': ''},
    {'no': 26, 'name': '남자화장실',                   'default_remark': ''},
    {'no': 27, 'name': '여자화장실',                   'default_remark': ''},
]

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_special_eq_db():
    conn = sqlite3.connect(SPECIAL_EQ_DB, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_radiation_db():
    conn = sqlite3.connect(RADIATION_DB, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL")

    # ── 사용자 테이블 ──
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        name TEXT NOT NULL,
        part TEXT DEFAULT '',
        role TEXT DEFAULT 'user',
        created_at TEXT DEFAULT (datetime('now','localtime')),
        hire_date TEXT DEFAULT '',
        retired_date TEXT DEFAULT ''
    )''')

    # ── 근무자 현황 ──
    c.execute('''CREATE TABLE IF NOT EXISTS staff_roster (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        shift TEXT NOT NULL,
        part TEXT DEFAULT '',
        staff_name TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )''')

    # ── 휴가 현황 (신규 스키마: date, staff_name, vacation_code) ──
    # 구 스키마 감지 후 마이그레이션
    try:
        c.execute("SELECT date, vacation_code FROM vacation LIMIT 1")
    except Exception:
        try:
            c.execute("ALTER TABLE vacation RENAME TO vacation_old")
            c.execute('''CREATE TABLE vacation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                part TEXT DEFAULT '',
                staff_name TEXT NOT NULL,
                vacation_code TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )''')
            c.execute("""INSERT INTO vacation(date, staff_name, vacation_code, created_at)
                         SELECT start_date, staff_name, vacation_type, created_at FROM vacation_old""")
        except Exception:
            c.execute('''CREATE TABLE IF NOT EXISTS vacation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                part TEXT DEFAULT '',
                staff_name TEXT NOT NULL,
                vacation_code TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )''')
    # part 컬럼 마이그레이션 (기존 DB 대응)
    try:
        c.execute("SELECT part FROM vacation LIMIT 1")
    except Exception:
        c.execute("ALTER TABLE vacation ADD COLUMN part TEXT DEFAULT ''")

    # ── 휴가 코드 관리 ──
    c.execute('''CREATE TABLE IF NOT EXISTS vacation_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        work_info TEXT DEFAULT '',
        start_time TEXT DEFAULT '',
        end_time TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )''')

    # ── On-call ──
    c.execute('''CREATE TABLE IF NOT EXISTS oncall (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        part TEXT DEFAULT '',
        staff_name TEXT NOT NULL,
        start_time TEXT DEFAULT '',
        end_time TEXT DEFAULT '',
        hours REAL DEFAULT 0,
        reason TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )''')

    # ── 연장근무 ──
    c.execute('''CREATE TABLE IF NOT EXISTS overtime (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        part TEXT DEFAULT '',
        staff_name TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        hours REAL NOT NULL,
        reason TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )''')
    # part 컬럼 마이그레이션 (기존 DB 대응)
    try:
        c.execute("SELECT part FROM overtime LIMIT 1")
    except Exception:
        c.execute("ALTER TABLE overtime ADD COLUMN part TEXT DEFAULT ''")

    # ── 장비 이력 ──
    c.execute('''CREATE TABLE IF NOT EXISTS equipment_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        equipment_name TEXT NOT NULL,
        log_type TEXT NOT NULL,
        description TEXT DEFAULT '',
        engineer TEXT DEFAULT '',
        start_time TEXT DEFAULT '',
        end_time TEXT DEFAULT '',
        downtime TEXT DEFAULT '',
        status TEXT DEFAULT '처리중',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )''')

    # ── 특이사항·이슈 ──
    c.execute('''CREATE TABLE IF NOT EXISTS issues (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        category TEXT NOT NULL,
        severity TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        status TEXT DEFAULT '진행중',
        author TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )''')

    # ── 인수인계 (기존 데이터 보존용, 라우트/UI 없음) ──
    c.execute('''CREATE TABLE IF NOT EXISTS handover (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        shift TEXT NOT NULL,
        from_person TEXT NOT NULL,
        to_person TEXT NOT NULL,
        content TEXT NOT NULL,
        priority TEXT DEFAULT '일반',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )''')

    # ── 업무일지 상태 ──
    c.execute('''CREATE TABLE IF NOT EXISTS worklog_status (
        date TEXT PRIMARY KEY,
        status TEXT DEFAULT '저장',
        submitted_by TEXT DEFAULT '',
        submitted_at TEXT DEFAULT '',
        rejected_by TEXT DEFAULT '',
        rejected_to TEXT DEFAULT '',
        rejected_at TEXT DEFAULT '',
        confirmed_by TEXT DEFAULT '',
        confirmed_at TEXT DEFAULT ''
    )''')

    # ── 야간 체크리스트 ──
    c.execute('''CREATE TABLE IF NOT EXISTS night_checklist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        item_no INTEGER NOT NULL,
        door_lock TEXT DEFAULT '',
        light_off TEXT DEFAULT '',
        hvac TEXT DEFAULT '',
        remark TEXT DEFAULT '',
        check_result TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(date, item_no)
    )''')

    # ── 마이그레이션 ──

    # users: part, hire_date, retired_date
    for col, typedef in [('part', "TEXT DEFAULT ''"), ('hire_date', "TEXT DEFAULT ''"), ('retired_date', "TEXT DEFAULT ''")]:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} {typedef}")
        except Exception:
            pass

    # staff_roster: part
    try:
        c.execute("ALTER TABLE staff_roster ADD COLUMN part TEXT DEFAULT ''")
    except Exception:
        pass

    # oncall: 신규 컬럼 추가 및 기존 데이터 복사
    for col, typedef in [('part', "TEXT DEFAULT ''"), ('received_time', "TEXT DEFAULT ''"), ('reason', "TEXT DEFAULT ''"),
                         ('start_time', "TEXT DEFAULT ''"), ('end_time', "TEXT DEFAULT ''"), ('hours', "REAL DEFAULT 0"),
                         ('arrival_time', "TEXT DEFAULT ''"), ('procedure_start', "TEXT DEFAULT ''"),
                         ('procedure_end', "TEXT DEFAULT ''"), ('departure_time', "TEXT DEFAULT ''")]:
        try:
            c.execute(f"ALTER TABLE oncall ADD COLUMN {col} {typedef}")
        except Exception:
            pass
    try:
        c.execute("UPDATE oncall SET part=modality WHERE (part IS NULL OR part='') AND modality IS NOT NULL")
    except Exception:
        pass
    try:
        c.execute("UPDATE oncall SET reason=note WHERE (reason IS NULL OR reason='') AND note IS NOT NULL")
    except Exception:
        pass
    try:
        c.execute("UPDATE oncall SET start_time=received_time WHERE (start_time IS NULL OR start_time='') AND received_time IS NOT NULL AND received_time!=''")
    except Exception:
        pass
    # start_time → arrival_time, end_time → departure_time 마이그레이션
    try:
        c.execute("UPDATE oncall SET arrival_time=start_time WHERE (arrival_time IS NULL OR arrival_time='') AND start_time IS NOT NULL AND start_time!=''")
    except Exception:
        pass
    try:
        c.execute("UPDATE oncall SET departure_time=end_time WHERE (departure_time IS NULL OR departure_time='') AND end_time IS NOT NULL AND end_time!=''")
    except Exception:
        pass

    # equipment_log: 신규 컬럼 추가 및 기존 데이터 복사
    for col, typedef in [
        ('equipment_name', "TEXT DEFAULT ''"),
        ('start_time', "TEXT DEFAULT ''"),
        ('end_time', "TEXT DEFAULT ''"),
        ('downtime', "TEXT DEFAULT ''"),
    ]:
        try:
            c.execute(f"ALTER TABLE equipment_log ADD COLUMN {col} {typedef}")
        except Exception:
            pass
    try:
        c.execute("UPDATE equipment_log SET equipment_name=equipment WHERE (equipment_name IS NULL OR equipment_name='') AND equipment IS NOT NULL")
    except Exception:
        pass
    try:
        c.execute("UPDATE equipment_log SET downtime=CAST(downtime_hours AS TEXT) WHERE (downtime IS NULL OR downtime='') AND downtime_hours IS NOT NULL")
    except Exception:
        pass

    # worklog_status: confirmed_by, confirmed_at
    for col in ['confirmed_by', 'confirmed_at']:
        try:
            c.execute(f"ALTER TABLE worklog_status ADD COLUMN {col} TEXT DEFAULT ''")
        except Exception:
            pass

    # 기본 관리자 계정
    hashed = hashlib.sha256('admin1234'.encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO users (username, password, name, role) VALUES (?, ?, ?, ?)",
              ('admin', hashed, '관리자', 'admin'))

    conn.commit()
    conn.close()


def init_special_eq_db():
    """특수의료장비 전용 DB 초기화 (instance/special_equipment.db)"""
    os.makedirs(os.path.dirname(SPECIAL_EQ_DB), exist_ok=True)
    conn = get_special_eq_db()
    c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL")
    c.execute('''CREATE TABLE IF NOT EXISTS special_equipment (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        unique_serial TEXT DEFAULT '',
        category TEXT DEFAULT '',
        sn TEXT DEFAULT '',
        equipment_name TEXT NOT NULL,
        manager TEXT DEFAULT '',
        radiographer1 TEXT DEFAULT '',
        radiographer2 TEXT DEFAULT '',
        note TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )''')
    conn.commit()

    # worklog.db에 기존 데이터가 있으면 마이그레이션
    existing = c.execute("SELECT COUNT(*) FROM special_equipment").fetchone()[0]
    if existing == 0 and os.path.exists(DB_PATH):
        try:
            old_conn = sqlite3.connect(DB_PATH)
            old_conn.row_factory = sqlite3.Row
            rows = old_conn.execute("SELECT * FROM special_equipment").fetchall()
            for r in rows:
                c.execute(
                    "INSERT OR IGNORE INTO special_equipment (id,unique_serial,category,sn,equipment_name,manager,radiographer1,radiographer2,note,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (r['id'], r['unique_serial'], r['category'], r['sn'], r['equipment_name'],
                     r['manager'], r['radiographer1'], r['radiographer2'], r['note'], r['created_at']))
            old_conn.close()
            conn.commit()
        except Exception:
            pass
    conn.close()


def init_radiation_db():
    """진단용방사선발생장치 전용 DB 초기화 (instance/radiation_device.db)"""
    os.makedirs(os.path.dirname(RADIATION_DB), exist_ok=True)
    conn = get_radiation_db()
    c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL")
    c.execute('''CREATE TABLE IF NOT EXISTS radiation_device (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT DEFAULT '',
        location TEXT DEFAULT '',
        purpose TEXT DEFAULT '',
        device_type TEXT DEFAULT '',
        model_name TEXT DEFAULT '',
        manufacture_date TEXT DEFAULT '',
        serial_number TEXT DEFAULT '',
        manufacture_country TEXT DEFAULT '',
        manufacturer TEXT DEFAULT '',
        first_use_date TEXT DEFAULT '',
        note TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )''')
    conn.commit()

    # worklog.db에 기존 데이터가 있으면 마이그레이션
    existing = c.execute("SELECT COUNT(*) FROM radiation_device").fetchone()[0]
    if existing == 0 and os.path.exists(DB_PATH):
        try:
            old_conn = sqlite3.connect(DB_PATH)
            old_conn.row_factory = sqlite3.Row
            rows = old_conn.execute("SELECT * FROM radiation_device").fetchall()
            for r in rows:
                c.execute(
                    "INSERT OR IGNORE INTO radiation_device (id,code,location,purpose,device_type,model_name,manufacture_date,serial_number,manufacture_country,manufacturer,first_use_date,note,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (r['id'], r['code'], r['location'], r['purpose'], r['device_type'],
                     r['model_name'], r['manufacture_date'], r['serial_number'],
                     r['manufacture_country'], r['manufacturer'], r['first_use_date'],
                     r['note'], r['created_at']))
            old_conn.close()
            conn.commit()
        except Exception:
            pass
    conn.close()


def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ════════════════════════════════════════════════════
# 인증
# ════════════════════════════════════════════════════
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = hash_pw(request.form['password'])
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=? AND password=?",
                            (username, password)).fetchone()
        conn.close()
        if user:
            session['user'] = username
            session['name'] = user['name']
            session['role'] = user['role']
            return redirect(url_for('dashboard'))
        flash('아이디 또는 비밀번호가 올바르지 않습니다.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ════════════════════════════════════════════════════
# 개인정보 수정
# ════════════════════════════════════════════════════
@app.route('/profile')
@login_required
def profile():
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=?", (session['user'],)).fetchone()
    conn.close()
    return render_template('profile.html', user=user, parts=PARTS)


@app.route('/profile/save', methods=['POST'])
@login_required
def profile_save():
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=?", (session['user'],)).fetchone()
    if not user:
        flash('사용자를 찾을 수 없습니다.', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    new_name = request.form.get('name', '').strip()
    new_part = request.form.get('part', '').strip()
    current_pw = request.form.get('current_password', '').strip()
    new_pw = request.form.get('new_password', '').strip()
    confirm_pw = request.form.get('confirm_password', '').strip()

    if new_name and new_name != user['name']:
        conn.execute("UPDATE users SET name=? WHERE username=?", (new_name, session['user']))
        session['name'] = new_name

    if new_part != (user['part'] or ''):
        conn.execute("UPDATE users SET part=? WHERE username=?", (new_part, session['user']))

    if new_pw:
        if not current_pw:
            flash('현재 비밀번호를 입력하세요.', 'danger')
            conn.close()
            return redirect(url_for('profile'))
        if hash_pw(current_pw) != user['password']:
            flash('현재 비밀번호가 올바르지 않습니다.', 'danger')
            conn.close()
            return redirect(url_for('profile'))
        if new_pw != confirm_pw:
            flash('새 비밀번호가 일치하지 않습니다.', 'danger')
            conn.close()
            return redirect(url_for('profile'))
        conn.execute("UPDATE users SET password=? WHERE username=?", (hash_pw(new_pw), session['user']))

    conn.commit()
    conn.close()
    flash('개인정보가 수정되었습니다.', 'success')
    return redirect(url_for('profile'))


# ════════════════════════════════════════════════════
# 대시보드
# ════════════════════════════════════════════════════
@app.route('/')
@login_required
def dashboard():
    today = date.today().isoformat()
    d1 = (date.today() - timedelta(days=1)).isoformat()
    d2 = (date.today() - timedelta(days=2)).isoformat()
    conn = get_db()

    # 오늘 현황 (섹션 테이블용)
    roster_today    = conn.execute("SELECT * FROM staff_roster WHERE date=? ORDER BY shift, part, id", (today,)).fetchall()
    vacation_today  = conn.execute("SELECT * FROM vacation WHERE date=? ORDER BY part, vacation_code, staff_name", (today,)).fetchall()
    oncall_today    = conn.execute("SELECT * FROM oncall WHERE date=? ORDER BY part", (today,)).fetchall()
    overtime_today  = conn.execute("SELECT * FROM overtime WHERE date=? ORDER BY part, staff_name", (today,)).fetchall()
    equipment_today = conn.execute("SELECT * FROM equipment_log WHERE date=? ORDER BY equipment_name", (today,)).fetchall()
    issues_today    = conn.execute("SELECT * FROM issues WHERE date=? ORDER BY severity, id", (today,)).fetchall()

    # D-1 현황
    vacation_d1  = conn.execute("SELECT * FROM vacation WHERE date=? ORDER BY part, vacation_code, staff_name", (d1,)).fetchall()
    oncall_d1    = conn.execute("SELECT * FROM oncall WHERE date=? ORDER BY part", (d1,)).fetchall()
    overtime_d1  = conn.execute("SELECT * FROM overtime WHERE date=? ORDER BY part, staff_name", (d1,)).fetchall()
    equipment_d1 = conn.execute("SELECT * FROM equipment_log WHERE date=? ORDER BY equipment_name", (d1,)).fetchall()
    issues_d1    = conn.execute("SELECT * FROM issues WHERE date=? ORDER BY severity, id", (d1,)).fetchall()

    # D-2 현황
    vacation_d2  = conn.execute("SELECT * FROM vacation WHERE date=? ORDER BY part, vacation_code, staff_name", (d2,)).fetchall()
    oncall_d2    = conn.execute("SELECT * FROM oncall WHERE date=? ORDER BY part", (d2,)).fetchall()
    overtime_d2  = conn.execute("SELECT * FROM overtime WHERE date=? ORDER BY part, staff_name", (d2,)).fetchall()
    equipment_d2 = conn.execute("SELECT * FROM equipment_log WHERE date=? ORDER BY equipment_name", (d2,)).fetchall()
    issues_d2    = conn.execute("SELECT * FROM issues WHERE date=? ORDER BY severity, id", (d2,)).fetchall()

    issues_open_rows  = conn.execute("SELECT * FROM issues WHERE status='진행중' ORDER BY severity, date DESC LIMIT 10").fetchall()
    equip_active_rows = conn.execute("SELECT * FROM equipment_log WHERE status='처리중' ORDER BY date DESC LIMIT 10").fetchall()

    # D-1 근무자 현황
    roster_d1 = conn.execute("SELECT * FROM staff_roster WHERE date=? ORDER BY shift, part, id", (d1,)).fetchall()

    conn.close()

    # 근무자 현황: shift+part 그룹화 (오늘)
    roster_grouped = {}
    shift_order = {'야간': 0, '오전': 1, '종일': 2}
    for r in roster_today:
        key = (r['shift'], r['part'])
        roster_grouped.setdefault(key, []).append(r['staff_name'])
    roster_grouped_sorted = sorted(roster_grouped.items(), key=lambda x: (shift_order.get(x[0][0], 9), x[0][1]))

    # 근무자 현황: shift+part 그룹화 (D-1)
    roster_grouped_d1 = {}
    for r in roster_d1:
        key = (r['shift'], r['part'])
        roster_grouped_d1.setdefault(key, []).append(r['staff_name'])
    roster_grouped_sorted_d1 = sorted(roster_grouped_d1.items(), key=lambda x: (shift_order.get(x[0][0], 9), x[0][1]))

    return render_template('dashboard.html',
        today=today, d1=d1, d2=d2,
        roster_grouped=roster_grouped_sorted,
        roster_grouped_d1=roster_grouped_sorted_d1,
        roster_today=roster_today,
        vacation_today=vacation_today,
        oncall_today=oncall_today,
        overtime_today=overtime_today,
        equipment_today=equipment_today,
        issues_today=issues_today,
        issues_open_rows=issues_open_rows,
        equip_active_rows=equip_active_rows,
        vacation_d1=vacation_d1, vacation_d2=vacation_d2,
        oncall_d1=oncall_d1, oncall_d2=oncall_d2,
        overtime_d1=overtime_d1, overtime_d2=overtime_d2,
        equipment_d1=equipment_d1, equipment_d2=equipment_d2,
        issues_d1=issues_d1, issues_d2=issues_d2,
        roster_d1=roster_d1)


# ════════════════════════════════════════════════════
# 작성 페이지 (날짜별 통합 입력)
# ════════════════════════════════════════════════════
@app.route('/write')
@login_required
def write():
    sel = request.args.get('date', date.today().isoformat())
    conn = get_db()
    ws = conn.execute("SELECT * FROM worklog_status WHERE date=?", (sel,)).fetchone()

    data = {
        'roster':    conn.execute("SELECT * FROM staff_roster WHERE date=? ORDER BY shift, part, id", (sel,)).fetchall(),
        'vacation':  conn.execute("SELECT * FROM vacation WHERE date=? ORDER BY part, vacation_code, staff_name", (sel,)).fetchall(),
        'oncall':    conn.execute("SELECT * FROM oncall WHERE date=? ORDER BY part", (sel,)).fetchall(),
        'overtime':  conn.execute("SELECT * FROM overtime WHERE date=? ORDER BY part, staff_name", (sel,)).fetchall(),
        'equipment': conn.execute("SELECT * FROM equipment_log WHERE date=? ORDER BY equipment_name", (sel,)).fetchall(),
        'issues':    conn.execute("SELECT * FROM issues WHERE date=? ORDER BY severity, id", (sel,)).fetchall(),
    }

    users_list = conn.execute(
        "SELECT name FROM users WHERE retired_date='' OR retired_date IS NULL ORDER BY name",
        ).fetchall()
    vacation_codes_list = conn.execute("SELECT * FROM vacation_codes ORDER BY code").fetchall()

    checklist_saved = conn.execute(
        "SELECT * FROM night_checklist WHERE date=? ORDER BY item_no", (sel,)).fetchall()
    conn.close()
    wl_status = ws['status'] if ws else None
    submitted_by = ws['submitted_by'] if ws else ''
    checklist_map = {r['item_no']: r for r in checklist_saved}
    night_checklist_items = []
    for _item in NIGHT_CHECKLIST_ITEMS:
        _saved = checklist_map.get(_item['no'])
        night_checklist_items.append({
            'no':           _item['no'],
            'name':         _item['name'],
            'door_lock':    _saved['door_lock']    if _saved else '-',
            'light_off':    _saved['light_off']    if _saved else '-',
            'hvac':         _saved['hvac']         if _saved else '-',
            'remark':       _saved['remark']       if _saved else _item['default_remark'],
            'check_result': _saved['check_result'] if _saved else '-',
        })
    return render_template('write.html',
        sel=sel, wl_status=wl_status, submitted_by=submitted_by,
        parts=PARTS, shifts=SHIFTS,
        users_list=users_list, vacation_codes_list=vacation_codes_list,
        night_checklist_items=night_checklist_items,
        **data)


def is_worklog_locked(date_str):
    conn = get_db()
    ws = conn.execute("SELECT status FROM worklog_status WHERE date=?", (date_str,)).fetchone()
    conn.close()
    return ws and ws['status'] in ('제출', '확정')


# ── 근무자 현황 ──
@app.route('/write/roster/add', methods=['POST'])
@login_required
def write_roster_add():
    d = request.form['date']
    if is_worklog_locked(d):
        flash('제출된 상태에서는 수정이 불가합니다.', 'danger')
        return redirect(url_for('write', date=d))
    conn = get_db()
    conn.execute("INSERT INTO staff_roster (date,shift,part,staff_name) VALUES (?,?,?,?)",
        (d, request.form['shift'], request.form.get('part', ''), request.form['staff_name']))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/roster/edit/<int:id>', methods=['POST'])
@login_required
def write_roster_edit(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM staff_roster WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    if is_worklog_locked(d):
        conn.close()
        flash('제출된 상태에서는 수정이 불가합니다.', 'danger')
        return redirect(url_for('write', date=d))
    conn.execute("UPDATE staff_roster SET shift=?,part=?,staff_name=? WHERE id=?",
        (request.form['shift'], request.form.get('part', ''), request.form['staff_name'], id))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/roster/delete/<int:id>', methods=['POST'])
@login_required
def write_roster_delete(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM staff_roster WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    if is_worklog_locked(d):
        conn.close()
        flash('제출된 상태에서는 수정이 불가합니다.', 'danger')
        return redirect(url_for('write', date=d))
    conn.execute("DELETE FROM staff_roster WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


# ── 휴가 현황 ──
@app.route('/write/vacation/add', methods=['POST'])
@login_required
def write_vacation_add():
    d = request.form['date']
    if is_worklog_locked(d):
        flash('제출된 상태에서는 수정이 불가합니다.', 'danger')
        return redirect(url_for('write', date=d))
    conn = get_db()
    conn.execute("INSERT INTO vacation (date,part,staff_name,vacation_code) VALUES (?,?,?,?)",
        (d, request.form.get('part',''), request.form['staff_name'], request.form['vacation_code']))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/vacation/edit/<int:id>', methods=['POST'])
@login_required
def write_vacation_edit(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM vacation WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    if is_worklog_locked(d):
        conn.close()
        flash('제출된 상태에서는 수정이 불가합니다.', 'danger')
        return redirect(url_for('write', date=d))
    conn.execute("UPDATE vacation SET part=?,staff_name=?,vacation_code=? WHERE id=?",
        (request.form.get('part',''), request.form['staff_name'], request.form['vacation_code'], id))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/vacation/delete/<int:id>', methods=['POST'])
@login_required
def write_vacation_delete(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM vacation WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    if is_worklog_locked(d):
        conn.close()
        flash('제출된 상태에서는 수정이 불가합니다.', 'danger')
        return redirect(url_for('write', date=d))
    conn.execute("DELETE FROM vacation WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


# ── On-call ──
@app.route('/write/oncall/add', methods=['POST'])
@login_required
def write_oncall_add():
    d = request.form['date']
    if is_worklog_locked(d):
        flash('제출된 상태에서는 수정이 불가합니다.', 'danger')
        return redirect(url_for('write', date=d))
    part        = request.form.get('part', '')
    staff_name  = request.form.get('staff_name', '')
    arrival     = request.form.get('arrival_time', '')
    proc_start  = request.form.get('procedure_start', '')
    proc_end    = request.form.get('procedure_end', '')
    departure   = request.form.get('departure_time', '')
    h           = _calc_hours(arrival, departure)
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO oncall (date,part,staff_name,arrival_time,procedure_start,procedure_end,departure_time,hours,reason,modality) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (d, part, staff_name, arrival, proc_start, proc_end, departure, h, request.form.get('reason', ''), part))
        conn.commit()
        _logger.info("oncall add date=%s part=%s staff=%s by=%s", d, part, staff_name, session.get('name'))
    except Exception as e:
        flash(f'저장 오류: {str(e)}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/oncall/edit/<int:id>', methods=['POST'])
@login_required
def write_oncall_edit(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM oncall WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    if is_worklog_locked(d):
        conn.close()
        flash('제출된 상태에서는 수정이 불가합니다.', 'danger')
        return redirect(url_for('write', date=d))
    arrival     = request.form.get('arrival_time', '')
    proc_start  = request.form.get('procedure_start', '')
    proc_end    = request.form.get('procedure_end', '')
    departure   = request.form.get('departure_time', '')
    h           = _calc_hours(arrival, departure)
    try:
        conn.execute(
            "UPDATE oncall SET part=?,staff_name=?,arrival_time=?,procedure_start=?,procedure_end=?,departure_time=?,hours=?,reason=? WHERE id=?",
            (request.form.get('part', ''), request.form.get('staff_name', ''),
             arrival, proc_start, proc_end, departure, h, request.form.get('reason', ''), id))
        conn.commit()
        _logger.info("oncall edit id=%d by=%s", id, session.get('name'))
    except Exception as e:
        flash(f'저장 오류: {str(e)}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/oncall/delete/<int:id>', methods=['POST'])
@login_required
def write_oncall_delete(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM oncall WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    if is_worklog_locked(d):
        conn.close()
        flash('제출된 상태에서는 수정이 불가합니다.', 'danger')
        return redirect(url_for('write', date=d))
    conn.execute("DELETE FROM oncall WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


# ── 연장근무 ──
@app.route('/write/overtime/add', methods=['POST'])
@login_required
def write_overtime_add():
    d = request.form['date']
    if is_worklog_locked(d):
        flash('제출된 상태에서는 수정이 불가합니다.', 'danger')
        return redirect(url_for('write', date=d))
    st = request.form['start_time']
    et = request.form['end_time']
    try:
        h = (datetime.strptime(et, '%H:%M') - datetime.strptime(st, '%H:%M')).seconds / 3600.0
    except Exception:
        h = 0.0
    conn = get_db()
    conn.execute("INSERT INTO overtime (date,part,staff_name,start_time,end_time,hours,reason) VALUES (?,?,?,?,?,?,?)",
        (d, request.form.get('part',''), request.form['staff_name'], st, et, h, request.form['reason']))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/overtime/edit/<int:id>', methods=['POST'])
@login_required
def write_overtime_edit(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM overtime WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    if is_worklog_locked(d):
        conn.close()
        flash('제출된 상태에서는 수정이 불가합니다.', 'danger')
        return redirect(url_for('write', date=d))
    st = request.form['start_time']
    et = request.form['end_time']
    try:
        h = (datetime.strptime(et, '%H:%M') - datetime.strptime(st, '%H:%M')).seconds / 3600.0
    except Exception:
        h = 0.0
    conn.execute("UPDATE overtime SET part=?,staff_name=?,start_time=?,end_time=?,hours=?,reason=? WHERE id=?",
        (request.form.get('part',''), request.form['staff_name'], st, et, h, request.form['reason'], id))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/overtime/delete/<int:id>', methods=['POST'])
@login_required
def write_overtime_delete(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM overtime WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    if is_worklog_locked(d):
        conn.close()
        flash('제출된 상태에서는 수정이 불가합니다.', 'danger')
        return redirect(url_for('write', date=d))
    conn.execute("DELETE FROM overtime WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


# ── 장비 이력 ──
@app.route('/write/equipment/add', methods=['POST'])
@login_required
def write_equipment_add():
    d = request.form['date']
    if is_worklog_locked(d):
        flash('제출된 상태에서는 수정이 불가합니다.', 'danger')
        return redirect(url_for('write', date=d))
    equipment_name = request.form['equipment_name']
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO equipment_log (date,equipment_name,log_type,description,engineer,start_time,end_time,downtime,status,equipment) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (d, equipment_name, request.form['log_type'],
             request.form.get('description', ''), request.form.get('engineer', ''),
             request.form.get('start_time', ''), request.form.get('end_time', ''),
             request.form.get('downtime', ''), request.form['status'], equipment_name))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/equipment/edit/<int:id>', methods=['POST'])
@login_required
def write_equipment_edit(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM equipment_log WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    if is_worklog_locked(d):
        conn.close()
        flash('제출된 상태에서는 수정이 불가합니다.', 'danger')
        return redirect(url_for('write', date=d))
    conn.execute("UPDATE equipment_log SET equipment_name=?,log_type=?,description=?,engineer=?,start_time=?,end_time=?,downtime=?,status=? WHERE id=?",
        (request.form['equipment_name'], request.form['log_type'],
         request.form.get('description', ''), request.form.get('engineer', ''),
         request.form.get('start_time', ''), request.form.get('end_time', ''),
         request.form.get('downtime', ''), request.form['status'], id))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/equipment/delete/<int:id>', methods=['POST'])
@login_required
def write_equipment_delete(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM equipment_log WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    if is_worklog_locked(d):
        conn.close()
        flash('제출된 상태에서는 수정이 불가합니다.', 'danger')
        return redirect(url_for('write', date=d))
    conn.execute("DELETE FROM equipment_log WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


# ── 특이사항·이슈 ──
@app.route('/write/issue/add', methods=['POST'])
@login_required
def write_issue_add():
    d = request.form['date']
    if is_worklog_locked(d):
        flash('제출된 상태에서는 수정이 불가합니다.', 'danger')
        return redirect(url_for('write', date=d))
    conn = get_db()
    try:
        conn.execute("INSERT INTO issues (date,category,severity,title,content,status,author) VALUES (?,?,?,?,?,?,?)",
            (d, request.form['category'], request.form['severity'],
             request.form['title'], request.form['content'],
             request.form.get('status', '진행중'), session['name']))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/issue/edit/<int:id>', methods=['POST'])
@login_required
def write_issue_edit(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM issues WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    if is_worklog_locked(d):
        conn.close()
        flash('제출된 상태에서는 수정이 불가합니다.', 'danger')
        return redirect(url_for('write', date=d))
    conn.execute("UPDATE issues SET category=?,severity=?,title=?,content=?,status=? WHERE id=?",
        (request.form['category'], request.form['severity'],
         request.form['title'], request.form['content'], request.form['status'], id))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/issue/delete/<int:id>', methods=['POST'])
@login_required
def write_issue_delete(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM issues WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    if is_worklog_locked(d):
        conn.close()
        flash('제출된 상태에서는 수정이 불가합니다.', 'danger')
        return redirect(url_for('write', date=d))
    conn.execute("DELETE FROM issues WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


# ── 날짜 초기화 (섹션 데이터만 삭제, worklog_status 유지) ──
@app.route('/write/reset/<date_str>')
@login_required
def write_reset(date_str):
    conn = get_db()
    ws = conn.execute("SELECT status FROM worklog_status WHERE date=?", (date_str,)).fetchone()
    wl_status = ws['status'] if ws else None
    # 관리자는 항상 가능, 일반 사용자는 작성(미저장) 상태일 때만 가능
    if session.get('role') != 'admin' and wl_status is not None:
        flash('초기화 권한이 없습니다.', 'danger')
        conn.close()
        return redirect(url_for('write', date=date_str))
    conn.execute("DELETE FROM staff_roster   WHERE date=?", (date_str,))
    conn.execute("DELETE FROM vacation        WHERE date=?", (date_str,))
    conn.execute("DELETE FROM oncall          WHERE date=?", (date_str,))
    conn.execute("DELETE FROM overtime        WHERE date=?", (date_str,))
    conn.execute("DELETE FROM equipment_log   WHERE date=?", (date_str,))
    conn.execute("DELETE FROM issues          WHERE date=?", (date_str,))
    conn.execute("DELETE FROM night_checklist WHERE date=?", (date_str,))
    conn.commit(); conn.close()
    flash(f'{date_str} 날짜의 모든 데이터가 초기화되었습니다.', 'info')
    return redirect(url_for('write', date=date_str))


# ── 업무일지 삭제 (섹션 데이터 + worklog_status 전체 삭제) ──
@app.route('/write/delete/<date_str>', methods=['POST'])
@login_required
def write_delete(date_str):
    conn = get_db()
    ws = conn.execute("SELECT status FROM worklog_status WHERE date=?", (date_str,)).fetchone()
    wl_status = ws['status'] if ws else None
    if wl_status not in (None, '저장'):
        flash('작성 또는 저장 상태일 때만 삭제할 수 있습니다.', 'danger')
        conn.close()
        return redirect(url_for('write', date=date_str))
    conn.execute("DELETE FROM staff_roster   WHERE date=?", (date_str,))
    conn.execute("DELETE FROM vacation        WHERE date=?", (date_str,))
    conn.execute("DELETE FROM oncall          WHERE date=?", (date_str,))
    conn.execute("DELETE FROM overtime        WHERE date=?", (date_str,))
    conn.execute("DELETE FROM equipment_log   WHERE date=?", (date_str,))
    conn.execute("DELETE FROM issues          WHERE date=?", (date_str,))
    conn.execute("DELETE FROM night_checklist WHERE date=?", (date_str,))
    conn.execute("DELETE FROM worklog_status  WHERE date=?", (date_str,))
    conn.commit(); conn.close()
    flash(f'{date_str} 업무일지가 삭제되었습니다.', 'success')
    return redirect(url_for('worklog_list'))


# ── 야간 체크리스트 저장 ──
@app.route('/write/night_checklist/save', methods=['POST'])
@login_required
def write_night_checklist_save():
    d = request.form['date']
    if is_worklog_locked(d):
        flash('제출된 상태에서는 수정이 불가합니다.', 'danger')
        return redirect(url_for('write', date=d))
    conn = get_db()
    for item in NIGHT_CHECKLIST_ITEMS:
        i = item['no']
        conn.execute(
            """INSERT OR REPLACE INTO night_checklist
               (date, item_no, door_lock, light_off, hvac, remark, check_result)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (d, i,
             request.form.get(f'door_lock_{i}', ''),
             request.form.get(f'light_off_{i}', ''),
             request.form.get(f'hvac_{i}', ''),
             request.form.get(f'remark_{i}', ''),
             request.form.get(f'check_result_{i}', '')))
    conn.commit(); conn.close()
    flash('야간 체크리스트가 저장되었습니다.', 'success')
    return redirect(url_for('write', date=d))


# ════════════════════════════════════════════════════
# 업무일지 저장 / 제출 / 회수 / 반려 / 확정
# ════════════════════════════════════════════════════
@app.route('/worklog/save/<date_str>', methods=['POST'])
@login_required
def worklog_save(date_str):
    conn = get_db()
    ws = conn.execute("SELECT status FROM worklog_status WHERE date=?", (date_str,)).fetchone()
    if ws and ws['status'] in ('제출', '확정'):
        flash('해당일자의 업무일지가 제출되었습니다. 업무일지 리스트에서 확인하시기 바랍니다.', 'warning')
        conn.close()
        return redirect(url_for('write', date=date_str))
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute("""INSERT OR REPLACE INTO worklog_status
        (date, status, submitted_by, submitted_at, rejected_by, rejected_to, rejected_at, confirmed_by, confirmed_at)
        VALUES (?, '저장', ?, ?, '', '', '', '', '')""",
        (date_str, session['user'], now))
    conn.commit(); conn.close()
    flash(f'{date_str} 업무일지가 저장되었습니다.', 'success')
    return redirect(url_for('write', date=date_str))


@app.route('/worklog/submit/<date_str>', methods=['POST'])
@login_required
def worklog_submit(date_str):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    conn.execute("""INSERT OR REPLACE INTO worklog_status
        (date, status, submitted_by, submitted_at, rejected_by, rejected_to, rejected_at, confirmed_by, confirmed_at)
        VALUES (?, '제출', ?, ?, '', '', '', '', '')""",
        (date_str, session['user'], now))
    conn.commit(); conn.close()
    flash(f'{date_str} 업무일지가 제출되었습니다.', 'success')
    return redirect(url_for('worklog_list'))


@app.route('/worklog/withdraw/<date_str>', methods=['POST'])
@login_required
def worklog_withdraw(date_str):
    conn = get_db()
    ws = conn.execute("SELECT submitted_by FROM worklog_status WHERE date=?", (date_str,)).fetchone()
    if ws and (ws['submitted_by'] == session['user'] or session.get('role') == 'admin'):
        conn.execute("UPDATE worklog_status SET status='저장' WHERE date=?", (date_str,))
        conn.commit()
        flash(f'{date_str} 업무일지가 회수되어 저장 상태로 변경되었습니다.', 'info')
    conn.close()
    return redirect(url_for('worklog_list'))


@app.route('/worklog/reject/<date_str>', methods=['POST'])
@login_required
def worklog_reject(date_str):
    if session.get('role') != 'admin':
        flash('관리자만 반려할 수 있습니다.', 'danger')
        return redirect(url_for('worklog_list'))
    target_user = request.form.get('target_user', '')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    conn.execute("UPDATE worklog_status SET status='반려', rejected_by=?, rejected_to=?, rejected_at=? WHERE date=?",
        (session['name'], target_user, now, date_str))
    conn.commit(); conn.close()
    flash(f'{date_str} 업무일지가 반려되었습니다.', 'warning')
    return redirect(url_for('worklog_list'))


@app.route('/worklog/confirm/<date_str>', methods=['POST'])
@login_required
def worklog_confirm(date_str):
    if session.get('role') != 'admin':
        return redirect(url_for('worklog_list'))
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    conn.execute("UPDATE worklog_status SET status='확정', confirmed_by=?, confirmed_at=? WHERE date=?",
        (session['name'], now, date_str))
    conn.commit(); conn.close()
    flash(f'{date_str} 업무일지가 확정되었습니다.', 'success')
    return redirect(url_for('worklog_list'))


@app.route('/worklog/unconfirm/<date_str>', methods=['POST'])
@login_required
def worklog_unconfirm(date_str):
    if session.get('role') != 'admin':
        return redirect(url_for('worklog_list'))
    conn = get_db()
    conn.execute("UPDATE worklog_status SET status='제출', confirmed_by='', confirmed_at='' WHERE date=?",
        (date_str,))
    conn.commit(); conn.close()
    flash(f'{date_str} 업무일지 확정이 취소되었습니다.', 'info')
    return redirect(url_for('worklog_list'))


# ════════════════════════════════════════════════════
# 업무일지 리스트
# ════════════════════════════════════════════════════
@app.route('/worklog')
@login_required
def worklog_list():
    date_from = request.args.get('date_from', '')
    date_to   = request.args.get('date_to', '')
    conn = get_db()

    query = "SELECT * FROM worklog_status WHERE 1=1"
    params = []
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)
    query += " ORDER BY date DESC"
    statuses = conn.execute(query, params).fetchall()

    if session.get('role') == 'admin':
        users = conn.execute("SELECT username, name FROM users ORDER BY name").fetchall()
    else:
        users = []

    all_users = conn.execute("SELECT username, name FROM users").fetchall()
    user_map = {u['username']: u['name'] for u in all_users}

    logs = []
    for ws in statuses:
        d = ws['date']
        sb = ws['submitted_by'] or ''
        logs.append({
            'date':              d,
            'roster':            conn.execute("SELECT COUNT(*) as c FROM staff_roster WHERE date=?", (d,)).fetchone()['c'],
            'vacation':          conn.execute("SELECT COUNT(*) as c FROM vacation WHERE date=?", (d,)).fetchone()['c'],
            'oncall':            conn.execute("SELECT COUNT(*) as c FROM oncall WHERE date=?", (d,)).fetchone()['c'],
            'overtime':          conn.execute("SELECT COUNT(*) as c FROM overtime WHERE date=?", (d,)).fetchone()['c'],
            'equipment':         conn.execute("SELECT COUNT(*) as c FROM equipment_log WHERE date=?", (d,)).fetchone()['c'],
            'issues':            conn.execute("SELECT COUNT(*) as c FROM issues WHERE date=?", (d,)).fetchone()['c'],
            'wl_status':         ws['status'],
            'submitted_by':      sb,
            'submitted_by_name': user_map.get(sb, sb),
            'rejected_by':       ws['rejected_by'] or '',
            'rejected_to':       ws['rejected_to'] or '',
            'confirmed_by':      ws['confirmed_by'] or '',
        })
    conn.close()
    return render_template('worklog_list.html', logs=logs, users=users,
                           date_from=date_from, date_to=date_to)


# ════════════════════════════════════════════════════
# On-call 리스트 페이지
# ════════════════════════════════════════════════════
@app.route('/oncall-list')
@login_required
def oncall_list():
    date_from  = request.args.get('date_from', '')
    date_to    = request.args.get('date_to', '')
    staff_name = request.args.get('staff_name', '')

    conn  = get_db()
    query = "SELECT * FROM oncall WHERE 1=1"
    params = []
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)
    if staff_name:
        query += " AND staff_name = ?"
        params.append(staff_name)
    query += " ORDER BY date DESC, id"
    rows = conn.execute(query, params).fetchall()

    # users 테이블 이름 + oncall 테이블에 실제 존재하는 이름 합집합 (가나다순)
    db_names = {r['name'] for r in conn.execute(
        "SELECT name FROM users WHERE (retired_date IS NULL OR retired_date='')"
    ).fetchall()}
    actual_names = {r['staff_name'] for r in conn.execute(
        "SELECT DISTINCT staff_name FROM oncall WHERE staff_name != ''"
    ).fetchall()}
    names = sorted(db_names | actual_names)
    conn.close()
    return render_template('oncall_list.html',
                           rows=rows, names=names,
                           date_from=date_from, date_to=date_to,
                           staff_name=staff_name)


# ════════════════════════════════════════════════════
# 연장근무 리스트 페이지
# ════════════════════════════════════════════════════
@app.route('/overtime-list')
@login_required
def overtime_list():
    date_from  = request.args.get('date_from', '')
    date_to    = request.args.get('date_to', '')
    staff_name = request.args.get('staff_name', '')

    conn  = get_db()
    query = "SELECT * FROM overtime WHERE 1=1"
    params = []
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)
    if staff_name:
        query += " AND staff_name = ?"
        params.append(staff_name)
    query += " ORDER BY date DESC, id"
    rows = conn.execute(query, params).fetchall()

    # users 테이블 이름 + overtime 테이블에 실제 존재하는 이름 합집합 (가나다순)
    db_names = {r['name'] for r in conn.execute(
        "SELECT name FROM users WHERE (retired_date IS NULL OR retired_date='')"
    ).fetchall()}
    actual_names = {r['staff_name'] for r in conn.execute(
        "SELECT DISTINCT staff_name FROM overtime WHERE staff_name != ''"
    ).fetchall()}
    names = sorted(db_names | actual_names)

    # 총 연장근무 시간 합계
    total_hours = sum(r['hours'] for r in rows if r['hours'])
    conn.close()
    return render_template('overtime_list.html',
                           rows=rows, names=names,
                           date_from=date_from, date_to=date_to,
                           staff_name=staff_name, total_hours=total_hours)


# ════════════════════════════════════════════════════
# 특수의료장비현황 페이지
# ════════════════════════════════════════════════════
@app.route('/special-equipment')
@login_required
def special_equipment_list():
    conn = get_special_eq_db()
    special_equips = conn.execute(
        "SELECT * FROM special_equipment ORDER BY category, equipment_name"
    ).fetchall()
    conn.close()
    return render_template('special_equipment.html', special_equips=special_equips)


# ════════════════════════════════════════════════════
# 진단용방사선발생장치현황 페이지
# ════════════════════════════════════════════════════
@app.route('/radiation-device')
@login_required
def radiation_device_list():
    conn = get_radiation_db()
    radiation_devs = conn.execute(
        "SELECT * FROM radiation_device ORDER BY id"
    ).fetchall()
    conn.close()
    return render_template('radiation_device.html', radiation_devs=radiation_devs)


# ════════════════════════════════════════════════════
# 사용자 관리 (관리자 전용)
# ════════════════════════════════════════════════════
@app.route('/users')
@login_required
def users():
    f = request.args.get('filter', '재직자')
    conn = get_db()
    if f == '퇴사자':
        rows = conn.execute(
            "SELECT * FROM users WHERE retired_date != '' AND retired_date IS NOT NULL ORDER BY username"
        ).fetchall()
    elif f == '전체':
        rows = conn.execute("SELECT * FROM users ORDER BY username").fetchall()
    else:  # 재직자 (기본)
        rows = conn.execute(
            "SELECT * FROM users WHERE retired_date='' OR retired_date IS NULL ORDER BY username"
        ).fetchall()
    vacation_codes = conn.execute("SELECT * FROM vacation_codes ORDER BY code").fetchall()
    conn.close()
    return render_template('users.html', rows=rows, vacation_codes=vacation_codes, current_filter=f, parts=PARTS)


@app.route('/users/add', methods=['POST'])
@login_required
def user_add():
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (username, password, name, part, role, hire_date, retired_date) VALUES (?,?,?,?,?,?,?)",
            (request.form['username'], hash_pw(request.form['password']),
             request.form['name'], request.form.get('part', ''),
             request.form.get('role', 'user'),
             request.form.get('hire_date', ''), request.form.get('retired_date', '')))
        conn.commit()
        flash('사용자가 추가되었습니다.', 'success')
    except sqlite3.IntegrityError:
        flash('이미 존재하는 사번입니다.', 'danger')
    conn.close()
    return redirect(url_for('users'))


@app.route('/users/edit/<int:id>', methods=['POST'])
@login_required
def user_edit(id):
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    conn = get_db()
    conn.execute(
        "UPDATE users SET name=?, part=?, role=?, hire_date=?, retired_date=? WHERE id=?",
        (request.form['name'], request.form.get('part', ''),
         request.form.get('role', 'user'),
         request.form.get('hire_date', ''), request.form.get('retired_date', ''), id))
    conn.commit(); conn.close()
    flash('사용자 정보가 수정되었습니다.', 'success')
    return redirect(url_for('users', filter=request.form.get('current_filter', '재직자')))


@app.route('/users/delete/<int:id>', methods=['POST'])
@login_required
def user_delete(id):
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect(url_for('users'))


@app.route('/users/change_password/<int:id>', methods=['POST'])
@login_required
def user_change_password(id):
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE id=?", (id,)).fetchone()
    conn.close()
    if not u:
        flash('사용자를 찾을 수 없습니다.', 'danger')
        return redirect(url_for('users'))
    # 관리자는 모든 사용자, 일반 사용자는 본인만 변경 가능
    if session.get('role') != 'admin' and session.get('user') != u['username']:
        flash('권한이 없습니다.', 'danger')
        return redirect(url_for('users'))
    new_pw = request.form.get('new_password', '').strip()
    confirm_pw = request.form.get('confirm_password', '').strip()
    if not new_pw:
        flash('새 비밀번호를 입력하세요.', 'danger')
        return redirect(url_for('users', filter=request.form.get('current_filter', '재직자')))
    if new_pw != confirm_pw:
        flash('비밀번호가 일치하지 않습니다.', 'danger')
        return redirect(url_for('users', filter=request.form.get('current_filter', '재직자')))
    conn = get_db()
    conn.execute("UPDATE users SET password=? WHERE id=?", (hash_pw(new_pw), id))
    conn.commit(); conn.close()
    flash('비밀번호가 변경되었습니다.', 'success')
    return redirect(url_for('users', filter=request.form.get('current_filter', '재직자')))


# ── 휴가 코드 관리 ──
@app.route('/users/vacation_code/add', methods=['POST'])
@login_required
def vacation_code_add():
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO vacation_codes (code, work_info, start_time, end_time) VALUES (?,?,?,?)",
            (request.form['code'], request.form.get('work_info', ''),
             request.form.get('start_time', ''), request.form.get('end_time', '')))
        conn.commit()
        flash('휴가 코드가 추가되었습니다.', 'success')
    except sqlite3.IntegrityError:
        flash('이미 존재하는 코드입니다.', 'danger')
    conn.close()
    return redirect(url_for('users'))


@app.route('/users/vacation_code/edit/<int:id>', methods=['POST'])
@login_required
def vacation_code_edit(id):
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    conn = get_db()
    conn.execute(
        "UPDATE vacation_codes SET code=?, work_info=?, start_time=?, end_time=? WHERE id=?",
        (request.form['code'], request.form.get('work_info', ''),
         request.form.get('start_time', ''), request.form.get('end_time', ''), id))
    conn.commit(); conn.close()
    flash('휴가 코드가 수정되었습니다.', 'success')
    return redirect(url_for('users'))


@app.route('/users/vacation_code/delete/<int:id>', methods=['POST'])
@login_required
def vacation_code_delete(id):
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    conn = get_db()
    conn.execute("DELETE FROM vacation_codes WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect(url_for('users'))


# ════════════════════════════════════════════════════
# 인쇄 뷰
# ════════════════════════════════════════════════════
@app.route('/print/<date_str>')
@login_required
def print_view(date_str):
    conn = get_db()
    data = {
        'roster':    conn.execute("SELECT * FROM staff_roster WHERE date=? ORDER BY shift, part, id", (date_str,)).fetchall(),
        'vacation':  conn.execute("SELECT * FROM vacation WHERE date=? ORDER BY part, vacation_code, staff_name", (date_str,)).fetchall(),
        'oncall':    conn.execute("SELECT * FROM oncall WHERE date=? ORDER BY part", (date_str,)).fetchall(),
        'overtime':  conn.execute("SELECT * FROM overtime WHERE date=? ORDER BY part, staff_name", (date_str,)).fetchall(),
        'equipment': conn.execute("SELECT * FROM equipment_log WHERE date=? ORDER BY equipment_name", (date_str,)).fetchall(),
        'issues':    conn.execute("SELECT * FROM issues WHERE date=? ORDER BY severity, id", (date_str,)).fetchall(),
    }
    checklist_saved = conn.execute(
        "SELECT * FROM night_checklist WHERE date=? ORDER BY item_no", (date_str,)).fetchall()
    conn.close()

    roster_grouped = {}
    shift_order = {'야간': 0, '오전': 1, '종일': 2}
    for r in data['roster']:
        key = (r['shift'], r['part'])
        roster_grouped.setdefault(key, []).append(r['staff_name'])
    roster_grouped_sorted = sorted(roster_grouped.items(), key=lambda x: (shift_order.get(x[0][0], 9), x[0][1]))

    checklist_map = {r['item_no']: r for r in checklist_saved}
    night_checklist_items = []
    for _item in NIGHT_CHECKLIST_ITEMS:
        _saved = checklist_map.get(_item['no'])
        night_checklist_items.append({
            'no':           _item['no'],
            'name':         _item['name'],
            'door_lock':    _saved['door_lock']    if _saved else '-',
            'light_off':    _saved['light_off']    if _saved else '-',
            'hvac':         _saved['hvac']         if _saved else '-',
            'remark':       _saved['remark']       if _saved else _item['default_remark'],
            'check_result': _saved['check_result'] if _saved else '-',
        })

    return render_template('print_view.html', date_str=date_str,
                           roster_grouped=roster_grouped_sorted,
                           night_checklist_items=night_checklist_items,
                           **data)


# ════════════════════════════════════════════════════
# 다중 날짜 인쇄 (PDF 저장용)
# ════════════════════════════════════════════════════
@app.route('/print_range', methods=['POST'])
@login_required
def print_range():
    dates = sorted(set(request.form.getlist('dates')))
    if not dates:
        flash('출력할 날짜를 선택하세요.', 'warning')
        return redirect(url_for('worklog_list'))

    conn = get_db()
    shift_order = {'야간': 0, '오전': 1, '종일': 2}
    entries = []
    for d in dates:
        roster_rows = conn.execute(
            "SELECT * FROM staff_roster WHERE date=? ORDER BY shift, part, id", (d,)).fetchall()
        roster_grouped = {}
        for r in roster_rows:
            key = (r['shift'], r['part'])
            roster_grouped.setdefault(key, []).append(r['staff_name'])
        roster_grouped_sorted = sorted(roster_grouped.items(),
                                       key=lambda x: (shift_order.get(x[0][0], 9), x[0][1]))

        checklist_saved = conn.execute(
            "SELECT * FROM night_checklist WHERE date=? ORDER BY item_no", (d,)).fetchall()
        checklist_map = {r['item_no']: r for r in checklist_saved}
        night_checklist_items = []
        for _item in NIGHT_CHECKLIST_ITEMS:
            _saved = checklist_map.get(_item['no'])
            night_checklist_items.append({
                'no':           _item['no'],
                'name':         _item['name'],
                'door_lock':    _saved['door_lock']    if _saved else '-',
                'light_off':    _saved['light_off']    if _saved else '-',
                'hvac':         _saved['hvac']         if _saved else '-',
                'remark':       _saved['remark']       if _saved else _item['default_remark'],
                'check_result': _saved['check_result'] if _saved else '-',
            })

        entries.append({
            'date':                 d,
            'roster_grouped':       roster_grouped_sorted,
            'vacation':             conn.execute("SELECT * FROM vacation WHERE date=? ORDER BY part, vacation_code, staff_name", (d,)).fetchall(),
            'oncall':               conn.execute("SELECT * FROM oncall WHERE date=? ORDER BY part", (d,)).fetchall(),
            'overtime':             conn.execute("SELECT * FROM overtime WHERE date=? ORDER BY part, staff_name", (d,)).fetchall(),
            'equipment':            conn.execute("SELECT * FROM equipment_log WHERE date=? ORDER BY equipment_name", (d,)).fetchall(),
            'issues':               conn.execute("SELECT * FROM issues WHERE date=? ORDER BY severity, id", (d,)).fetchall(),
            'night_checklist_items': night_checklist_items,
        })
    conn.close()
    return render_template('print_range.html', entries=entries,
                           now=datetime.now().strftime('%Y-%m-%d %H:%M'))


# ════════════════════════════════════════════════════
# JSON API (SPA 전용)
# ════════════════════════════════════════════════════
def rows_to_list(rows):
    return [dict(r) for r in rows]


def api_auth():
    if 'user' not in session:
        return jsonify({'ok': False, 'msg': '로그인 필요'}), 401
    return None


@app.route('/api/login', methods=['POST'])
def api_login():
    d = request.get_json()
    password = hash_pw(d.get('password', ''))
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=? AND password=?",
                        (d.get('username', ''), password)).fetchone()
    conn.close()
    if user:
        session['user'] = user['username']
        session['name'] = user['name']
        session['role'] = user['role']
        return jsonify({'ok': True, 'user': user['username'], 'name': user['name'], 'role': user['role']})
    return jsonify({'ok': False, 'msg': '아이디 또는 비밀번호가 올바르지 않습니다.'}), 401


@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'ok': True})


@app.route('/api/me')
def api_me():
    if 'user' not in session:
        return jsonify({'ok': False}), 401
    return jsonify({'ok': True, 'user': session['user'], 'name': session['name'], 'role': session['role']})


@app.route('/api/dashboard')
def api_dashboard():
    err = api_auth()
    if err: return err
    td = date.today().isoformat()
    conn = get_db()
    data = {
        'today':           td,
        'roster_today':    rows_to_list(conn.execute("SELECT * FROM staff_roster WHERE date=? ORDER BY shift,part,id", (td,)).fetchall()),
        'vacation_today':  rows_to_list(conn.execute("SELECT * FROM vacation WHERE date=? ORDER BY part, vacation_code, staff_name", (td,)).fetchall()),
        'oncall_today':    rows_to_list(conn.execute("SELECT * FROM oncall WHERE date=? ORDER BY part", (td,)).fetchall()),
        'overtime_today':  rows_to_list(conn.execute("SELECT * FROM overtime WHERE date=? ORDER BY part, staff_name", (td,)).fetchall()),
        'equipment_today': rows_to_list(conn.execute("SELECT * FROM equipment_log WHERE date=? ORDER BY equipment_name", (td,)).fetchall()),
        'issues_today':    rows_to_list(conn.execute("SELECT * FROM issues WHERE date=? ORDER BY severity,id", (td,)).fetchall()),
        'issues_open':     rows_to_list(conn.execute("SELECT * FROM issues WHERE status='진행중' ORDER BY severity,date DESC LIMIT 10").fetchall()),
        'equip_active':    rows_to_list(conn.execute("SELECT * FROM equipment_log WHERE status='처리중' ORDER BY date DESC LIMIT 10").fetchall()),
    }
    conn.close()
    return jsonify({'ok': True, **data})


@app.route('/api/write')
def api_write():
    err = api_auth()
    if err: return err
    sel = request.args.get('date', date.today().isoformat())
    conn = get_db()
    ws = conn.execute("SELECT * FROM worklog_status WHERE date=?", (sel,)).fetchone()
    data = {
        'sel':       sel,
        'roster':    rows_to_list(conn.execute("SELECT * FROM staff_roster WHERE date=? ORDER BY shift,part,id", (sel,)).fetchall()),
        'vacation':  rows_to_list(conn.execute("SELECT * FROM vacation WHERE date=? ORDER BY part, vacation_code, staff_name", (sel,)).fetchall()),
        'oncall':    rows_to_list(conn.execute("SELECT * FROM oncall WHERE date=? ORDER BY part", (sel,)).fetchall()),
        'overtime':  rows_to_list(conn.execute("SELECT * FROM overtime WHERE date=? ORDER BY part, staff_name", (sel,)).fetchall()),
        'equipment': rows_to_list(conn.execute("SELECT * FROM equipment_log WHERE date=? ORDER BY equipment_name", (sel,)).fetchall()),
        'issues':    rows_to_list(conn.execute("SELECT * FROM issues WHERE date=? ORDER BY severity,id", (sel,)).fetchall()),
        'wl_status': dict(ws) if ws else None,
        'users_list': rows_to_list(conn.execute("SELECT name FROM users WHERE retired_date='' OR retired_date IS NULL ORDER BY name").fetchall()),
        'vacation_codes': rows_to_list(conn.execute("SELECT * FROM vacation_codes ORDER BY code").fetchall()),
    }
    conn.close()
    return jsonify({'ok': True, **data})


# ── API: 근무자 ──
@app.route('/api/write/roster/add', methods=['POST'])
def api_roster_add():
    err = api_auth()
    if err: return err
    d = request.get_json()
    conn = get_db()
    conn.execute("INSERT INTO staff_roster (date,shift,part,staff_name) VALUES (?,?,?,?)",
        (d['date'], d['shift'], d.get('part', ''), d['staff_name']))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


@app.route('/api/write/roster/edit/<int:id>', methods=['POST'])
def api_roster_edit(id):
    err = api_auth()
    if err: return err
    d = request.get_json()
    conn = get_db()
    conn.execute("UPDATE staff_roster SET shift=?,part=?,staff_name=? WHERE id=?",
        (d['shift'], d.get('part', ''), d['staff_name'], id))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


@app.route('/api/write/roster/delete/<int:id>', methods=['POST'])
def api_roster_delete(id):
    err = api_auth()
    if err: return err
    conn = get_db(); conn.execute("DELETE FROM staff_roster WHERE id=?", (id,)); conn.commit(); conn.close()
    return jsonify({'ok': True})


# ── API: 휴가 ──
@app.route('/api/write/vacation/add', methods=['POST'])
def api_vacation_add():
    err = api_auth()
    if err: return err
    d = request.get_json()
    conn = get_db()
    conn.execute("INSERT INTO vacation (date,part,staff_name,vacation_code) VALUES (?,?,?,?)",
        (d['date'], d.get('part',''), d['staff_name'], d['vacation_code']))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


@app.route('/api/write/vacation/edit/<int:id>', methods=['POST'])
def api_vacation_edit(id):
    err = api_auth()
    if err: return err
    d = request.get_json()
    conn = get_db()
    conn.execute("UPDATE vacation SET part=?,staff_name=?,vacation_code=? WHERE id=?",
        (d.get('part',''), d['staff_name'], d['vacation_code'], id))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


@app.route('/api/write/vacation/delete/<int:id>', methods=['POST'])
def api_vacation_delete(id):
    err = api_auth()
    if err: return err
    conn = get_db(); conn.execute("DELETE FROM vacation WHERE id=?", (id,)); conn.commit(); conn.close()
    return jsonify({'ok': True})


# ── API: On-call ──
@app.route('/api/write/oncall/add', methods=['POST'])
def api_oncall_add():
    err = api_auth()
    if err: return err
    d = request.get_json()
    arrival    = d.get('arrival_time', '')
    proc_start = d.get('procedure_start', '')
    proc_end   = d.get('procedure_end', '')
    departure  = d.get('departure_time', '')
    h          = _calc_hours(arrival, departure)
    conn = get_db()
    conn.execute(
        "INSERT INTO oncall (date,part,staff_name,arrival_time,procedure_start,procedure_end,departure_time,hours,reason,modality) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (d['date'], d.get('part', ''), d['staff_name'], arrival, proc_start, proc_end, departure, h, d.get('reason', ''), d.get('part', '')))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


@app.route('/api/write/oncall/edit/<int:id>', methods=['POST'])
def api_oncall_edit(id):
    err = api_auth()
    if err: return err
    d = request.get_json()
    arrival    = d.get('arrival_time', '')
    proc_start = d.get('procedure_start', '')
    proc_end   = d.get('procedure_end', '')
    departure  = d.get('departure_time', '')
    h          = _calc_hours(arrival, departure)
    conn = get_db()
    conn.execute(
        "UPDATE oncall SET part=?,staff_name=?,arrival_time=?,procedure_start=?,procedure_end=?,departure_time=?,hours=?,reason=? WHERE id=?",
        (d.get('part', ''), d['staff_name'], arrival, proc_start, proc_end, departure, h, d.get('reason', ''), id))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


@app.route('/api/write/oncall/delete/<int:id>', methods=['POST'])
def api_oncall_delete(id):
    err = api_auth()
    if err: return err
    conn = get_db(); conn.execute("DELETE FROM oncall WHERE id=?", (id,)); conn.commit(); conn.close()
    return jsonify({'ok': True})


# ── API: 연장근무 ──
@app.route('/api/write/overtime/add', methods=['POST'])
def api_overtime_add():
    err = api_auth()
    if err: return err
    d = request.get_json()
    st, et = d['start_time'], d['end_time']
    try:
        h = round((datetime.strptime(et, '%H:%M') - datetime.strptime(st, '%H:%M')).seconds / 3600, 1)
    except Exception:
        h = 0
    conn = get_db()
    conn.execute("INSERT INTO overtime (date,staff_name,start_time,end_time,hours,reason) VALUES (?,?,?,?,?,?)",
        (d['date'], d['staff_name'], st, et, h, d['reason']))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


@app.route('/api/write/overtime/edit/<int:id>', methods=['POST'])
def api_overtime_edit(id):
    err = api_auth()
    if err: return err
    d = request.get_json()
    st, et = d['start_time'], d['end_time']
    try:
        h = round((datetime.strptime(et, '%H:%M') - datetime.strptime(st, '%H:%M')).seconds / 3600, 1)
    except Exception:
        h = 0
    conn = get_db()
    conn.execute("UPDATE overtime SET staff_name=?,start_time=?,end_time=?,hours=?,reason=? WHERE id=?",
        (d['staff_name'], st, et, h, d['reason'], id))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


@app.route('/api/write/overtime/delete/<int:id>', methods=['POST'])
def api_overtime_delete(id):
    err = api_auth()
    if err: return err
    conn = get_db(); conn.execute("DELETE FROM overtime WHERE id=?", (id,)); conn.commit(); conn.close()
    return jsonify({'ok': True})


# ── API: 장비 ──
@app.route('/api/write/equipment/add', methods=['POST'])
def api_equipment_add():
    err = api_auth()
    if err: return err
    d = request.get_json()
    conn = get_db()
    conn.execute("INSERT INTO equipment_log (date,equipment_name,log_type,description,engineer,start_time,end_time,downtime,status) VALUES (?,?,?,?,?,?,?,?,?)",
        (d['date'], d['equipment_name'], d['log_type'], d.get('description', ''),
         d.get('engineer', ''), d.get('start_time', ''), d.get('end_time', ''),
         d.get('downtime', ''), d['status']))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


@app.route('/api/write/equipment/edit/<int:id>', methods=['POST'])
def api_equipment_edit(id):
    err = api_auth()
    if err: return err
    d = request.get_json()
    conn = get_db()
    conn.execute("UPDATE equipment_log SET equipment_name=?,log_type=?,description=?,engineer=?,start_time=?,end_time=?,downtime=?,status=? WHERE id=?",
        (d['equipment_name'], d['log_type'], d.get('description', ''), d.get('engineer', ''),
         d.get('start_time', ''), d.get('end_time', ''), d.get('downtime', ''), d['status'], id))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


@app.route('/api/write/equipment/delete/<int:id>', methods=['POST'])
def api_equipment_delete(id):
    err = api_auth()
    if err: return err
    conn = get_db(); conn.execute("DELETE FROM equipment_log WHERE id=?", (id,)); conn.commit(); conn.close()
    return jsonify({'ok': True})


# ── API: 이슈 ──
@app.route('/api/write/issue/add', methods=['POST'])
def api_issue_add():
    err = api_auth()
    if err: return err
    d = request.get_json()
    conn = get_db()
    conn.execute("INSERT INTO issues (date,category,severity,title,content,status,author) VALUES (?,?,?,?,?,?,?)",
        (d['date'], d['category'], d['severity'], d['title'], d['content'], d.get('status', '진행중'), session['name']))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


@app.route('/api/write/issue/edit/<int:id>', methods=['POST'])
def api_issue_edit(id):
    err = api_auth()
    if err: return err
    d = request.get_json()
    conn = get_db()
    conn.execute("UPDATE issues SET category=?,severity=?,title=?,content=?,status=? WHERE id=?",
        (d['category'], d['severity'], d['title'], d['content'], d['status'], id))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


@app.route('/api/write/issue/delete/<int:id>', methods=['POST'])
def api_issue_delete(id):
    err = api_auth()
    if err: return err
    conn = get_db(); conn.execute("DELETE FROM issues WHERE id=?", (id,)); conn.commit(); conn.close()
    return jsonify({'ok': True})


# ── API: 초기화 ──
@app.route('/api/write/reset/<date_str>', methods=['POST'])
def api_write_reset(date_str):
    err = api_auth()
    if err: return err
    if session.get('role') != 'admin':
        return jsonify({'ok': False, 'msg': '관리자만 가능'}), 403
    conn = get_db()
    conn.execute("DELETE FROM staff_roster   WHERE date=?", (date_str,))
    conn.execute("DELETE FROM vacation        WHERE date=?", (date_str,))
    conn.execute("DELETE FROM oncall          WHERE date=?", (date_str,))
    conn.execute("DELETE FROM overtime        WHERE date=?", (date_str,))
    conn.execute("DELETE FROM equipment_log   WHERE date=?", (date_str,))
    conn.execute("DELETE FROM issues          WHERE date=?", (date_str,))
    conn.execute("DELETE FROM night_checklist WHERE date=?", (date_str,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


# ── API: 업무일지 ──
@app.route('/api/worklog')
def api_worklog():
    err = api_auth()
    if err: return err
    conn = get_db()
    statuses = conn.execute("SELECT * FROM worklog_status ORDER BY date DESC").fetchall()
    if session.get('role') == 'admin':
        users_rows = conn.execute("SELECT username, name FROM users ORDER BY name").fetchall()
    else:
        users_rows = []
    logs = []
    for ws in statuses:
        d = ws['date']
        logs.append({
            'date':         d,
            'roster':       conn.execute("SELECT COUNT(*) as c FROM staff_roster WHERE date=?", (d,)).fetchone()['c'],
            'vacation':     conn.execute("SELECT COUNT(*) as c FROM vacation WHERE date=?", (d,)).fetchone()['c'],
            'oncall':       conn.execute("SELECT COUNT(*) as c FROM oncall WHERE date=?", (d,)).fetchone()['c'],
            'overtime':     conn.execute("SELECT COUNT(*) as c FROM overtime WHERE date=?", (d,)).fetchone()['c'],
            'equipment':    conn.execute("SELECT COUNT(*) as c FROM equipment_log WHERE date=?", (d,)).fetchone()['c'],
            'issues':       conn.execute("SELECT COUNT(*) as c FROM issues WHERE date=?", (d,)).fetchone()['c'],
            'wl_status':    ws['status'],
            'submitted_by': ws['submitted_by'] or '',
            'rejected_by':  ws['rejected_by'] or '',
            'rejected_to':  ws['rejected_to'] or '',
            'confirmed_by': ws['confirmed_by'] or '',
        })
    conn.close()
    return jsonify({'ok': True, 'logs': logs, 'users': rows_to_list(users_rows)})


@app.route('/api/worklog/save/<date_str>', methods=['POST'])
def api_worklog_save(date_str):
    err = api_auth()
    if err: return err
    conn = get_db()
    ws = conn.execute("SELECT status FROM worklog_status WHERE date=?", (date_str,)).fetchone()
    if ws and ws['status'] in ('제출', '확정'):
        conn.close()
        return jsonify({'ok': False, 'msg': '해당일자의 업무일지가 제출되었습니다. 업무일지 리스트에서 확인하시기 바랍니다.'})
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute("""INSERT OR REPLACE INTO worklog_status
        (date, status, submitted_by, submitted_at, rejected_by, rejected_to, rejected_at, confirmed_by, confirmed_at)
        VALUES (?, '저장', ?, ?, '', '', '', '', '')""",
        (date_str, session['user'], now_str))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


@app.route('/api/worklog/submit/<date_str>', methods=['POST'])
def api_worklog_submit(date_str):
    err = api_auth()
    if err: return err
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    conn.execute("""INSERT OR REPLACE INTO worklog_status
        (date, status, submitted_by, submitted_at, rejected_by, rejected_to, rejected_at, confirmed_by, confirmed_at)
        VALUES (?, '제출', ?, ?, '', '', '', '', '')""",
        (date_str, session['user'], now_str))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


@app.route('/api/worklog/withdraw/<date_str>', methods=['POST'])
def api_worklog_withdraw(date_str):
    err = api_auth()
    if err: return err
    conn = get_db()
    ws = conn.execute("SELECT submitted_by FROM worklog_status WHERE date=?", (date_str,)).fetchone()
    if ws and (ws['submitted_by'] == session['user'] or session.get('role') == 'admin'):
        conn.execute("UPDATE worklog_status SET status='저장' WHERE date=?", (date_str,))
        conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/worklog/reject/<date_str>', methods=['POST'])
def api_worklog_reject(date_str):
    err = api_auth()
    if err: return err
    if session.get('role') != 'admin':
        return jsonify({'ok': False}), 403
    d = request.get_json()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    conn.execute("UPDATE worklog_status SET status='반려',rejected_by=?,rejected_to=?,rejected_at=? WHERE date=?",
        (session['name'], d.get('target_user', ''), now_str, date_str))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


@app.route('/api/worklog/confirm/<date_str>', methods=['POST'])
def api_worklog_confirm(date_str):
    err = api_auth()
    if err: return err
    if session.get('role') != 'admin':
        return jsonify({'ok': False}), 403
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    conn.execute("UPDATE worklog_status SET status='확정', confirmed_by=?, confirmed_at=? WHERE date=?",
        (session['name'], now_str, date_str))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


# ── API: 인쇄 ──
@app.route('/api/print/<date_str>')
def api_print(date_str):
    err = api_auth()
    if err: return err
    conn = get_db()
    data = {
        'date_str': date_str,
        'roster':    rows_to_list(conn.execute("SELECT * FROM staff_roster WHERE date=? ORDER BY shift,part,id", (date_str,)).fetchall()),
        'vacation':  rows_to_list(conn.execute("SELECT * FROM vacation WHERE date=? ORDER BY part, vacation_code, staff_name", (date_str,)).fetchall()),
        'oncall':    rows_to_list(conn.execute("SELECT * FROM oncall WHERE date=? ORDER BY part", (date_str,)).fetchall()),
        'overtime':  rows_to_list(conn.execute("SELECT * FROM overtime WHERE date=? ORDER BY part, staff_name", (date_str,)).fetchall()),
        'equipment': rows_to_list(conn.execute("SELECT * FROM equipment_log WHERE date=? ORDER BY equipment_name", (date_str,)).fetchall()),
        'issues':    rows_to_list(conn.execute("SELECT * FROM issues WHERE date=? ORDER BY severity,id", (date_str,)).fetchall()),
        'now':       datetime.now().strftime('%Y-%m-%d %H:%M'),
    }
    conn.close()
    return jsonify({'ok': True, **data})


# ── API: 사용자 관리 ──
@app.route('/api/users')
def api_users():
    err = api_auth()
    if err: return err
    if session.get('role') != 'admin':
        return jsonify({'ok': False}), 403
    f = request.args.get('filter', '재직자')
    conn = get_db()
    if f == '퇴사자':
        rows = conn.execute("SELECT * FROM users WHERE retired_date != '' AND retired_date IS NOT NULL ORDER BY name").fetchall()
    elif f == '전체':
        rows = conn.execute("SELECT * FROM users ORDER BY name").fetchall()
    else:
        rows = conn.execute("SELECT * FROM users WHERE retired_date='' OR retired_date IS NULL ORDER BY name").fetchall()
    vacation_codes = conn.execute("SELECT * FROM vacation_codes ORDER BY code").fetchall()
    conn.close()
    return jsonify({'ok': True, 'users': rows_to_list(rows), 'vacation_codes': rows_to_list(vacation_codes)})


@app.route('/api/users/add', methods=['POST'])
def api_users_add():
    err = api_auth()
    if err: return err
    if session.get('role') != 'admin':
        return jsonify({'ok': False}), 403
    d = request.get_json()
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (username, password, name, part, role, hire_date, retired_date) VALUES (?,?,?,?,?,?,?)",
            (d['username'], hash_pw(d['password']), d['name'],
             d.get('part', ''), d.get('role', 'user'),
             d.get('hire_date', ''), d.get('retired_date', '')))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception:
        conn.close()
        return jsonify({'ok': False, 'msg': '이미 존재하는 사번입니다.'}), 400


@app.route('/api/users/delete/<int:id>', methods=['POST'])
def api_users_delete(id):
    err = api_auth()
    if err: return err
    if session.get('role') != 'admin':
        return jsonify({'ok': False}), 403
    conn = get_db(); conn.execute("DELETE FROM users WHERE id=?", (id,)); conn.commit(); conn.close()
    return jsonify({'ok': True})


# ════════════════════════════════════════════════════
# 특수의료장비현황 CRUD
# ════════════════════════════════════════════════════
@app.route('/special-equipment/add', methods=['POST'])
@login_required
def special_equipment_add():
    conn = get_special_eq_db()
    conn.execute(
        "INSERT INTO special_equipment (unique_serial, category, sn, equipment_name, manager, radiographer1, radiographer2, note) VALUES (?,?,?,?,?,?,?,?)",
        (request.form.get('unique_serial', '').strip(),
         request.form.get('category', '').strip(),
         request.form.get('sn', '').strip(),
         request.form.get('equipment_name', '').strip(),
         request.form.get('manager', '').strip(),
         request.form.get('radiographer1', '').strip(),
         request.form.get('radiographer2', '').strip(),
         request.form.get('note', '').strip())
    )
    conn.commit()
    conn.close()
    return redirect(url_for('special_equipment_list'))


@app.route('/special-equipment/edit/<int:eid>', methods=['POST'])
@login_required
def special_equipment_edit(eid):
    conn = get_special_eq_db()
    conn.execute(
        "UPDATE special_equipment SET unique_serial=?, category=?, sn=?, equipment_name=?, manager=?, radiographer1=?, radiographer2=?, note=? WHERE id=?",
        (request.form.get('unique_serial', '').strip(),
         request.form.get('category', '').strip(),
         request.form.get('sn', '').strip(),
         request.form.get('equipment_name', '').strip(),
         request.form.get('manager', '').strip(),
         request.form.get('radiographer1', '').strip(),
         request.form.get('radiographer2', '').strip(),
         request.form.get('note', '').strip(),
         eid)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('special_equipment_list'))


@app.route('/special-equipment/delete/<int:eid>', methods=['POST'])
@login_required
def special_equipment_delete(eid):
    conn = get_special_eq_db()
    conn.execute("DELETE FROM special_equipment WHERE id=?", (eid,))
    conn.commit()
    conn.close()
    return redirect(url_for('special_equipment_list'))


# ════════════════════════════════════════════════════
# 진단용방사선발생장치현황 CRUD
# ════════════════════════════════════════════════════
@app.route('/radiation-device/add', methods=['POST'])
@login_required
def radiation_device_add():
    conn = get_radiation_db()
    conn.execute(
        "INSERT INTO radiation_device (code, location, purpose, device_type, model_name, manufacture_date, serial_number, manufacture_country, manufacturer, first_use_date, note) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (request.form.get('code', '').strip(),
         request.form.get('location', '').strip(),
         request.form.get('purpose', '').strip(),
         request.form.get('device_type', '').strip(),
         request.form.get('model_name', '').strip(),
         request.form.get('manufacture_date', '').strip(),
         request.form.get('serial_number', '').strip(),
         request.form.get('manufacture_country', '').strip(),
         request.form.get('manufacturer', '').strip(),
         request.form.get('first_use_date', '').strip(),
         request.form.get('note', '').strip())
    )
    conn.commit()
    conn.close()
    return redirect(url_for('radiation_device_list'))


@app.route('/radiation-device/edit/<int:eid>', methods=['POST'])
@login_required
def radiation_device_edit(eid):
    conn = get_radiation_db()
    conn.execute(
        "UPDATE radiation_device SET code=?, location=?, purpose=?, device_type=?, model_name=?, manufacture_date=?, serial_number=?, manufacture_country=?, manufacturer=?, first_use_date=?, note=? WHERE id=?",
        (request.form.get('code', '').strip(),
         request.form.get('location', '').strip(),
         request.form.get('purpose', '').strip(),
         request.form.get('device_type', '').strip(),
         request.form.get('model_name', '').strip(),
         request.form.get('manufacture_date', '').strip(),
         request.form.get('serial_number', '').strip(),
         request.form.get('manufacture_country', '').strip(),
         request.form.get('manufacturer', '').strip(),
         request.form.get('first_use_date', '').strip(),
         request.form.get('note', '').strip(),
         eid)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('radiation_device_list'))


@app.route('/radiation-device/delete/<int:eid>', methods=['POST'])
@login_required
def radiation_device_delete(eid):
    conn = get_radiation_db()
    conn.execute("DELETE FROM radiation_device WHERE id=?", (eid,))
    conn.commit()
    conn.close()
    return redirect(url_for('radiation_device_list'))


# ════════════════════════════════════════════════════
# 앱 실행
# ════════════════════════════════════════════════════
if __name__ == '__main__':
    init_db()
    init_special_eq_db()
    init_radiation_db()
    try:
        from waitress import serve
        print('[INFO] 서버 시작 중... http://localhost:1000')
        serve(app, host='0.0.0.0', port=1000, threads=8)
    except ImportError:
        print('[WARN] waitress 미설치 — Flask 개발 서버로 시작합니다.')
        app.run(host='0.0.0.0', port=1000, debug=False)
