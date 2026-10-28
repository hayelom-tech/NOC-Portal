"""Prune old uploaded workbooks and process documents (interim lifecycle policy).

Usage:
    python scripts/prune_uploads.py [--days 90] [--dry-run]
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.database import SessionLocal
from server.models import ProcessDocument, UploadedFile


def main():
    parser = argparse.ArgumentParser(description="Prune old uploads")
    parser.add_argument("--days", type=int, default=90, help="Age threshold in days")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted")
    args = parser.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    with SessionLocal() as db:
        files = db.query(UploadedFile).filter(UploadedFile.uploaded_at < cutoff).all()
        docs = db.query(ProcessDocument).filter(ProcessDocument.created_at < cutoff).all()
        print(f"Found {len(files)} uploaded files and {len(docs)} process documents older than {args.days} days.")
        for f in files:
            print(f"  UploadedFile id={f.id} name={f.original_name} uploaded_at={f.uploaded_at}")
        for d in docs:
            print(f"  ProcessDocument id={d.id} name={d.file_name} created_at={d.created_at}")
        if args.dry_run:
            print("Dry run: no changes made.")
            return
        for f in files:
            db.delete(f)
        for d in docs:
            db.delete(d)
        db.commit()
        print(f"Deleted {len(files)} uploaded files and {len(docs)} process documents.")


if __name__ == "__main__":
    main()
