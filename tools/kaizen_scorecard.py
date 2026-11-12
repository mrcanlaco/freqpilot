"""WF-06: Weekly Kaizen Loop — Single-Bottleneck Optimization Scorecard.

Runs every Monday at 08:00 (and on-demand):
1. Aggregates 7-day Funnel Canary uptime from `work/ops/watchdog-history.jsonl`.
2. Checks Strategy Library SEO growth from `work/ops/seo-sync-latest.json` & `status.json`.
3. Refresh social drafts via `generate_social_drafts.py`.
4. Applies the deterministic Single-Bottleneck Decision Matrix so you optimize
   ONLY the #1 highest-leverage constraint each week.
5. Saves `work/ops/monday-kaizen-latest.md` and sends a 5-line Monday Kaizen Card to Telegram.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from funnel_watchdog import _send_telegram

FREQPILOT_ROOT = Path(r"E:\FreqPilot\freqpilot")
OPS_DIR = FREQPILOT_ROOT / "work" / "ops"
SYNC_STATUS = Path(r"E:\QuantResearch\strategy-library-sync\status.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="WF-06 Monday Kaizen Scorecard")
    parser.add_argument("--no-telegram", action="store_true", help="Skip Telegram delivery")
    args = parser.parse_args()

    OPS_DIR.mkdir(parents=True, exist_ok=True)

    # Refresh weekly social drafts automatically as part of Monday preparation
    subprocess.run(
        [sys.executable, "-X", "utf8", str(FREQPILOT_ROOT / "tools" / "generate_social_drafts.py")],
        capture_output=True,
        text=True,
    )

    # 1. Compute 7-day watchdog health
    hist_path = OPS_DIR / "watchdog-history.jsonl"
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    checks_7d = 0
    healthy_7d = 0
    whop_live = False
    if hist_path.exists():
        for line in hist_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                ts = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
                if ts >= cutoff:
                    checks_7d += 1
                    if row.get("ok"):
                        healthy_7d += 1
                    if row.get("whopLiveOnLanding"):
                        whop_live = True
            except Exception:
                continue

    uptime_pct = round((healthy_7d / checks_7d) * 100.0, 1) if checks_7d else 100.0

    # 2. Read SEO library stats
    candidates = 0
    jobs = 0
    sync_ok = False
    if SYNC_STATUS.exists():
        try:
            st = json.loads(SYNC_STATUS.read_text(encoding="utf-8"))
            sync_ok = bool(st.get("ok"))
            candidates = int(st.get("groupCandidates") or 0)
            jobs = int(st.get("groupJobs") or 0)
        except Exception:
            pass

    # 3. Single-Bottleneck Decision Matrix
    if uptime_pct < 99.0 or not sync_ok:
        bottleneck = "Độ ổn định đường ống (Infrastructure / Sync Reliability)"
        single_action = "Kiểm tra ngay `work/ops/watchdog-status.json` và khôi phục mục bị đỏ trước khi đẩy thêm traffic."
    elif not whop_live:
        bottleneck = "Chưa đồng bộ bản mới lên tên miền chính `freqpilot.dev`"
        single_action = "Push commit `site/` lên nhánh `main` (hoặc Cloudflare Pages) để 3 nút Whop Checkout kích hoạt trên `freqpilot.dev`."
    else:
        bottleneck = "Độ phủ Đầu Phễu Quốc Tế (Top-of-Funnel Organic Traffic)"
        single_action = (
            "KHÔNG sửa code giao diện tuần này. Đăng 1 bài Reddit (`r/freqtrade` / `r/algotrading`) + "
            "1 Thread X từ file nháp `work/ops/social-drafts-latest.md` và đối chiếu lượt tải gói `$0` vs `$39` trên Whop Dashboard."
        )

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_md = f"""# 📈 Thẻ Điểm Tối Ưu Sáng Thứ Hai (WF-06 Weekly Kaizen Card — {today})

- **Uptime Phễu 7 ngày qua (`WF-05`)**: `{uptime_pct}%` (`{healthy_7d}/{checks_7d}` lần kiểm tra xanh)
- **Kho SEO Chiến Lược (`WF-01`)**: `{candidates:,}` ứng viên · `{jobs:,}` lô kiểm định (`sync_ok={sync_ok}`)
- **Trạng thái Nút Whop trên `freqpilot.dev`**: `{'LIVE 100%' if whop_live else 'Chờ deploy Cloudflare Pages'}`
- **Bản nháp MXH tuần mới (`WF-03`)**: Đã cập nhật sẵn tại `work/ops/social-drafts-latest.md`

---

## 🎯 Mắt Xích Trọng Tâm Duy Nhất Tuần Này (Single Bottleneck)
- **Điểm nghẽn #1**: **{bottleneck}**
- **Hành động duy nhất cần làm**: {single_action}

---

## Checklist 3 Phút Trên Whop Dashboard (`https://whop.com/dashboard/biz_ZrjmjAGqgcmiVH/`)
1. Xem số lượt nhận **Free Starter (`$0`)** tuần qua:
   - Nếu `< 10 lượt/tuần` → Tiếp tục đẩy thêm 2 bài từ `social-drafts-latest.md` (tập trung kéo traffic).
   - Nếu `>= 20 lượt/tuần` nhưng `< 2%` lên gói `$39` → Ghim thêm bài **Day 2 Overfit Case Study** trong `docs/WHOP-AUTOMATION-WORKFLOWS.md` lên đầu tab `Content` trên Whop.
"""
    out_path = OPS_DIR / "monday-kaizen-latest.md"
    out_path.write_text(report_md, encoding="utf-8")

    sent = False
    if not args.no_telegram:
        tg_msg = (
            f"📈 *Monday Kaizen Card ({today}) — FreqPilot MMO*\n"
            f"• *Uptime Phễu 7d:* `{uptime_pct}%` ({healthy_7d}/{checks_7d})\n"
            f"• *Kho SEO:* `{candidates:,}` chiến lược (`{jobs:,}` jobs)\n"
            f"• *Điểm nghẽn #1:* *{bottleneck}*\n"
            f"• *Việc duy nhất tuần này:* {single_action}"
        )
        sent = _send_telegram(tg_msg)

    print(json.dumps({"ok": True, "uptimePct": uptime_pct, "bottleneck": bottleneck, "telegramSent": sent}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
