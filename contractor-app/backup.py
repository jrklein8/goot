"""
Database backups.

  * snapshot(): consistent copy of the SQLite file (online backup API), gzipped into
    DATA_DIR/backups/app-YYYYMMDD-HHMM.db.gz. Keeps the newest BACKUP_KEEP (default 14).
  * If BACKUP_S3_BUCKET is set, the snapshot is also uploaded to that S3-compatible bucket
    (AWS S3, Cloudflare R2, Supabase Storage...). Needs boto3 and:
        BACKUP_S3_BUCKET, BACKUP_S3_ENDPOINT (R2/Supabase only), AWS_ACCESS_KEY_ID,
        AWS_SECRET_ACCESS_KEY, optional BACKUP_S3_PREFIX
  * start_scheduler(): background thread that makes one snapshot a day at BACKUP_HOUR
    (default 3, server local time). Safe under several gunicorn workers: the first one
    to create the day's lock file does the work.
"""

import glob
import gzip
import os
import shutil
import sqlite3
import threading
import time
from datetime import datetime


def _backup_dir(data_dir):
    d = os.path.join(data_dir, "backups")
    os.makedirs(d, exist_ok=True)
    return d


def snapshot(db_path, data_dir, keep=None):
    """Write a gzipped consistent copy of the database. Returns the file path."""
    keep = keep or int(os.environ.get("BACKUP_KEEP", "14"))
    bdir = _backup_dir(data_dir)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    raw = os.path.join(bdir, f"app-{stamp}.db")
    out = raw + ".gz"
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(raw)
    with dst:
        src.backup(dst)          # consistent even while the app is writing
    dst.close()
    src.close()
    with open(raw, "rb") as f_in, gzip.open(out, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    os.remove(raw)
    for old in sorted(glob.glob(os.path.join(bdir, "app-*.db.gz")))[:-keep]:
        os.remove(old)
    _maybe_upload(out)
    return out


def _maybe_upload(path):
    bucket = os.environ.get("BACKUP_S3_BUCKET")
    if not bucket:
        return
    try:
        import boto3  # optional dependency
    except ImportError:
        print("backup: BACKUP_S3_BUCKET is set but boto3 is not installed; add boto3 to requirements.txt")
        return
    kwargs = {}
    if os.environ.get("BACKUP_S3_ENDPOINT"):
        kwargs["endpoint_url"] = os.environ["BACKUP_S3_ENDPOINT"]
    key = (os.environ.get("BACKUP_S3_PREFIX", "contractor-app/").rstrip("/") + "/" + os.path.basename(path))
    boto3.client("s3", **kwargs).upload_file(path, bucket, key)
    print(f"backup: uploaded {key} to {bucket}")


def latest(data_dir):
    files = sorted(glob.glob(os.path.join(_backup_dir(data_dir), "app-*.db.gz")))
    return files[-1] if files else None


def start_scheduler(db_path, data_dir):
    """Daily snapshot at BACKUP_HOUR. Set BACKUP_HOUR=off to disable."""
    hour_env = os.environ.get("BACKUP_HOUR", "3")
    if hour_env.lower() in ("off", "none", ""):
        return
    hour = int(hour_env)

    def loop():
        while True:
            now = datetime.now()
            if now.hour >= hour:
                lock = os.path.join(_backup_dir(data_dir), f".done-{now.strftime('%Y%m%d')}")
                try:
                    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)   # one worker wins
                    os.close(fd)
                    try:
                        snapshot(db_path, data_dir)
                    except Exception as e:  # never kill the thread
                        print(f"backup: failed: {e}")
                        try:
                            os.remove(lock)
                        except OSError:
                            pass
                except FileExistsError:
                    pass
                for old in sorted(glob.glob(os.path.join(_backup_dir(data_dir), ".done-*")))[:-3]:
                    try:
                        os.remove(old)
                    except OSError:
                        pass
            time.sleep(600)

    threading.Thread(target=loop, name="nightly-backup", daemon=True).start()
