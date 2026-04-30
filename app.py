"""
영상의학과 업무일지 웹앱
Flask + SQLite 기반 내부망 전용
"""
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from datetime import datetime, date, timedelta
import sqlite3
import os
import hashlib

app = Flask(__name__)

app.secret_key = os.environ.get('SECRET_KEY', 'caumc-radiology-2024-!@#internal')

@app.context_processor
def inject_now():
    return {'now': datetime.now().strftime('%Y-%m-%d %H:%M')}

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'worklog.db')

PARTS = ['GR', 'CT', 'MR', '인터벤션', '간호']
SHIFTS = ['야간', '오전', '종일']

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    c = conn.cursor()

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
                staff_name TEXT NOT NULL,
                vacation_code TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )''')

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
        received_time TEXT DEFAULT '',
        reason TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )''')

    # ── 연장근무 ──
    c.execute('''CREATE TABLE IF NOT EXISTS overtime (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        staff_name TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        hours REAL NOT NULL,
        reason TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )''')

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
    for col, typedef in [('part', "TEXT DEFAULT ''"), ('received_time', "TEXT DEFAULT ''"), ('reason', "TEXT DEFAULT ''")]:
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
    vacation_today  = conn.execute("SELECT * FROM vacation WHERE date=? ORDER BY staff_name", (today,)).fetchall()
    oncall_today    = conn.execute("SELECT * FROM oncall WHERE date=? ORDER BY part", (today,)).fetchall()
    overtime_today  = conn.execute("SELECT * FROM overtime WHERE date=? ORDER BY staff_name", (today,)).fetchall()
    equipment_today = conn.execute("SELECT * FROM equipment_log WHERE date=? ORDER BY equipment_name", (today,)).fetchall()
    issues_today    = conn.execute("SELECT * FROM issues WHERE date=? ORDER BY severity, id", (today,)).fetchall()

    # D-1 현황 (KPI 카운트용)
    vacation_d1  = conn.execute("SELECT * FROM vacation WHERE date=? ORDER BY staff_name", (d1,)).fetchall()
    oncall_d1    = conn.execute("SELECT * FROM oncall WHERE date=? ORDER BY part", (d1,)).fetchall()
    overtime_d1  = conn.execute("SELECT * FROM overtime WHERE date=? ORDER BY staff_name", (d1,)).fetchall()
    equipment_d1 = conn.execute("SELECT * FROM equipment_log WHERE date=? ORDER BY equipment_name", (d1,)).fetchall()
    issues_d1    = conn.execute("SELECT * FROM issues WHERE date=? ORDER BY severity, id", (d1,)).fetchall()

    # D-2 현황 (툴팁 비교용)
    vacation_d2  = conn.execute("SELECT * FROM vacation WHERE date=? ORDER BY staff_name", (d2,)).fetchall()
    oncall_d2    = conn.execute("SELECT * FROM oncall WHERE date=? ORDER BY part", (d2,)).fetchall()
    overtime_d2  = conn.execute("SELECT * FROM overtime WHERE date=? ORDER BY staff_name", (d2,)).fetchall()
    equipment_d2 = conn.execute("SELECT * FROM equipment_log WHERE date=? ORDER BY equipment_name", (d2,)).fetchall()
    issues_d2    = conn.execute("SELECT * FROM issues WHERE date=? ORDER BY severity, id", (d2,)).fetchall()

    issues_open_rows  = conn.execute("SELECT * FROM issues WHERE status='진행중' ORDER BY severity, date DESC LIMIT 10").fetchall()
    equip_active_rows = conn.execute("SELECT * FROM equipment_log WHERE status='처리중' ORDER BY date DESC LIMIT 10").fetchall()

    conn.close()

    # 근무자 현황: shift+part 그룹화
    roster_grouped = {}
    shift_order = {'야간': 0, '오전': 1, '종일': 2}
    for r in roster_today:
        key = (r['shift'], r['part'])
        roster_grouped.setdefault(key, []).append(r['staff_name'])
    roster_grouped_sorted = sorted(roster_grouped.items(), key=lambda x: (shift_order.get(x[0][0], 9), x[0][1]))

    return render_template('dashboard.html',
        today=today, d1=d1, d2=d2,
        roster_grouped=roster_grouped_sorted,
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
        issues_d1=issues_d1, issues_d2=issues_d2)


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
        'vacation':  conn.execute("SELECT * FROM vacation WHERE date=? ORDER BY staff_name", (sel,)).fetchall(),
        'oncall':    conn.execute("SELECT * FROM oncall WHERE date=? ORDER BY part", (sel,)).fetchall(),
        'overtime':  conn.execute("SELECT * FROM overtime WHERE date=? ORDER BY staff_name", (sel,)).fetchall(),
        'equipment': conn.execute("SELECT * FROM equipment_log WHERE date=? ORDER BY equipment_name", (sel,)).fetchall(),
        'issues':    conn.execute("SELECT * FROM issues WHERE date=? ORDER BY severity, id", (sel,)).fetchall(),
    }

    users_list = conn.execute(
        "SELECT name FROM users WHERE retired_date='' OR retired_date IS NULL ORDER BY name",
        ).fetchall()
    vacation_codes_list = conn.execute("SELECT * FROM vacation_codes ORDER BY code").fetchall()

    conn.close()
    wl_status = ws['status'] if ws else None
    submitted_by = ws['submitted_by'] if ws else ''
    return render_template('write.html',
        sel=sel, wl_status=wl_status, submitted_by=submitted_by,
        parts=PARTS, shifts=SHIFTS,
        users_list=users_list, vacation_codes_list=vacation_codes_list,
        **data)


