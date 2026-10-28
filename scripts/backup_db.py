"""Daily database backup script.

Usage:
    python scripts/backup_db.py [--output-dir /backups]

Cron example (daily at 2 AM):
    0 2 * * * docker compose exec -T app python scripts/backup_db.py
"""
import argparse
import glob
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(description="Back up the PostgreSQL database")
    parser.add_argument("--output-dir", default="/backups", help="Directory for backup files")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"noc_portal_{timestamp}.sql.gz"
    filepath = os.path.join(args.output_dir, filename)

    database_url = os.getenv("DATABASE_URL", "")
    match = re.match(r"postgresql\+psycopg://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", database_url)
    if not match:
        print(f"Cannot parse DATABASE_URL: {database_url}")
        sys.exit(1)

    user, password, host, port, dbname = match.groups()
    env = os.environ.copy()
    env["PGPASSWORD"] = password

    cmd = ["pg_dump", "-h", host, "-p", port, "-U", user, "-d", dbname, "--format=custom", "--compress=9"]
    with open(filepath, "wb") as f:
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, env=env)

    if result.returncode != 0:
        print(f"Backup failed: {result.stderr.decode()}")
        os.remove(filepath)
        sys.exit(1)

    size = os.path.getsize(filepath)
    print(f"Backup written to {filepath} ({size} bytes)")

    cutoff = time.time() - (30 * 24 * 60 * 60)
    for old_file in glob.glob(os.path.join(args.output_dir, "noc_portal_*.sql.gz")):
        if os.path.getmtime(old_file) < cutoff:
            os.remove(old_file)
            print(f"Pruned old backup: {old_file}")


if __name__ == "__main__":
    main()
