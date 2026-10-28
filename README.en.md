# ⚡ FreqPilot — Quantitative Strategy Research, Validation & 1x Paper Trading Studio on Official Freqtrade 2026.9

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL%203.0-blue.svg)](SOURCES.md)
[![Engine: Freqtrade 2026.9](https://img.shields.io/badge/Engine-Freqtrade%202026.9-brightgreen.svg)](#)
[![Tests: 1,878+ Passed](https://img.shields.io/badge/Tests-1%2C878%2B%20Passed-brightgreen.svg)](#)
[![Languages](https://img.shields.io/badge/Language-Vi%E1%BA%BFt%20%7C%20English%20%7C%20%E4%B8%AD%E6%96%87%20%7C%20%D0%A0%D0%BE%D1%81%D1%81%D0%B8%D1%8F%20%7C%20%ED%95%9C%EA%B5%AD%EC%96%B4-blue)](#)

[🇻🇳 Tiếng Việt](README.md) | [🇬🇧 English](README.en.md) | [🇨🇳 简体中文](README.zh-CN.md) | [🇷🇺 Русский](README.ru.md) | [🇰🇷 한국어](README.ko.md)

---

**FreqPilot** ([freqpilot.dev](https://freqpilot.dev)) is an evidence-first quantitative strategy research workspace (*Idea → Code → Data Audit → Frozen Backtest → Lookahead/Recursive Checks → 2D Sensitivity & Walk-Forward → 1x Paper Trading & Trade Reconciliation*) built on top of **FreqUI Ultimate v2.1.0** and **100% unmodified official Freqtrade `2026.9`**.

- **Zero Fork Lock-In**: Runs directly on the official `freqtradeorg/freqtrade` `2026.9` image (all 118 core engine files remain byte-for-byte identical).
- **Cryptographic Provenance (`SHA-256` Frozen Bundles)**: Every run snapshots your local `.py` strategy, named `preset` parameters, research config, and local `feather` data (candles + mark + 8h funding) into a verifiable `freqpilot-<id>.zip` bundle that can be exported with a Markdown `Dossier (.md)`, imported on another machine, and re-verified via `Archive Replay`.
- **Safe by Design**: Hard-locked to `dry_run=true`, `Binance USDT-M Futures Isolated 1x`, no live exchange API keys, no silent auto-optimization, and no silent replacement of running paper profiles.

---

## 1. Why FreqPilot Instead of Stock FreqUI or Forked Engines?

| Capability | Stock FreqUI | `frequi-ultimate` (`/strategy-dev`) | **FreqPilot (`/studio`)** |
| :--- | :--- | :--- | :--- |
| **Official Freqtrade `2026.9` Compatibility** | Yes | **No** (returns `404 Endpoint Not Found` without the custom `freqtrade-ultimate` fork) | **Yes (100% official Freqtrade `2026.9`)** |
| **Pre-Run Data & Funding Audit** | No | No | **Audits OHLCV candles, mark price, 8h funding events, gaps & warmup candles before launch** |
| **Frozen Bundles & `.zip` Import/Export** | Loose JSON/ZIP outputs | Form prefill (`reconstitute`) | **`artifact.zip` with `SHA-256`, `.zip` Import, exact trade-by-trade `Archive Replay` & `Dossier (.md)` export** |
| **Lookahead & Recursive Bias Checks** | Separate CLI commands | Not integrated into strategy flow | **Integrated in Step `06 · Checks`, bound to exact code `revision` & `preset`** |
| **Walk-Forward & Post-Hyperopt Holdout** | No | Stitches window % & divides `WFE` by 0 | **Rolling Train/OOS windows, untuned Baseline vs. Candidate comparison & separate Holdout check** |
| **2D Parameter & Fee Sensitivity Matrix** | No | Post-hoc perturbation | **Independent native backtest per `(Param 1 × Param 2 / Fee)` cell** |
| **1x Paper Profile & Trade Reconciliation** | No | Read-only live bot card | **Dedicated 1x Paper worker (`8095`), `history.sqlite` audit log & `PaperReconcileWorkspace`** |

---

## 2. Empirical Benchmark: 10 Public Strategies Audited on Official Freqtrade 2026.9

All runs below were executed on **official Freqtrade `2026.9`** (`BTC/USDT:USDT` + `ETH/USDT:USDT`, Isolated `1x`, `1,000 USDT` wallet, `100 USDT` stake, max `2` open trades, `0.05%` fee per side, actual `1h` mark and `8h` funding rates, **zero parameter tuning**). Full details and hashes are in **[`docs/SCANNED-STRATEGIES-TRIAL.md`](docs/SCANNED-STRATEGIES-TRIAL.md)** and **[`benchmarks/scanned-strategies-summary.json`](benchmarks/scanned-strategies-summary.json)**:

| Strategy (`IStrategy` 1x) | Source & Pinned Commit | Timeframe | 1-Month (`1m` detail) | 6.7-Month (`5m` detail) | Max Drawdown | Profit Factor | Lookahead / Recursive | Audit Outcome |
| :--- | :--- | :---: | ---: | ---: | ---: | ---: | :---: | :--- |
| **`RocketHunterSma501h`** | `rocket-hunter-research` (`d8dae34e`) | `1h (+1d)` | `+6.80 USDT` (2 trades) | **`+61.83 USDT`** (8 trades) | `0.35%` | **`18.29`** | `has_bias=false / ok` | **Survived · Paper 1x Prepared** |
| **`DikibagastEmaRsi1h`** | `Dikibagast EMA RSI` (`a7af9593`) | `1h` | `+8.99 USDT` (5 trades) | **`+44.23 USDT`** (30 trades) | `0.73%` | **`3.96`** | `has_bias=false / ok` | **Survived · 9/9 2D Sensitivity Cells Positive** |
| **`BdrEmaRideFutures1h`** | `BDR-Pro/crypto-futures` (`0df59de9`) | `1h (+1d)` | `+5.55 USDT` (2 trades) | **`+9.37 USDT`** (8 trades) | `1.41%` | **`1.67`** | `has_bias=false / ok` | **Survived Both Windows** |
| **`TrendCoreBagging1h`** | `0x-boss/quant_crypto_strategy` | `1h (+1d)` | `+5.55 USDT` (2 trades) | **`+2.15 USDT`** (2 trades) | `0.15%` | **`2.45`** | `has_bias=false / ok` | **Survived · Low Drawdown** |
| **`CodexBotVibe4h`** | `erfanrhb/CodexBot` (`922e26ee`) | `4h (+1d)` | `+3.30 USDT` (5 trades) | **`-20.02 USDT`** (30 trades) | `2.96%` | `0.67` | `has_bias=false / ok` | **Eliminated on 6.7m Window** |

### Key Anti-Overfit Findings on `DikibagastEmaRsi1h`:
- **2D Parameter Neighbor Continuity (`d28b58b598`)**: All **9/9 cells** in the `3×3` grid (`ema_short ∈ {45, 50, 55} × rsi_entry_offset ∈ {8, 10, 12}`) were positive (`+26.21 USDT` to `+46.09 USDT`, `MaxDD <= 1.52%`) over the 6.7-month sample.
- **Untuned Baseline vs. Hyperopt Candidate (`94b955e45b`)**: In a 2-window Walk-Forward test, the untuned default baseline (`50/100/10/30/2.0`) outperformed the Hyperopt-selected candidate on both Window #1 OOS (`+13.18 USDT` vs. `+6.78 USDT`) and the post-Hyperopt `2026-09-16` to `2026-10-21` holdout interval (`+9.16 USDT, PF 3.44` vs. `-3.46 USDT`).

---

## 3. Quickstart in 3 Commands

Requirements: **Node.js 24**, **pnpm 10.33.2**, **Docker Desktop**, and **PowerShell** (supports Windows PowerShell 5.1, PowerShell 7, and Linux/WSL2).

```powershell
# 1. Initialize isolated user_data, random local API credentials, and 8 starter templates (STOPPED, dry_run=true)
./Initialize.ps1

# 2. Validate configuration, ports, and native strategy schemas before starting
./Start.ps1 -CheckOnly

# 3. Build UI + research image and start services at http://localhost:8090/studio
./Start.ps1 -Build
```

Run the full automated verification suite (`1,745` UI tests, `133` isolated container backend tests, `28` installation guard assertions):
```powershell
./Check.ps1
```

---

## 4. Documentation & License

- **Operations, Backup & Restore Guide**: [`docs/OPERATIONS.md`](docs/OPERATIONS.md)
- **Clean Installation Guide**: [`docs/INSTALL.md`](docs/INSTALL.md)
- **Freqtrade France 5-Strategy Engine Parity Trial**: [`docs/FREQTRADE-FRANCE-TRIAL.md`](docs/FREQTRADE-FRANCE-TRIAL.md)
- **License**: GNU GPL-3.0 (derivative of FreqUI Ultimate v2.1.0 & FreqUI/Freqtrade; see [`SOURCES.md`](SOURCES.md)).
