# -*- coding: utf-8 -*-
"""instance 폴더 전체 백업 스크립트 (Windows 작업 스케줄러용)

instance/ 안의 모든 파일을 매일 backups/ 폴더에 백업합니다.
- .db 파일: SQLite 온라인 백업 API 사용 → 앱(app.py)이 실행 중이어도 안전
- 그 외 파일: 그대로 복사
백업 파일은 날짜별로 계속 누적되며 자동 삭제하지 않습니다.
"""
import sqlite3
import shutil
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
BACKUP_DIR = BASE_DIR / "backups"
LOG_PATH = BACKUP_DIR / "backup.log"

# SQLite가 만드는 임시 파일 (온라인 백업이 일관 스냅샷을 만들므로 백업 대상에서 제외)
SKIP_SUFFIXES = ("-wal", "-shm", "-journal")


def log(message: str) -> None:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def backup_sqlite(src_path: Path, dst_path: Path) -> None:
    src = sqlite3.connect(str(src_path))
    dst = sqlite3.connect(str(dst_path))
    try:
        with dst:
            src.backup(dst)
    finally:
        dst.close()
        src.close()


def main() -> None:
    BACKUP_DIR.mkdir(exist_ok=True)

    if not INSTANCE_DIR.exists():
        log(f"실패: instance 폴더가 없습니다 - {INSTANCE_DIR}")
        return

    today = datetime.date.today().isoformat()
    files = [f for f in INSTANCE_DIR.iterdir() if f.is_file()]
    if not files:
        log("실패: instance 폴더에 백업할 파일이 없습니다.")
        return

    ok = 0
    for f in files:
        if f.name.endswith(SKIP_SUFFIXES):
            continue
        # 예: worklog.db -> worklog_2026-07-24.db
        dest = BACKUP_DIR / f"{f.stem}_{today}{f.suffix}"
        try:
            if f.suffix == ".db":
                backup_sqlite(f, dest)
            else:
                shutil.copy2(str(f), str(dest))
            size_kb = dest.stat().st_size / 1024
            log(f"성공: {dest.name} ({size_kb:.1f} KB)")
            ok += 1
        except Exception as e:
            log(f"실패: {f.name} - {e}")

    log(f"완료: {ok}/{len(files)}개 파일 백업")


if __name__ == "__main__":
    main()
