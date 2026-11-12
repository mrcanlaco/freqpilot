"""WF-05: Funnel Canary & Sync Health Watchdog for FreqPilot MMO Ecosystem.

Checks every 6 hours (or on-demand):
1. Public web surfaces (`freqpilot.dev`, `strategies.freqpilot.dev`, `pulse.freqpilot.dev`)
2. Live Whop store & 3 commercial product pages (`$0`, `$39`, `$29/mo`)
3. Local Strategy Library Sync health (`E:/QuantResearch/strategy-library-sync/status.json`)
4. Cryptographic SHA-256 & ZIP archive integrity of `work/release-dossiers-10k` and `work/whop-ready`

Writes structured state to `work/ops/watchdog-status.json` + appends history to
`work/ops/watchdog-history.jsonl` (consumed by WF-06 Monday Kaizen Scorecard).
Sends a Telegram alert ONLY on state failure/recovery (or when `--notify-always` is passed),
reading credentials in memory without ever printing secrets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FREQPILOT_ROOT = Path(r"E:\FreqPilot\freqpilot")
OPS_DIR = FREQPILOT_ROOT / "work" / "ops"
DOSSIERS_10K = FREQPILOT_ROOT / "work" / "release-dossiers-10k"
WHOP_READY = FREQPILOT_ROOT / "work" / "whop-ready"
SYNC_STATUS = Path(r"E:\QuantResearch\strategy-library-sync\status.json")
DAO_VANG_ENV = Path(r"E:\Coding\dao_vang\.env")

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

WEB_TARGETS = [
    ("freqpilot_landing", "https://freqpilot.dev/", "FreqPilot"),
    ("strategy_library", "https://strategies.freqpilot.dev/", ""),
    ("peakpulse_radar", "https://pulse.freqpilot.dev/", ""),
]

WHOP_TARGETS = [
    ("whop_store", "https://whop.com/freqpilot/"),
    ("whop_free_starter", "https://whop.com/freqpilot/freqpilot-free-starter-bundle-sha-256-verified/"),
    ("whop_pack_v1_39", "https://whop.com/freqpilot/freqpilot-verified-strategy-pack-v1-10k-benchmark/"),
    ("whop_membership_29", "https://whop.com/freqpilot/freqpilot-quant-lab-membership/"),
]


def _http_probe(url: str, expected_substring: str = "", timeout_sec: int = 15) -> dict[str, Any]:
    """Probe an HTTPS URL using curl.exe (Cloudflare TLS fingerprint friendly) with urllib fallback."""
    try:
        proc = subprocess.run(
            [
                "curl.exe",
                "-sSL",
                "--max-time",
                str(timeout_sec),
                "-A",
                BROWSER_UA,
                "-w",
                "\n__HTTP_CODE__:%{http_code}",
                url,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        out = proc.stdout or ""
        if "__HTTP_CODE__:" in out:
            body, code_str = out.rsplit("__HTTP_CODE__:", 1)
            code = int(code_str.strip() or "0")
            ok = 200 <= code < 400
            if ok and expected_substring and expected_substring not in body:
                return {"ok": False, "code": code, "error": f"Missing marker '{expected_substring}'"}
            return {
                "ok": ok,
                "code": code,
                "has_whop_links": ("whop.com/freqpilot" in body) if "freqpilot.dev" in url else None,
            }
    except Exception:
        pass

    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = resp.read(65536).decode("utf-8", errors="replace")
            code = int(resp.status)
            ok = 200 <= code < 400
            if ok and expected_substring and expected_substring not in body:
                return {"ok": False, "code": code, "error": f"Missing marker '{expected_substring}'"}
            return {"ok": ok, "code": code}
    except urllib.error.HTTPError as e:
        return {"ok": False, "code": int(e.code), "error": str(e)}
    except Exception as e:
        return {"ok": False, "code": 0, "error": str(e)}


def _check_sync_health(max_age_hours: float = 36.0) -> dict[str, Any]:
    if not SYNC_STATUS.exists():
        return {"ok": False, "error": "Missing status.json"}
    try:
        data = json.loads(SYNC_STATUS.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"Corrupt status.json: {e}"}

    if not data.get("ok"):
        return {"ok": False, "error": str(data.get("error") or "status.ok is false")[:240]}

    completed_raw = data.get("completedAt")
    age_hours = None
    if completed_raw:
        try:
            dt = datetime.fromisoformat(completed_raw.replace("Z", "+00:00"))
            age_hours = round((datetime.now(timezone.utc) - dt).total_seconds() / 3600.0, 2)
            if age_hours > max_age_hours:
                return {"ok": False, "age_hours": age_hours, "error": f"Sync stale ({age_hours}h > {max_age_hours}h)"}
        except Exception:
            pass

    return {
        "ok": True,
        "age_hours": age_hours,
        "groupCandidates": data.get("groupCandidates"),
        "groupJobs": data.get("groupJobs"),
        "changed": data.get("changed"),
    }


def _check_bundles_integrity() -> dict[str, Any]:
    manifest_path = DOSSIERS_10K / "RELEASE-MANIFEST-10K.json"
    if not manifest_path.exists():
        return {"ok": False, "error": "Missing RELEASE-MANIFEST-10K.json"}
    try:
        items = json.loads(manifest_path.read_text(encoding="utf-8"))
        if len(items) != 5:
            return {"ok": False, "error": f"Expected 5 items in 10K manifest, found {len(items)}"}
        for b in items:
            zp = DOSSIERS_10K / b["zip_file"]
            if not zp.exists():
                return {"ok": False, "error": f"Missing {zp.name}"}
            actual = hashlib.sha256(zp.read_bytes()).hexdigest()
            if actual != b["sha256"]:
                return {"ok": False, "error": f"SHA256 mismatch on {zp.name}"}

        for pkg in ("Whop-Product-1-Free-Starter-Bundle.zip", "Whop-Product-2-Verified-Strategy-Pack-v1-10k.zip"):
            p = WHOP_READY / pkg
            if not p.exists():
                return {"ok": False, "error": f"Missing Whop package {pkg}"}
            with zipfile.ZipFile(p, "r") as zf:
                bad = zf.testzip()
                if bad is not None:
                    return {"ok": False, "error": f"Corrupt entry {bad} in {pkg}"}
        return {"ok": True, "verified_10k_bundles": 5, "verified_whop_zips": 2}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _load_telegram_creds() -> tuple[str, str]:
    token = os.environ.get("DAO_VANG_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("DAO_VANG_TELEGRAM_CHAT_ID", "").strip()
    if (not token or not chat_id) and DAO_VANG_ENV.exists():
        for raw_line in DAO_VANG_ENV.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            if k == "DAO_VANG_TELEGRAM_BOT_TOKEN" and not token:
                token = v
            elif k == "DAO_VANG_TELEGRAM_CHAT_ID" and not chat_id:
                chat_id = v
    return token, chat_id


def _send_telegram(message: str) -> bool:
    token, chat_id = _load_telegram_creds()
    if not token or not chat_id:
        return False
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
            return bool(body.get("ok"))
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="FreqPilot MMO Funnel Canary Watchdog")
    parser.add_argument("--notify-always", action="store_true", help="Send Telegram summary even when healthy")
    args = parser.parse_args()

    OPS_DIR.mkdir(parents=True, exist_ok=True)
    status_file = OPS_DIR / "watchdog-status.json"
    history_file = OPS_DIR / "watchdog-history.jsonl"

    prev_ok = True
    if status_file.exists():
        try:
            prev_ok = bool(json.loads(status_file.read_text(encoding="utf-8")).get("ok", True))
        except Exception:
            prev_ok = True

    checks: dict[str, Any] = {}
    failures: list[str] = []

    for name, url, marker in WEB_TARGETS:
        res = _http_probe(url, marker)
        checks[name] = res
        if not res.get("ok"):
            failures.append(f"{name} ({url}): HTTP {res.get('code')} {res.get('error', '')}".strip())

    for name, url in WHOP_TARGETS:
        res = _http_probe(url)
        checks[name] = res
        if not res.get("ok"):
            failures.append(f"{name}: HTTP {res.get('code')} {res.get('error', '')}".strip())

    sync_res = _check_sync_health()
    checks["strategy_library_sync"] = sync_res
    if not sync_res.get("ok"):
        failures.append(f"strategy_library_sync: {sync_res.get('error')}")

    bundle_res = _check_bundles_integrity()
    checks["bundles_sha256"] = bundle_res
    if not bundle_res.get("ok"):
        failures.append(f"bundles_sha256: {bundle_res.get('error')}")

    now_iso = datetime.now(timezone.utc).isoformat()
    overall_ok = len(failures) == 0
    report = {
        "ok": overall_ok,
        "checkedAt": now_iso,
        "failureCount": len(failures),
        "failures": failures,
        "checks": checks,
    }

    status_file.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with history_file.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ts": now_iso,
                    "ok": overall_ok,
                    "failureCount": len(failures),
                    "whopLiveOnLanding": checks.get("freqpilot_landing", {}).get("has_whop_links"),
                    "groupCandidates": sync_res.get("groupCandidates"),
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    notified = False
    if not overall_ok:
        bullet_lines = "\n".join(f"• `{item}`" for item in failures[:6])
        msg = (
            "🚨 *FreqPilot MMO Watchdog — CẢNH BÁO LỖI PHỄU*\n"
            f"• *Thời điểm:* `{now_iso[:19]} UTC`\n"
            f"• *Số mục lỗi:* *{len(failures)}*\n"
            f"{bullet_lines}"
        )
        notified = _send_telegram(msg)
    elif not prev_ok or args.notify_always:
        state_title = "ĐÃ KHÔI PHỤC XANH 100%" if not prev_ok else "BÁO CÁO SỨC KHỎE PHỄU (XANH 100%)"
        msg = (
            f"✅ *FreqPilot MMO Watchdog — {state_title}*\n"
            f"• *Web & SEO:* `freqpilot.dev` / `strategies` / `pulse` = HTTP 200\n"
            f"• *Whop Store & 3 Gói (`$0`, `$39`, `$29/mo`):* Online 100%\n"
            f"• *Strategy Sync:* `{sync_res.get('groupCandidates', 0)}` chiến lược (`ok=true`)\n"
            f"• *Gói SHA-256:* 5/5 Dossier 10k & 2/2 Whop ZIP toàn vẹn"
        )
        notified = _send_telegram(msg)

    print(json.dumps({"ok": overall_ok, "failureCount": len(failures), "telegramNotified": notified}, ensure_ascii=False))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