# ── 근무자 현황 ──
@app.route('/write/roster/add', methods=['POST'])
@login_required
def write_roster_add():
    d = request.form['date']
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
    conn.execute("UPDATE staff_roster SET shift=?,part=?,staff_name=? WHERE id=?",
        (request.form['shift'], request.form.get('part', ''), request.form['staff_name'], id))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/roster/delete/<int:id>')
@login_required
def write_roster_delete(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM staff_roster WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    conn.execute("DELETE FROM staff_roster WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


# ── 휴가 현황 ──
@app.route('/write/vacation/add', methods=['POST'])
@login_required
def write_vacation_add():
    d = request.form['date']
    conn = get_db()
    conn.execute("INSERT INTO vacation (date,staff_name,vacation_code) VALUES (?,?,?)",
        (d, request.form['staff_name'], request.form['vacation_code']))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/vacation/edit/<int:id>', methods=['POST'])
@login_required
def write_vacation_edit(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM vacation WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    conn.execute("UPDATE vacation SET staff_name=?,vacation_code=? WHERE id=?",
        (request.form['staff_name'], request.form['vacation_code'], id))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/vacation/delete/<int:id>')
@login_required
def write_vacation_delete(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM vacation WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    conn.execute("DELETE FROM vacation WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


# ── On-call ──
@app.route('/write/oncall/add', methods=['POST'])
@login_required
def write_oncall_add():
    d = request.form['date']
    conn = get_db()
    conn.execute("INSERT INTO oncall (date,part,staff_name,received_time,reason) VALUES (?,?,?,?,?)",
        (d, request.form.get('part', ''), request.form['staff_name'],
         request.form.get('received_time', ''), request.form.get('reason', '')))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/oncall/edit/<int:id>', methods=['POST'])
@login_required
def write_oncall_edit(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM oncall WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    conn.execute("UPDATE oncall SET part=?,staff_name=?,received_time=?,reason=? WHERE id=?",
        (request.form.get('part', ''), request.form['staff_name'],
         request.form.get('received_time', ''), request.form.get('reason', ''), id))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/oncall/delete/<int:id>')
@login_required
def write_oncall_delete(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM oncall WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    conn.execute("DELETE FROM oncall WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


# ── 연장근무 ──
@app.route('/write/overtime/add', methods=['POST'])
@login_required
def write_overtime_add():
    d = request.form['date']
    st = request.form['start_time']
    et = request.form['end_time']
    try:
        h = round((datetime.strptime(et, '%H:%M') - datetime.strptime(st, '%H:%M')).seconds / 3600, 1)
    except Exception:
        h = 0
    conn = get_db()
    conn.execute("INSERT INTO overtime (date,staff_name,start_time,end_time,hours,reason) VALUES (?,?,?,?,?,?)",
        (d, request.form['staff_name'], st, et, h, request.form['reason']))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/overtime/edit/<int:id>', methods=['POST'])
@login_required
def write_overtime_edit(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM overtime WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    st = request.form['start_time']
    et = request.form['end_time']
    try:
        h = round((datetime.strptime(et, '%H:%M') - datetime.strptime(st, '%H:%M')).seconds / 3600, 1)
    except Exception:
        h = 0
    conn.execute("UPDATE overtime SET staff_name=?,start_time=?,end_time=?,hours=?,reason=? WHERE id=?",
        (request.form['staff_name'], st, et, h, request.form['reason'], id))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/overtime/delete/<int:id>')
@login_required
def write_overtime_delete(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM overtime WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    conn.execute("DELETE FROM overtime WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


# ── 장비 이력 ──
@app.route('/write/equipment/add', methods=['POST'])
@login_required
def write_equipment_add():
    d = request.form['date']
    conn = get_db()
    conn.execute("INSERT INTO equipment_log (date,equipment_name,log_type,description,engineer,start_time,end_time,downtime,status) VALUES (?,?,?,?,?,?,?,?,?)",
        (d, request.form['equipment_name'], request.form['log_type'],
         request.form.get('description', ''), request.form.get('engineer', ''),
         request.form.get('start_time', ''), request.form.get('end_time', ''),
         request.form.get('downtime', ''), request.form['status']))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/equipment/edit/<int:id>', methods=['POST'])
@login_required
def write_equipment_edit(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM equipment_log WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    conn.execute("UPDATE equipment_log SET equipment_name=?,log_type=?,description=?,engineer=?,start_time=?,end_time=?,downtime=?,status=? WHERE id=?",
        (request.form['equipment_name'], request.form['log_type'],
         request.form.get('description', ''), request.form.get('engineer', ''),
         request.form.get('start_time', ''), request.form.get('end_time', ''),
         request.form.get('downtime', ''), request.form['status'], id))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/equipment/delete/<int:id>')
@login_required
def write_equipment_delete(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM equipment_log WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    conn.execute("DELETE FROM equipment_log WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


# ── 특이사항·이슈 ──
@app.route('/write/issue/add', methods=['POST'])
@login_required
def write_issue_add():
    d = request.form['date']
    conn = get_db()
    conn.execute("INSERT INTO issues (date,category,severity,title,content,status,author) VALUES (?,?,?,?,?,?,?)",
        (d, request.form['category'], request.form['severity'],
         request.form['title'], request.form['content'],
         request.form.get('status', '진행중'), session['name']))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/issue/edit/<int:id>', methods=['POST'])
@login_required
def write_issue_edit(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM issues WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    conn.execute("UPDATE issues SET category=?,severity=?,title=?,content=?,status=? WHERE id=?",
        (request.form['category'], request.form['severity'],
         request.form['title'], request.form['content'], request.form['status'], id))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/issue/delete/<int:id>')
@login_required
def write_issue_delete(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM issues WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    conn.execute("DELETE FROM issues WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


# ── 날짜 초기화 ──
@app.route('/write/reset/<date_str>')
@login_required
def write_reset(date_str):
    if session.get('role') != 'admin':
        flash('관리자만 초기화할 수 있습니다.', 'danger')
        return redirect(url_for('write', date=date_str))
    conn = get_db()
    conn.execute("DELETE FROM staff_roster  WHERE date=?", (date_str,))
    conn.execute("DELETE FROM vacation       WHERE date=?", (date_str,))
    conn.execute("DELETE FROM oncall         WHERE date=?", (date_str,))
    conn.execute("DELETE FROM overtime       WHERE date=?", (date_str,))
    conn.execute("DELETE FROM equipment_log  WHERE date=?", (date_str,))
    conn.execute("DELETE FROM issues         WHERE date=?", (date_str,))
    conn.commit(); conn.close()
    flash(f'{date_str} 날짜의 모든 데이터가 초기화되었습니다.', 'info')
    return redirect(url_for('write', date=date_str))


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
        conn.execute("UPDATE worklog_status SET status='회수' WHERE date=?", (date_str,))
        conn.commit()
        flash(f'{date_str} 업무일지가 회수되었습니다.', 'info')
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
    conn = get_db()
    if session.get('role') == 'admin':
        statuses = conn.execute("SELECT * FROM worklog_status ORDER BY date DESC").fetchall()
        users = conn.execute("SELECT username, name FROM users ORDER BY name").fetchall()
    else:
        statuses = conn.execute(
            """SELECT * FROM worklog_status
               WHERE submitted_by=? OR (status='반려' AND rejected_to=?)
               ORDER BY date DESC""",
            (session['user'], session['user'])).fetchall()
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
    return render_template('worklog_list.html', logs=logs, users=users)


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
            "SELECT * FROM users WHERE retired_date != '' AND retired_date IS NOT NULL ORDER BY name"
        ).fetchall()
    elif f == '전체':
        rows = conn.execute("SELECT * FROM users ORDER BY name").fetchall()
    else:  # 재직자 (기본)
        rows = conn.execute(
            "SELECT * FROM users WHERE retired_date='' OR retired_date IS NULL ORDER BY name"
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


@app.route('/users/delete/<int:id>')
@login_required
def user_delete(id):
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect(url_for('users'))


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


@app.route('/users/vacation_code/delete/<int:id>')
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
        'vacation':  conn.execute("SELECT * FROM vacation WHERE date=? ORDER BY staff_name", (date_str,)).fetchall(),
        'oncall':    conn.execute("SELECT * FROM oncall WHERE date=? ORDER BY part", (date_str,)).fetchall(),
        'overtime':  conn.execute("SELECT * FROM overtime WHERE date=? ORDER BY staff_name", (date_str,)).fetchall(),
        'equipment': conn.execute("SELECT * FROM equipment_log WHERE date=? ORDER BY equipment_name", (date_str,)).fetchall(),
        'issues':    conn.execute("SELECT * FROM issues WHERE date=? ORDER BY severity, id", (date_str,)).fetchall(),
    }
    conn.close()

    roster_grouped = {}
    shift_order = {'야간': 0, '오전': 1, '종일': 2}
    for r in data['roster']:
        key = (r['shift'], r['part'])
        roster_grouped.setdefault(key, []).append(r['staff_name'])
    roster_grouped_sorted = sorted(roster_grouped.items(), key=lambda x: (shift_order.get(x[0][0], 9), x[0][1]))

    return render_template('print_view.html', date_str=date_str, roster_grouped=roster_grouped_sorted, **data)


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
        'vacation_today':  rows_to_list(conn.execute("SELECT * FROM vacation WHERE date=? ORDER BY staff_name", (td,)).fetchall()),
        'oncall_today':    rows_to_list(conn.execute("SELECT * FROM oncall WHERE date=? ORDER BY part", (td,)).fetchall()),
        'overtime_today':  rows_to_list(conn.execute("SELECT * FROM overtime WHERE date=? ORDER BY staff_name", (td,)).fetchall()),
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
        'vacation':  rows_to_list(conn.execute("SELECT * FROM vacation WHERE date=? ORDER BY staff_name", (sel,)).fetchall()),
        'oncall':    rows_to_list(conn.execute("SELECT * FROM oncall WHERE date=? ORDER BY part", (sel,)).fetchall()),
        'overtime':  rows_to_list(conn.execute("SELECT * FROM overtime WHERE date=? ORDER BY staff_name", (sel,)).fetchall()),
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
    conn.execute("INSERT INTO vacation (date,staff_name,vacation_code) VALUES (?,?,?)",
        (d['date'], d['staff_name'], d['vacation_code']))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


@app.route('/api/write/vacation/edit/<int:id>', methods=['POST'])
def api_vacation_edit(id):
    err = api_auth()
    if err: return err
    d = request.get_json()
    conn = get_db()
    conn.execute("UPDATE vacation SET staff_name=?,vacation_code=? WHERE id=?",
        (d['staff_name'], d['vacation_code'], id))
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
    conn = get_db()
    conn.execute("INSERT INTO oncall (date,part,staff_name,received_time,reason) VALUES (?,?,?,?,?)",
        (d['date'], d.get('part', ''), d['staff_name'], d.get('received_time', ''), d.get('reason', '')))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


@app.route('/api/write/oncall/edit/<int:id>', methods=['POST'])
def api_oncall_edit(id):
    err = api_auth()
    if err: return err
    d = request.get_json()
    conn = get_db()
    conn.execute("UPDATE oncall SET part=?,staff_name=?,received_time=?,reason=? WHERE id=?",
        (d.get('part', ''), d['staff_name'], d.get('received_time', ''), d.get('reason', ''), id))
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
    conn.execute("DELETE FROM staff_roster  WHERE date=?", (date_str,))
    conn.execute("DELETE FROM vacation       WHERE date=?", (date_str,))
    conn.execute("DELETE FROM oncall         WHERE date=?", (date_str,))
    conn.execute("DELETE FROM overtime       WHERE date=?", (date_str,))
    conn.execute("DELETE FROM equipment_log  WHERE date=?", (date_str,))
    conn.execute("DELETE FROM issues         WHERE date=?", (date_str,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


# ── API: 업무일지 ──
@app.route('/api/worklog')
def api_worklog():
    err = api_auth()
    if err: return err
    conn = get_db()
    if session.get('role') == 'admin':
        statuses = conn.execute("SELECT * FROM worklog_status ORDER BY date DESC").fetchall()
        users_rows = conn.execute("SELECT username, name FROM users ORDER BY name").fetchall()
    else:
        statuses = conn.execute(
            """SELECT * FROM worklog_status
               WHERE submitted_by=? OR (status='반려' AND rejected_to=?)
               ORDER BY date DESC""",
            (session['user'], session['user'])).fetchall()
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
        conn.execute("UPDATE worklog_status SET status='회수' WHERE date=?", (date_str,))
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
        'vacation':  rows_to_list(conn.execute("SELECT * FROM vacation WHERE date=? ORDER BY staff_name", (date_str,)).fetchall()),
        'oncall':    rows_to_list(conn.execute("SELECT * FROM oncall WHERE date=? ORDER BY part", (date_str,)).fetchall()),
        'overtime':  rows_to_list(conn.execute("SELECT * FROM overtime WHERE date=? ORDER BY staff_name", (date_str,)).fetchall()),
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
# 앱 실행
# ════════════════════════════════════════════════════
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=1000, debug=False)
