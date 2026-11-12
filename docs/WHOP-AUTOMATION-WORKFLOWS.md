# WF-04 — Chuỗi Tự Động Hóa Chuyển Đổi Khách Free (`$0`) → Paid (`$39` / `$29/tháng`) Trên Whop

Tài liệu này cung cấp sẵn nội dung **Copy-Paste 1 chạm** cho **Automated Welcome Message** và **Chuỗi 3 Bước Chăm Sóc Tự Động (Day 0 → Day 2 → Day 5)** trên `https://whop.com/dashboard/biz_ZrjmjAGqgcmiVH/` để chuyển đổi tự động người tải gói Free sang mua gói `$39` hoặc thuê bao `$29/tháng`.

---

## 1. Tin Nhắn Chào Mừng Tự Động Ngay Khi Tải Gói `$0` (`Automated Welcome DM` — Day 0)

*Cài đặt tại: `Whop Dashboard → Automations / Welcome Message` cho sản phẩm `FreqPilot Free Starter Bundle (SHA-256 Verified)`*

```markdown
Welcome to **FreqPilot Quant Lab**! 🧪

Your **SHA-256 Verified Starter Bundle** (`TrendCoreBagging1h` — `10,000 USDT` benchmark) is unlocked in the **Files** tab on the left.

**Verify it on your own CPU in 60 seconds:**
1. Download `Whop-Product-1-Free-Starter-Bundle.zip` from the **Files** app.
2. Launch open-source FreqPilot Studio (`https://freqpilot.dev/?utm_source=whop_dm&utm_medium=welcome&utm_campaign=day0_starter`) and import `freqpilot-10k-TrendCoreBagging1h-b0692cd1ca.zip`.
3. Confirm hash `2c5d5ff39e7212a5...` — zero lookahead bias (`has_bias = False`), actual `8h` funding settlement, `5m` intrabar execution.

Want the top 4 higher-frequency / higher-return survivors (led by `RocketHunterSma501h` at **+721.18 USDT / PF 14.90** and `DikibagastEmaRsi1h` passing **9/9 2D Sensitivity cells**)?
👉 **Unlock all 5 Verified 10K Bundles ($39 one-time):**
https://whop.com/freqpilot/freqpilot-verified-strategy-pack-v1-10k-benchmark/?utm_source=whop_dm&utm_medium=welcome&utm_campaign=day0_upsell
```

---

## 2. Bài Ghim Trong Tab `Content` Của Gói Free (Tự Động Upsell Mọi Lúc — Day 2 Hook)

*Cài đặt tại: Tab `Content` trong Whop Hub `FreqPilot` (hiển thị cho thành viên gói `$0`)*

### Tiêu đề:
`Why 10 of 15 "Profitable" Crypto Strategies Failed Our 6.7-Month Multi-Regime Audit (And the 5 That Survived)`

### Nội dung:
```markdown
Most public Freqtrade strategies look great on a 30-day window and bleed out in live markets.

When we ran **9,111+ strategy candidates** through our automated screening pipeline (`https://strategies.freqpilot.dev/?utm_source=whop_content&utm_medium=hub&utm_campaign=day2_education`) and stress-tested the top 15 automated discovery finalists on **6.7 months of 5m intrabar + 8h funding data (`2026-04-01` → `2026-10-21`, `10,000 USDT` wallet, `1x` Isolated)**:

- ❌ **`CodexBotVibe4h`**: Looked profitable on 1-month data → flipped to **`-190.53 USDT` (PF `0.70`)** over 6.7 months.
- ❌ **`CodeAlchemyLowPassFisher1h`**: Flipped to **`-235.51 USDT` (PF `0.52`)** once historical funding & multi-regime chop were included.
- ✅ **Only 5 strategies survived** with `lookahead-analysis = False`, `recursive-analysis = OK`, and positive net expectancy:
  1. **`RocketHunterSma501h`** — **+721.18 USDT (`+7.21%`)** · MaxDD `0.51%` · PF `14.90`
  2. **`TarsisVolTargetSma501h`** — **+648.03 USDT (`+6.48%`)** · MaxDD `0.51%` · PF `13.49` *(9/9 2D Sensitivity pass)*
  3. **`DikibagastEmaRsi1h`** — **+478.54 USDT (`+4.79%`)** · 30 trades · MaxDD `0.86%` · PF `3.69` *(Beat Hyperopt on Sealed WFA Holdout)*
  4. **`BdrEmaRideFutures1h`** — **+116.99 USDT (`+1.17%`)** · MaxDD `1.50%` · PF `1.78`
  5. **`TrendCoreBagging1h`** — **+28.58 USDT (`+0.29%`)** · MaxDD `0.15%` · PF `2.90` *(Included in your Free Starter)*

### Ready to inspect and replay all 5 survivors locally?
- 📦 **One-Time Pack v1 ($39 — Lifetime access to all 5 SHA-256 10K ZIPs + Bilingual Dossiers + `Verify-Bundles.ps1`):**
  https://whop.com/freqpilot/freqpilot-verified-strategy-pack-v1-10k-benchmark/?utm_source=whop_content&utm_medium=hub&utm_campaign=day2_overfit
- 🔄 **Quant Lab Membership ($29/mo — Includes Pack v1 + 2–4 newly audited bundles/month + Weekly 1x Paper Reconciliation Digest):**
  https://whop.com/freqpilot/freqpilot-quant-lab-membership/?utm_source=whop_content&utm_medium=hub&utm_campaign=day5_membership
```

---

## 3. Tin Nhắn Nhắc Nâng Cấp Ngày Thứ 5 (`Abandoned / Free Member Follow-up` — Day 5)

```markdown
Quick check-in from **FreqPilot Quant Lab** 👋

Were you able to replay the free `TrendCoreBagging1h` bundle inside FreqPilot Studio?

If you are building a diversified `BTC/USDT` + `ETH/USDT` `1x` research portfolio, combining low-correlation trend & RSI mean-reversion survivors reduces single-regime stagnation:
- `RocketHunterSma501h` (**+721.18 USDT**, PF `14.90`) captures high-impulse breakouts.
- `DikibagastEmaRsi1h` (**+478.54 USDT**, 30 trades, `9/9` parameter neighbor stability) captures recurring 1h pullbacks.

Grab the complete **5-Strategy Verified Pack v1 ($39 one-time)** with full Python source, frozen feather data, and `SHA-256` verification script here:
👉 https://whop.com/freqpilot/freqpilot-verified-strategy-pack-v1-10k-benchmark/?utm_source=whop_followup&utm_medium=dm&utm_campaign=day5_upgrade
```
