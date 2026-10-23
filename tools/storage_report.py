"""Read-only storage budget report for a private FreqPilot user_data tree."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from workspace_backup import sha256


def report(root: Path, hash_limit_mb: int = 256) -> dict:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("user_data must be a directory")
    groups = defaultdict(lambda: {"files": 0, "bytes": 0})
    candidates = defaultdict(list)
    skipped_hash_bytes = 0
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root)
        group = relative.parts[0] if relative.parts else "(root)"
        size = path.stat().st_size
        groups[group]["files"] += 1
        groups[group]["bytes"] += size
        if size > hash_limit_mb * 1048576:
            skipped_hash_bytes += size
            continue
        # Hash only same-size files; each byte is still checked before it can
        # be called duplicate. This is a report, never a hardlink/delete action.
        candidates[size].append(path)
    duplicates = []
    for same_size in candidates.values():
        if len(same_size) < 2:
            continue
        hashes = defaultdict(list)
        for path in same_size:
            hashes[sha256(path)].append(path.relative_to(root).as_posix())
        for paths in hashes.values():
            if len(paths) > 1:
                duplicates.append({"bytes_each": same_size[0].stat().st_size, "paths": paths})
    return {
        "root": str(root),
        "total_bytes": sum(item["bytes"] for item in groups.values()),
        "groups": dict(sorted(groups.items())),
        "duplicate_candidates": duplicates,
        "hash_skipped_bytes": skipped_hash_bytes,
        "note": "Read-only report. Duplicate candidates are not deleted or hardlinked; immutable references must be checked before cleanup.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("user_data", type=Path)
    parser.add_argument("--hash-limit-mb", type=int, default=256)
    args = parser.parse_args()
    print(json.dumps(report(args.user_data, args.hash_limit_mb), ensure_ascii=False, indent=2))
