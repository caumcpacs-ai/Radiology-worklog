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

# 모든 템플릿에 현재 시각 전달
@app.context_processor
def inject_now():
    return {'now': datetime.now().strftime('%Y-%m-%d %H:%M')}

# ── DB 경로 ──────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'worklog.db')

# ── DB 연결 헬퍼 ─────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # dict-like 접근
    return conn

# ── DB 초기화 ─────────────────────────────────────────
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

    # 인수인계 메모
    c.execute('''CREATE TABLE IF NOT EXISTS handover (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        shift TEXT NOT NULL,     -- 오전/오후/야간
        from_person TEXT NOT NULL,
        to_person TEXT NOT NULL,
        content TEXT NOT NULL,
        priority TEXT DEFAULT '일반',  -- 긴급/중요/일반
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )''')

    # 장비 고장·점검 이력
    c.execute('''CREATE TABLE IF NOT EXISTS equipment_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        equipment TEXT NOT NULL,  -- CT1/MRI1/일반1 등
        log_type TEXT NOT NULL,   -- 고장/점검/수리완료/PM
        description TEXT NOT NULL,
        engineer TEXT,
        downtime_hours REAL DEFAULT 0,
        status TEXT DEFAULT '처리중',  -- 처리중/완료
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
        role TEXT,
        note TEXT,
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

    # 업무일지 상태 (제출/반려)
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

    c.execute('''CREATE TABLE IF NOT EXISTS overtime (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        staff_name TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        hours REAL NOT NULL,
        reason TEXT NOT NULL,
        approved_by TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )''')

    # oncall 시간 컬럼 마이그레이션 (기존 DB 호환)
    try:
        c.execute("ALTER TABLE oncall ADD COLUMN start_time TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE staff_roster ADD COLUMN part TEXT DEFAULT ''")
    except Exception:
        pass

    # worklog_status 컬럼 마이그레이션 (기존 DB 호환)
    for col in ['submitted_by', 'submitted_at', 'rejected_to']:
        try:
            c.execute(f"ALTER TABLE oncall ADD COLUMN {col} {typedef}")
        except Exception:
            pass
    try:
        c.execute("ALTER TABLE worklog_status ADD COLUMN rejected_at TEXT DEFAULT ''")
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

# ── 비밀번호 해시 ─────────────────────────────────────
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
# 대시보드 (메인)
# ════════════════════════════════════════════════════
@app.route('/')
@login_required
def dashboard():
    today = date.today().isoformat()
    conn = get_db()

    # 오늘 데이터 (작성 페이지 7개 섹션 전부)
    roster_today    = conn.execute("SELECT * FROM staff_roster   WHERE date=? ORDER BY shift, id",      (today,)).fetchall()
    vacation_today  = conn.execute("SELECT * FROM vacation        WHERE start_date<=? AND end_date>=? ORDER BY staff_name", (today, today)).fetchall()
    oncall_today    = conn.execute("SELECT * FROM oncall          WHERE date=? ORDER BY modality",       (today,)).fetchall()
    overtime_today  = conn.execute("SELECT * FROM overtime        WHERE date=? ORDER BY staff_name",     (today,)).fetchall()
    equipment_today = conn.execute("SELECT * FROM equipment_log   WHERE date=? ORDER BY equipment",      (today,)).fetchall()
    handover_today  = conn.execute("SELECT * FROM handover        WHERE date=? ORDER BY shift, id",      (today,)).fetchall()
    issues_today    = conn.execute("SELECT * FROM issues          WHERE date=? ORDER BY severity, id",   (today,)).fetchall()

    # 전체 미해결/처리중 (KPI 툴팁)
    issues_open_rows  = conn.execute("SELECT * FROM issues WHERE status='진행중' ORDER BY severity, date DESC LIMIT 10").fetchall()
    equip_active_rows = conn.execute("SELECT * FROM equipment_log WHERE status='처리중' ORDER BY date DESC LIMIT 10").fetchall()

    conn.close()
    return render_template('dashboard.html',
        today=today,
        roster_today=roster_today, vacation_today=vacation_today,
        oncall_today=oncall_today, overtime_today=overtime_today,
        equipment_today=equipment_today, handover_today=handover_today,
        issues_today=issues_today,
        issues_open_rows=issues_open_rows, equip_active_rows=equip_active_rows)

# ════════════════════════════════════════════════════
# 특이사항·이슈
# ════════════════════════════════════════════════════
@app.route('/issues')
@login_required
def issues():
    conn = get_db()
    rows = conn.execute("SELECT * FROM issues ORDER BY date DESC, created_at DESC").fetchall()
    conn.close()
    return render_template('issues.html', rows=rows)

@app.route('/issues/add', methods=['GET', 'POST'])
@login_required
def issue_add():
    if request.method == 'POST':
        conn = get_db()
        conn.execute("INSERT INTO issues (date,category,severity,title,content,status,author) VALUES (?,?,?,?,?,?,?)",
            (request.form['date'], request.form['category'], request.form['severity'],
             request.form['title'], request.form['content'], request.form['status'],
             session['name']))
        conn.commit(); conn.close()
        flash('이슈가 등록되었습니다.', 'success')
        return redirect(url_for('issues'))
    return render_template('issue_form.html', row=None, today=date.today().isoformat())

@app.route('/issues/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def issue_edit(id):
    conn = get_db()
    if request.method == 'POST':
        conn.execute("UPDATE issues SET date=?,category=?,severity=?,title=?,content=?,status=? WHERE id=?",
            (request.form['date'], request.form['category'], request.form['severity'],
             request.form['title'], request.form['content'], request.form['status'], id))
        conn.commit(); conn.close()
        flash('수정되었습니다.', 'success')
        return redirect(url_for('issues'))
    row = conn.execute("SELECT * FROM issues WHERE id=?", (id,)).fetchone()
    conn.close()
    return render_template('issue_form.html', row=row, today=date.today().isoformat())

@app.route('/issues/delete/<int:id>')
@login_required
def issue_delete(id):
    conn = get_db()
    conn.execute("DELETE FROM issues WHERE id=?", (id,))
    conn.commit(); conn.close()
    flash('삭제되었습니다.', 'info')
    return redirect(url_for('issues'))

# ════════════════════════════════════════════════════
# 인수인계
# ════════════════════════════════════════════════════
@app.route('/handover')
@login_required
def handover():
    conn = get_db()
    rows = conn.execute("SELECT * FROM handover ORDER BY date DESC, created_at DESC").fetchall()
    conn.close()
    return render_template('handover.html', rows=rows)

@app.route('/handover/add', methods=['GET', 'POST'])
@login_required
def handover_add():
    if request.method == 'POST':
        conn = get_db()
        conn.execute("INSERT INTO handover (date,shift,from_person,to_person,content,priority) VALUES (?,?,?,?,?,?)",
            (request.form['date'], request.form['shift'], request.form['from_person'],
             request.form['to_person'], request.form['content'], request.form['priority']))
        conn.commit(); conn.close()
        flash('인수인계가 등록되었습니다.', 'success')
        return redirect(url_for('handover'))
    return render_template('handover_form.html', row=None, today=date.today().isoformat())

@app.route('/handover/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def handover_edit(id):
    conn = get_db()
    if request.method == 'POST':
        conn.execute("UPDATE handover SET date=?,shift=?,from_person=?,to_person=?,content=?,priority=? WHERE id=?",
            (request.form['date'], request.form['shift'], request.form['from_person'],
             request.form['to_person'], request.form['content'], request.form['priority'], id))
        conn.commit(); conn.close()
        flash('수정되었습니다.', 'success')
        return redirect(url_for('handover'))
    row = conn.execute("SELECT * FROM handover WHERE id=?", (id,)).fetchone()
    conn.close()
    return render_template('handover_form.html', row=row, today=date.today().isoformat())

@app.route('/handover/delete/<int:id>')
@login_required
def handover_delete(id):
    conn = get_db()
    conn.execute("DELETE FROM handover WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect(url_for('handover'))

# ════════════════════════════════════════════════════
# 장비 고장·점검
# ════════════════════════════════════════════════════
@app.route('/equipment')
@login_required
def equipment():
    conn = get_db()
    rows = conn.execute("SELECT * FROM equipment_log ORDER BY date DESC, created_at DESC").fetchall()
    conn.close()
    return render_template('equipment.html', rows=rows)

@app.route('/equipment/add', methods=['GET', 'POST'])
@login_required
def equipment_add():
    if request.method == 'POST':
        conn = get_db()
        conn.execute("INSERT INTO equipment_log (date,equipment,log_type,description,engineer,downtime_hours,status) VALUES (?,?,?,?,?,?,?)",
            (request.form['date'], request.form['equipment'], request.form['log_type'],
             request.form['description'], request.form.get('engineer',''),
             float(request.form.get('downtime_hours', 0) or 0), request.form['status']))
        conn.commit(); conn.close()
        flash('장비 이력이 등록되었습니다.', 'success')
        return redirect(url_for('equipment'))
    return render_template('equipment_form.html', row=None, today=date.today().isoformat())

@app.route('/equipment/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def equipment_edit(id):
    conn = get_db()
    if request.method == 'POST':
        conn.execute("UPDATE equipment_log SET date=?,equipment=?,log_type=?,description=?,engineer=?,downtime_hours=?,status=? WHERE id=?",
            (request.form['date'], request.form['equipment'], request.form['log_type'],
             request.form['description'], request.form.get('engineer',''),
             float(request.form.get('downtime_hours', 0) or 0), request.form['status'], id))
        conn.commit(); conn.close()
        flash('수정되었습니다.', 'success')
        return redirect(url_for('equipment'))
    row = conn.execute("SELECT * FROM equipment_log WHERE id=?", (id,)).fetchone()
    conn.close()
    return render_template('equipment_form.html', row=row, today=date.today().isoformat())

@app.route('/equipment/delete/<int:id>')
@login_required
def equipment_delete(id):
    conn = get_db()
    conn.execute("DELETE FROM equipment_log WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect(url_for('equipment'))

# ════════════════════════════════════════════════════
# 휴가 현황
# ════════════════════════════════════════════════════
@app.route('/vacation')
@login_required
def vacation():
    conn = get_db()
    rows = conn.execute("SELECT * FROM vacation ORDER BY start_date DESC").fetchall()
    conn.close()
    return render_template('vacation.html', rows=rows)

@app.route('/vacation/add', methods=['GET', 'POST'])
@login_required
def vacation_add():
    if request.method == 'POST':
        conn = get_db()
        conn.execute("INSERT INTO vacation (staff_name,vacation_type,start_date,end_date,days,reason,status) VALUES (?,?,?,?,?,?,?)",
            (request.form['staff_name'], request.form['vacation_type'],
             request.form['start_date'], request.form['end_date'],
             float(request.form['days']), request.form.get('reason',''), request.form['status']))
        conn.commit(); conn.close()
        flash('휴가가 등록되었습니다.', 'success')
        return redirect(url_for('vacation'))
    return render_template('vacation_form.html', row=None, today=date.today().isoformat())

@app.route('/vacation/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def vacation_edit(id):
    conn = get_db()
    if request.method == 'POST':
        conn.execute("UPDATE vacation SET staff_name=?,vacation_type=?,start_date=?,end_date=?,days=?,reason=?,status=? WHERE id=?",
            (request.form['staff_name'], request.form['vacation_type'],
             request.form['start_date'], request.form['end_date'],
             float(request.form['days']), request.form.get('reason',''), request.form['status'], id))
        conn.commit(); conn.close()
        flash('수정되었습니다.', 'success')
        return redirect(url_for('vacation'))
    row = conn.execute("SELECT * FROM vacation WHERE id=?", (id,)).fetchone()
    conn.close()
    return render_template('vacation_form.html', row=row, today=date.today().isoformat())

@app.route('/vacation/delete/<int:id>')
@login_required
def vacation_delete(id):
    conn = get_db()
    conn.execute("DELETE FROM vacation WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect(url_for('vacation'))

# ════════════════════════════════════════════════════
# On-call 현황
# ════════════════════════════════════════════════════
@app.route('/oncall')
@login_required
def oncall():
    conn = get_db()
    rows = conn.execute("SELECT * FROM oncall ORDER BY date DESC, modality").fetchall()
    conn.close()
    return render_template('oncall.html', rows=rows)

@app.route('/oncall/add', methods=['GET', 'POST'])
@login_required
def oncall_add():
    if request.method == 'POST':
        conn = get_db()
        conn.execute("INSERT INTO oncall (date,staff_name,modality,phone,note) VALUES (?,?,?,?,?)",
            (request.form['date'], request.form['staff_name'], request.form['modality'],
             request.form.get('phone',''), request.form.get('note','')))
        conn.commit(); conn.close()
        flash('On-call이 등록되었습니다.', 'success')
        return redirect(url_for('oncall'))
    return render_template('oncall_form.html', row=None, today=date.today().isoformat())

@app.route('/oncall/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def oncall_edit(id):
    conn = get_db()
    if request.method == 'POST':
        conn.execute("UPDATE oncall SET date=?,staff_name=?,modality=?,phone=?,note=? WHERE id=?",
            (request.form['date'], request.form['staff_name'], request.form['modality'],
             request.form.get('phone',''), request.form.get('note',''), id))
        conn.commit(); conn.close()
        flash('수정되었습니다.', 'success')
        return redirect(url_for('oncall'))
    row = conn.execute("SELECT * FROM oncall WHERE id=?", (id,)).fetchone()
    conn.close()
    return render_template('oncall_form.html', row=row, today=date.today().isoformat())

@app.route('/oncall/delete/<int:id>')
@login_required
def oncall_delete(id):
    conn = get_db()
    conn.execute("DELETE FROM oncall WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect(url_for('oncall'))

# ════════════════════════════════════════════════════
# 연장근무
# ════════════════════════════════════════════════════
@app.route('/overtime')
@login_required
def overtime():
    conn = get_db()
    rows = conn.execute("SELECT * FROM overtime ORDER BY date DESC").fetchall()
    conn.close()
    return render_template('overtime.html', rows=rows)

@app.route('/overtime/add', methods=['GET', 'POST'])
@login_required
def overtime_add():
    if request.method == 'POST':
        st = request.form['start_time']
        et = request.form['end_time']
        # 시간 계산
        try:
            h = (datetime.strptime(et,'%H:%M') - datetime.strptime(st,'%H:%M')).seconds / 3600
        except:
            h = 0
        conn = get_db()
        conn.execute("INSERT INTO overtime (date,staff_name,start_time,end_time,hours,reason,approved_by) VALUES (?,?,?,?,?,?,?)",
            (request.form['date'], request.form['staff_name'], st, et, round(h,1),
             request.form['reason'], request.form.get('approved_by','')))
        conn.commit(); conn.close()
        flash('연장근무가 등록되었습니다.', 'success')
        return redirect(url_for('overtime'))
    return render_template('overtime_form.html', row=None, today=date.today().isoformat())

@app.route('/overtime/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def overtime_edit(id):
    conn = get_db()
    if request.method == 'POST':
        st = request.form['start_time']
        et = request.form['end_time']
        try:
            h = (datetime.strptime(et,'%H:%M') - datetime.strptime(st,'%H:%M')).seconds / 3600
        except:
            h = 0
        conn.execute("UPDATE overtime SET date=?,staff_name=?,start_time=?,end_time=?,hours=?,reason=?,approved_by=? WHERE id=?",
            (request.form['date'], request.form['staff_name'], st, et, round(h,1),
             request.form['reason'], request.form.get('approved_by',''), id))
        conn.commit(); conn.close()
        flash('수정되었습니다.', 'success')
        return redirect(url_for('overtime'))
    row = conn.execute("SELECT * FROM overtime WHERE id=?", (id,)).fetchone()
    conn.close()
    return render_template('overtime_form.html', row=row, today=date.today().isoformat())

@app.route('/overtime/delete/<int:id>')
@login_required
def overtime_delete(id):
    conn = get_db()
    conn.execute("DELETE FROM overtime WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect(url_for('overtime'))

# ════════════════════════════════════════════════════
# 사용자 관리 (관리자 전용)
# ════════════════════════════════════════════════════
@app.route('/users')
@login_required
def users():
    if session.get('role') != 'admin':
        flash('관리자만 접근 가능합니다.', 'danger')
        return redirect(url_for('dashboard'))
    conn = get_db()
    rows = conn.execute("SELECT id, username, name, role, created_at FROM users ORDER BY id").fetchall()
    conn.close()
    return render_template('users.html', rows=rows)

@app.route('/users/add', methods=['GET', 'POST'])
@login_required
def user_add():
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        conn = get_db()
        try:
            conn.execute("INSERT INTO users (username, password, name, role) VALUES (?,?,?,?)",
                (request.form['username'], hash_pw(request.form['password']),
                 request.form['name'], request.form['role']))
            conn.commit()
            flash('사용자가 추가되었습니다.', 'success')
        except sqlite3.IntegrityError:
            flash('이미 존재하는 아이디입니다.', 'danger')
        conn.close()
        return redirect(url_for('users'))
    return render_template('user_form.html')

@app.route('/users/delete/<int:id>')
@login_required
def user_delete(id):
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect(url_for('users'))

# ════════════════════════════════════════════════════
# 작성 (날짜별 통합 입력)
# ════════════════════════════════════════════════════
@app.route('/write')
@login_required
def write():
    sel = request.args.get('date', date.today().isoformat())
    conn = get_db()
    ws = conn.execute("SELECT * FROM worklog_status WHERE date=?", (sel,)).fetchone()

    data = {
        'roster':    conn.execute("SELECT * FROM staff_roster   WHERE date=? ORDER BY shift, id", (sel,)).fetchall(),
        'vacation':  conn.execute("SELECT * FROM vacation        WHERE start_date<=? AND end_date>=? ORDER BY staff_name", (sel, sel)).fetchall(),
        'oncall':    conn.execute("SELECT * FROM oncall          WHERE date=? ORDER BY modality", (sel,)).fetchall(),
        'overtime':  conn.execute("SELECT * FROM overtime        WHERE date=? ORDER BY staff_name", (sel,)).fetchall(),
        'equipment': conn.execute("SELECT * FROM equipment_log   WHERE date=? ORDER BY equipment", (sel,)).fetchall(),
        'handover':  conn.execute("SELECT * FROM handover        WHERE date=? ORDER BY shift, id", (sel,)).fetchall(),
        'issues':    conn.execute("SELECT * FROM issues          WHERE date=? ORDER BY severity, id", (sel,)).fetchall(),
    }
    conn.close()
    wl_status = ws['status'] if ws else None
    return render_template('write.html', sel=sel, wl_status=wl_status, **data)

# 작성 페이지 전용 POST 라우트 (저장 후 /write?date=... 로 복귀)
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
    conn.execute("UPDATE staff_roster SET shift=?,staff_name=?,role=?,note=? WHERE id=?",
        (request.form['shift'], request.form['staff_name'],
         request.form.get('role',''), request.form.get('note',''), id))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))

@app.route('/write/roster/delete/<int:id>')
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
    start = request.form['start_date']
    conn = get_db()
    conn.execute("INSERT INTO vacation (staff_name,vacation_type,start_date,end_date,days,reason,status) VALUES (?,?,?,?,?,?,?)",
        (request.form['staff_name'], request.form['vacation_type'],
         start, start, 1, '', '승인'))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/vacation/edit/<int:id>', methods=['POST'])
@login_required
def write_vacation_edit(id):
    conn = get_db()
    conn.execute("UPDATE vacation SET staff_name=?,vacation_type=?,start_date=?,end_date=? WHERE id=?",
        (request.form['staff_name'], request.form['vacation_type'], start, start, id))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=start))


@app.route('/write/vacation/delete/<int:id>', methods=['POST'])
@login_required
def write_vacation_delete(id):
    conn = get_db()
    r = conn.execute("SELECT start_date FROM vacation WHERE id=?", (id,)).fetchone()
    d = r['start_date'] if r else date.today().isoformat()
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
    conn.execute("INSERT INTO oncall (date,staff_name,modality,phone,note,start_time,end_time) VALUES (?,?,?,?,?,?,?)",
        (d, request.form['staff_name'], request.form['modality'],
         '', request.form.get('note',''),
         request.form.get('start_time',''), request.form.get('end_time','')))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/oncall/edit/<int:id>', methods=['POST'])
@login_required
def write_oncall_edit(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM oncall WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    conn.execute("UPDATE oncall SET staff_name=?,modality=?,note=?,start_time=?,end_time=? WHERE id=?",
        (request.form['staff_name'], request.form['modality'],
         request.form.get('note',''),
         request.form.get('start_time',''), request.form.get('end_time',''), id))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))

@app.route('/write/oncall/delete/<int:id>')
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
    st = request.form['start_time']; et = request.form['end_time']
    try:
        h = round((datetime.strptime(et,'%H:%M') - datetime.strptime(st,'%H:%M')).seconds / 3600, 1)
    except:
        h = 0
    conn = get_db()
    conn.execute("INSERT INTO overtime (date,staff_name,start_time,end_time,hours,reason,approved_by) VALUES (?,?,?,?,?,?,?)",
        (d, request.form['staff_name'], st, et, h, request.form['reason'], ''))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/overtime/edit/<int:id>', methods=['POST'])
@login_required
def write_overtime_edit(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM overtime WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    st = request.form['start_time']; et = request.form['end_time']
    try:
        h = round((datetime.strptime(et,'%H:%M') - datetime.strptime(st,'%H:%M')).seconds / 3600, 1)
    except:
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
    conn.execute("INSERT INTO equipment_log (date,equipment,log_type,description,engineer,downtime_hours,status) VALUES (?,?,?,?,?,?,?)",
        (d, request.form['equipment'], request.form['log_type'], request.form['description'],
         request.form.get('engineer',''), float(request.form.get('downtime_hours',0) or 0), request.form['status']))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))


@app.route('/write/equipment/edit/<int:id>', methods=['POST'])
@login_required
def write_equipment_edit(id):
    conn = get_db()
    r = conn.execute("SELECT date FROM equipment_log WHERE id=?", (id,)).fetchone()
    d = r['date'] if r else date.today().isoformat()
    conn.execute("UPDATE equipment_log SET equipment=?,log_type=?,description=?,engineer=?,downtime_hours=?,status=? WHERE id=?",
        (request.form['equipment'], request.form['log_type'], request.form['description'],
         request.form.get('engineer',''), float(request.form.get('downtime_hours',0) or 0),
         request.form['status'], id))
    conn.commit(); conn.close()
    return redirect(url_for('write', date=d))

@app.route('/write/equipment/delete/<int:id>')
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
    conn.execute("INSERT INTO issues (date,category,severity,title,content,status,author) VALUES (?,?,?,?,?,?,?)",
        (d, request.form['category'], request.form['severity'],
         request.form['title'], request.form['content'],
         request.form.get('status','진행중'), session['name']))
    conn.commit(); conn.close()
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

@app.route('/write/reset/<date_str>')
@login_required
def write_reset(date_str):
    conn = get_db()
    conn.execute("DELETE FROM staff_roster  WHERE date=?", (date_str,))
    conn.execute("DELETE FROM oncall        WHERE date=?", (date_str,))
    conn.execute("DELETE FROM overtime      WHERE date=?", (date_str,))
    conn.execute("DELETE FROM equipment_log WHERE date=?", (date_str,))
    conn.execute("DELETE FROM handover      WHERE date=?", (date_str,))
    conn.execute("DELETE FROM issues        WHERE date=?", (date_str,))
    conn.execute("DELETE FROM vacation      WHERE start_date=? AND end_date=?", (date_str, date_str))
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

# ════════════════════════════════════════════════════
# 업무일지 리스트
# ════════════════════════════════════════════════════
@app.route('/worklog')
@login_required
def worklog_list():
    date_from = request.args.get('date_from', '')
    date_to   = request.args.get('date_to', '')
    conn = get_db()
    # 관리자: 전체 제출/반려 목록 / 사용자: 본인 제출 + 본인에게 반려된 항목
    if session.get('role') == 'admin':
        statuses = conn.execute(
            "SELECT * FROM worklog_status ORDER BY date DESC"
        ).fetchall()
        users = conn.execute("SELECT username, name FROM users ORDER BY name").fetchall()
    else:
        statuses = conn.execute(
            """SELECT * FROM worklog_status
            WHERE (status='제출' AND submitted_by=?)
               OR (status='반려' AND rejected_to=?)
            ORDER BY date DESC""",
            (session['user'], session['user'])
        ).fetchall()
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
# 업무일지 반려
# ════════════════════════════════════════════════════
@app.route('/worklog/reject/<date_str>', methods=['POST'])
@login_required
def worklog_reject(date_str):
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

@app.route('/worklog/unreject/<date_str>')
@login_required
def user_delete(id):
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (id,))
    conn.commit(); conn.close()
    flash(f'{date_str} 반려가 취소되었습니다.', 'success')
    return redirect(url_for('worklog_list'))

# ════════════════════════════════════════════════════
# 인쇄 뷰
# ════════════════════════════════════════════════════
@app.route('/print/<date_str>')
@login_required
def print_view(date_str):
    conn = get_db()
    data = {
        'roster':    conn.execute("SELECT * FROM staff_roster   WHERE date=? ORDER BY shift,id", (date_str,)).fetchall(),
        'vacation':  conn.execute("SELECT * FROM vacation        WHERE start_date<=? AND end_date>=?", (date_str,date_str)).fetchall(),
        'oncall':    conn.execute("SELECT * FROM oncall          WHERE date=? ORDER BY modality", (date_str,)).fetchall(),
        'overtime':  conn.execute("SELECT * FROM overtime        WHERE date=? ORDER BY staff_name", (date_str,)).fetchall(),
        'equipment': conn.execute("SELECT * FROM equipment_log   WHERE date=? ORDER BY equipment", (date_str,)).fetchall(),
        'handover':  conn.execute("SELECT * FROM handover        WHERE date=? ORDER BY shift,id", (date_str,)).fetchall(),
        'issues':    conn.execute("SELECT * FROM issues          WHERE date=? ORDER BY severity,id", (date_str,)).fetchall(),
    }
    conn.close()
    return render_template('print_view.html', date_str=date_str, **data)

# ════════════════════════════════════════════════════
# 앱 실행
# ════════════════════════════════════════════════════
if __name__ == '__main__':
    init_db()
    # host='0.0.0.0' → 내부망 전체 접근 허용
    app.run(host='0.0.0.0', port=1000, debug=False)
