# ⚡ FreqPilot — 基于官方 Freqtrade 2026.9 的量化策略研究、验证与 1x 模拟盘工作台

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL%203.0-blue.svg)](SOURCES.md)
[![Engine: Freqtrade 2026.9](https://img.shields.io/badge/Engine-Freqtrade%202026.9-brightgreen.svg)](#)
[![Tests: 1,878+ Passed](https://img.shields.io/badge/Tests-1%2C878%2B%20Passed-brightgreen.svg)](#)
[![Languages](https://img.shields.io/badge/Language-Vi%E1%BA%BFt%20%7C%20English%20%7C%20%E4%B8%AD%E6%96%87%20%7C%20%D0%A0%D0%BE%D1%81%D1%81%D0%B8%D1%8F%20%7C%20%ED%95%9C%EA%B5%AD%EC%96%B4-blue)](#)

[🇻🇳 Tiếng Việt](README.md) | [🇬🇧 English](README.en.md) | [🇨🇳 简体中文](README.zh-CN.md) | [🇷🇺 Русский](README.ru.md) | [🇰🇷 한국어](README.ko.md)

---

**FreqPilot** ([freqpilot.dev](https://freqpilot.dev)) 是以证据为核心的量化策略全生命周期工作台（*策略构思 → 代码编写 → 数据与资金费率审计 → 冻结回测 → Lookahead/Recursive 偏差检验 → 2D 参数敏感度矩阵与 Walk-Forward → 1x 模拟盘与实盘对账*），基于 **FreqUI Ultimate v2.1.0** 构建，并 **100% 兼容原版 Freqtrade `2026.9` 引擎**。

- **无需绑定第三方分叉 (Zero Fork Lock-In)**：直接运行于官方 `freqtradeorg/freqtrade` `2026.9` 镜像之上（118 个核心引擎文件与官方逐字节一致）。
- **`SHA-256` 密码学冻结证据包**：每次运行均将本地 `.py` 策略代码、命名的参数预设 `preset`、研究配置以及本地 `feather` 数据（K线 + 标记价格 + 8小时资金费率）打包为可校验的 `freqpilot-<id>.zip`，支持一键导出 `Dossier (.md)` 报告、跨机导入（`Import .zip`）与逐笔交易复现（`Archive Replay`）。
- **原生安全设计**：强制锁定 `dry_run=true`、币安 USDT-M 永续合约逐仓 `1x`（Isolated 1x），不接触实盘交易私钥，绝不静默篡改或替换正在运行的模拟盘配置。

---

## 1. 为什么选择 FreqPilot？

| 功能维度 | 原版 FreqUI | `frequi-ultimate` (`/strategy-dev`) | **FreqPilot (`/studio`)** |
| :--- | :--- | :--- | :--- |
| **兼容官方 Freqtrade `2026.9`** | 支持 | **不支持**（未安装私有分叉时返回 `404 Endpoint Not Found`） | **支持（100% 官方 Freqtrade `2026.9`）** |
| **运行前数据与资金费率审计** | 无 | 无 | **运行前自动检查 K线、标记价格、8h 资金费率、时间戳断层与预热 K线** |
| **冻结证据包与 `.zip` 导入/导出** | 零散 JSON/ZIP | 仅回填表单 (`reconstitute`) | **`SHA-256` 签名 `artifact.zip`、支持外部导入、逐笔对账 `Archive Replay` 与 `Dossier (.md)` 导出** |
| **前视偏差与递归检验 (Lookahead/Recursive)** | 需命令行单独执行 | 未集成至策略工作流 | **内置于步骤 `06 · 检验`，严格绑定代码 `revision` 与 `preset`** |
| **滚动步进 (Walk-Forward) 与 Holdout 检验** | 无 | 简单拼接百分比、WFE 存在除零误导 | **独立滚动训练/OOS 窗口，保留未调参 Baseline 对照与独立 Holdout 检验** |
| **二维参数与费率敏感度矩阵** | 无 | 事后插值扰动 | **每个 `(参数1 × 参数2 / 费率)` 单元格均为真实的独立原生回测** |
| **1x 模拟盘档案管理与逐笔对账** | 无 | 仅只读展示 | **独立 8095 模拟盘服务、`history.sqlite` 审计日志与 `PaperReconcileWorkspace` 偏差对账** |

---

## 2. 10 个公开策略在官方 Freqtrade 2026.9 上的实证审计结果

以下所有测试均在 **官方 Freqtrade `2026.9`** 上使用统一冻结协议执行（`BTC/USDT:USDT` + `ETH/USDT:USDT`，逐仓 `1x`，初始资金 `1,000 USDT`，单笔 `100 USDT`，最多 `2` 仓位，单边手续费 `0.05%`，包含真实标记价格与 8小时资金费率，**零参数微调**）。完整哈希与细节见 **[`docs/SCANNED-STRATEGIES-TRIAL.md`](docs/SCANNED-STRATEGIES-TRIAL.md)**：

| 策略名称 (`IStrategy` 1x) | 来源与固定 Commit | 周期 | 1 个月 (`1m` 细节) | 6.7 个月 (`5m` 细节) | 最大回撤 | 盈亏比 (PF) | Lookahead / Recursive | 审计结论 |
| :--- | :--- | :---: | ---: | ---: | ---: | ---: | :---: | :--- |
| **`RocketHunterSma501h`** | `rocket-hunter-research` (`d8dae34e`) | `1h (+1d)` | `+6.80 USDT` (2笔) | **`+61.83 USDT`** (8笔) | `0.35%` | **`18.29`** | `has_bias=false / ok` | **通过 · 已生成 1x 模拟盘档案** |
| **`DikibagastEmaRsi1h`** | `Dikibagast EMA RSI` (`a7af9593`) | `1h` | `+8.99 USDT` (5笔) | **`+44.23 USDT`** (30笔) | `0.73%` | **`3.96`** | `has_bias=false / ok` | **通过 · 2D 敏感度矩阵 9/9 格盈利** |
| **`BdrEmaRideFutures1h`** | `BDR-Pro/crypto-futures` (`0df59de9`) | `1h (+1d)` | `+5.55 USDT` (2笔) | **`+9.37 USDT`** (8笔) | `1.41%` | **`1.67`** | `has_bias=false / ok` | **通过长短双周期检验** |
| **`TrendCoreBagging1h`** | `0x-boss/quant_crypto_strategy` | `1h (+1d)` | `+5.55 USDT` (2笔) | **`+2.15 USDT`** (2笔) | `0.15%` | **`2.45`** | `has_bias=false / ok` | **通过 · 极低回撤 (`0.15%`)** |
| **`CodexBotVibe4h`** | `erfanrhb/CodexBot` (`922e26ee`) | `4h (+1d)` | `+3.30 USDT` (5笔) | **`-20.02 USDT`** (30笔) | `2.96%` | `0.67` | `has_bias=false / ok` | **淘汰：单月盈利但 6.7 个月亏损** |

---

## 3. 三步快速启动

环境要求：**Node.js 24**、**pnpm 10.33.2**、**Docker Desktop** 与 **PowerShell**（兼容 Windows PowerShell 5.1、PowerShell 7 与 Linux/WSL2）。

```powershell
# 1. 初始化独立数据目录、随机本地 API 密钥与 8 个示例策略（默认 STOPPED, dry_run=true）
./Initialize.ps1

# 2. 启动前检查配置、端口与原生策略结构
./Start.ps1 -CheckOnly

# 3. 构建前端与研究镜像并启动服务（访问 http://localhost:8090/studio）
./Start.ps1 -Build
```

运行完整自动化验证套件（`1,745` 项前端测试、`133` 项无网络容器后端测试、`28` 项安装保护断言）：
```powershell
./Check.ps1
```
