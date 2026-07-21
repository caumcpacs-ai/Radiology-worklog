# -*- coding: utf-8 -*-
"""worklog.db 자동 백업 스크립트 (Windows 작업 스케줄러용)

SQLite 온라인 백업 API를 사용하므로 앱(app.py)이 실행 중이어도 안전하게 백업됩니다.
backups/ 폴더에 날짜별 파일로 저장하고, 보관 기간이 지난 백업은 자동 삭제합니다.
"""
import sqlite3
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "instance" / "worklog.db"
BACKUP_DIR = BASE_DIR / "backups"
LOG_PATH = BACKUP_DIR / "backup.log"
KEEP_DAYS = 30  # 백업 보관 일수


def log(message: str) -> None:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def main() -> None:
    BACKUP_DIR.mkdir(exist_ok=True)

    if not DB_PATH.exists():
        log(f"실패: DB 파일이 없습니다 - {DB_PATH}")
        return

    today = datetime.date.today().isoformat()
    backup_path = BACKUP_DIR / f"worklog_{today}.db"

    try:
        src = sqlite3.connect(str(DB_PATH))
        dst = sqlite3.connect(str(backup_path))
        with dst:
            src.backup(dst)
        dst.close()
        src.close()
        size_kb = backup_path.stat().st_size / 1024
        log(f"성공: {backup_path.name} ({size_kb:.1f} KB)")
    except Exception as e:
        log(f"실패: {e}")
        return

    # 보관 기간이 지난 백업 삭제
    cutoff = datetime.date.today() - datetime.timedelta(days=KEEP_DAYS)
    for old in BACKUP_DIR.glob("worklog_*.db"):
        try:
            file_date = datetime.date.fromisoformat(old.stem.replace("worklog_", ""))
        except ValueError:
            continue
        if file_date < cutoff:
            old.unlink()
            log(f"삭제: {old.name} (보관 기간 {KEEP_DAYS}일 초과)")


if __name__ == "__main__":
    main()
