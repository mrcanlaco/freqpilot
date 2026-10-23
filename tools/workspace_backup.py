"""Private, verifiable FreqPilot user_data backup and restore.

SQLite files are copied through SQLite's online backup API, including committed
WAL content. Other files are copied with a before/after stat check. The backup
is private: it can contain local API credentials and must not be shared as a
research export.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


MANIFEST = "freqpilot-backup.json"
SQLITE_SUFFIXES = {".sqlite", ".sqlite3", ".db"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_sqlite(path: Path) -> bool:
    if path.suffix.lower() not in SQLITE_SUFFIXES:
        return False
    with path.open("rb") as stream:
        return stream.read(16) == b"SQLite format 3\x00"


def files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symbolic links are not supported in a private backup")
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.name == MANIFEST:
            raise ValueError(f"Reserved backup file name in source: {MANIFEST}")
        if relative.suffix.lower() in {".sqlite-wal", ".sqlite-shm"}:
            continue
        if relative.name.endswith((".db-wal", ".db-shm", ".sqlite-wal", ".sqlite-shm", ".sqlite3-wal", ".sqlite3-shm")):
            continue
        yield path, relative


def nested(source: Path, destination: Path) -> bool:
    return source == destination or source in destination.parents or destination in source.parents


def backup(source: Path, destination: Path) -> dict:
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if not source.is_dir() or nested(source, destination):
        raise ValueError("Source and destination must be separate directories")
    if destination.exists():
        raise FileExistsError("Backup destination already exists")
    destination.mkdir(parents=True)
    records = []
    for path, relative in files(source):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if is_sqlite(path):
            uri = f"file:{path.as_posix()}?mode=ro"
            with closing(sqlite3.connect(uri, uri=True)) as original, closing(sqlite3.connect(target)) as copy:
                original.backup(copy)
            mode = "sqlite-online-backup"
        else:
            before = path.stat()
            shutil.copy2(path, target)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise RuntimeError(f"Source changed while being copied: {relative.as_posix()}")
            mode = "file-copy"
        records.append({"path": relative.as_posix(), "bytes": target.stat().st_size, "sha256": sha256(target), "mode": mode})
    manifest = {
        "format": "freqpilot-private-backup-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "files": records,
    }
    (destination / MANIFEST).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"files": len(records), "bytes": sum(item["bytes"] for item in records)}


def verify(source: Path) -> dict:
    source = source.resolve(strict=True)
    manifest = json.loads((source / MANIFEST).read_text(encoding="utf-8"))
    if manifest.get("format") != "freqpilot-private-backup-v1":
        raise ValueError("Unsupported or incomplete backup")
    seen = set()
    for item in manifest["files"]:
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts or item["path"] in seen:
            raise ValueError("Unsafe or duplicate manifest path")
        seen.add(item["path"])
        path = source / relative
        if path.is_symlink() or not path.is_file() or path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            raise ValueError(f"Backup verification failed: {relative.as_posix()}")
    return manifest


def restore(source: Path, destination: Path) -> dict:
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if nested(source, destination) or destination.exists():
        raise ValueError("Restore destination must be a new, separate directory")
    manifest = verify(source)
    destination.mkdir(parents=True)
    for item in manifest["files"]:
        relative = Path(item["path"])
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)
    # Do not copy the backup manifest into user_data; confirm the restored bytes.
    for item in manifest["files"]:
        if sha256(destination / item["path"]) != item["sha256"]:
            raise ValueError(f"Restore verification failed: {item['path']}")
    return {"files": len(manifest["files"]), "bytes": sum(item["bytes"] for item in manifest["files"])}


def main() -> int:
    parser = argparse.ArgumentParser(description="Private FreqPilot workspace backup (may contain credentials)")
    parser.add_argument("action", choices=["backup", "verify", "restore"])
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", nargs="?", type=Path)
    args = parser.parse_args()
    if args.action != "verify" and args.destination is None:
        parser.error("destination is required for backup and restore")
    try:
        result = verify(args.source) if args.action == "verify" else (
            backup(args.source, args.destination) if args.action == "backup" else restore(args.source, args.destination)
        )
    except (OSError, ValueError, RuntimeError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"{args.action} failed: {exc}", file=sys.stderr)
        return 1
    count = len(result["files"]) if args.action == "verify" else result["files"]
    print(f"{args.action} complete: {count} files verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
