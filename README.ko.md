# ⚡ FreqPilot — 공식 Freqtrade 2026.9 기반 퀀트 전략 연구·검증 및 1x 페이퍼 트레이딩 스튜디오

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL%203.0-blue.svg)](SOURCES.md)
[![Engine: Freqtrade 2026.9](https://img.shields.io/badge/Engine-Freqtrade%202026.9-brightgreen.svg)](#)
[![Tests: 1,878+ Passed](https://img.shields.io/badge/Tests-1%2C878%2B%20Passed-brightgreen.svg)](#)
[![Languages](https://img.shields.io/badge/Language-Vi%E1%BA%BFt%20%7C%20English%20%7C%20%E4%B8%AD%E6%96%87%20%7C%20%D0%A0%D0%BE%D1%81%D1%81%D0%B8%D1%8F%20%7C%20%ED%95%9C%EA%B5%AD%EC%96%B4-blue)](#)

[🇻🇳 Tiếng Việt](README.md) | [🇬🇧 English](README.en.md) | [🇨🇳 简体中文](README.zh-CN.md) | [🇷🇺 Русский](README.ru.md) | [🇰🇷 한국어](README.ko.md)

---

**FreqPilot** ([freqpilot.dev](https://freqpilot.dev))은 **FreqUI Ultimate v2.1.0** 인터페이스와 **100% 수정되지 않은 공식 Freqtrade `2026.9` 엔진**을 결합한 증거 중심(Evidence-First) 퀀트 전략 연구 워크스페이스(*아이디어 → 코드 → 데이터·펀딩비 감사 → 동결 백테스트 → Lookahead/Recursive 편향 검증 → 2D 민감도 행렬 및 Walk-Forward → 1x 페이퍼 트레이딩 및 체결 대사*)입니다.

- **포크 종속성 제로 (Zero Fork Lock-In)**: 공식 `freqtradeorg/freqtrade` `2026.9` 이미지를 그대로 사용합니다(118개 핵심 엔진 파일 바이트 단위 동일).
- **`SHA-256` 암호화 동결 번들**: 모든 실행은 로컬 `.py` 코드, 파라미터 프리셋(`preset`), 연구 설정 및 로컬 `feather` 데이터(캔들 + 마크 가격 + 8시간 펀딩비)를 `freqpilot-<id>.zip`으로 동결하며, `Dossier (.md)` 내보내기, 외부 `.zip` 가져오기(`Import .zip`) 및 `Archive Replay` 재검증을 지원합니다.
- **설계 단계부터 안전한 격리**: `dry_run=true` 및 바이낸스 USDT-M 선물 격리 `1x`(Isolated 1x)로 고정되며, 실거래 API 키를 받지 않고 실행 중인 페이퍼 프로필을 임의로 변경하지 않습니다.

---

## 1. 공식 Freqtrade 2026.9에서 수행한 10개 공개 전략 실증 감사 결과

모든 테스트는 **공식 Freqtrade `2026.9`**의 동일한 동결 프로토콜(`BTC/USDT:USDT` + `ETH/USDT:USDT`, 격리 `1x`, 시드 `1,000 USDT`, 주문당 `100 USDT`, 최대 `2` 포지션, 편도 수수료 `0.05%`, 실제 마크 가격 및 8시간 펀딩비 반영, **파라미터 튜닝 없음**)로 실행되었습니다. 상세 보고서: **[`docs/SCANNED-STRATEGIES-TRIAL.md`](docs/SCANNED-STRATEGIES-TRIAL.md)**.

| 전략 이름 (`IStrategy` 1x) | 출처 및 고정 커밋 | 타임프레임 | 1개월 (`1m` 정밀) | 6.7개월 (`5m` 정밀) | 최대 낙폭 (MDD) | 손익비 (PF) | Lookahead / Recursive | 감사 결론 |
| :--- | :--- | :---: | ---: | ---: | ---: | ---: | :---: | :--- |
| **`RocketHunterSma501h`** | `rocket-hunter-research` (`d8dae34e`) | `1h (+1d)` | `+6.80 USDT` (2회) | **`+61.83 USDT`** (8회) | `0.35%` | **`18.29`** | `has_bias=false / ok` | **통과 · Paper 1x 프로필 준비 완료** |
| **`DikibagastEmaRsi1h`** | `Dikibagast EMA RSI` (`a7af9593`) | `1h` | `+8.99 USDT` (5회) | **`+44.23 USDT`** (30회) | `0.73%` | **`3.96`** | `has_bias=false / ok` | **통과 · 2D 민감도 9/9칸 모두 흑자** |
| **`BdrEmaRideFutures1h`** | `BDR-Pro/crypto-futures` (`0df59de9`) | `1h (+1d)` | `+5.55 USDT` (2회) | **`+9.37 USDT`** (8회) | `1.41%` | **`1.67`** | `has_bias=false / ok` | **단기·장기 구간 모두 수익 유지** |
| **`TrendCoreBagging1h`** | `0x-boss/quant_crypto_strategy` | `1h (+1d)` | `+5.55 USDT` (2회) | **`+2.15 USDT`** (2회) | `0.15%` | **`2.45`** | `has_bias=false / ok` | **통과 · 초저낙폭 (`0.15%`)** |
| **`CodexBotVibe4h`** | `erfanrhb/CodexBot` (`922e26ee`) | `4h (+1d)` | `+3.30 USDT` (5회) | **`-20.02 USDT`** (30회) | `2.96%` | `0.67` | `has_bias=false / ok` | **탈락: 1개월 흑자이나 6.7개월 적자** |

---

## 2. 3단계 빠른 시작 (Quickstart)

필수 환경: **Node.js 24**, **pnpm 10.33.2**, **Docker Desktop**, **PowerShell** (Windows PowerShell 5.1, PowerShell 7 및 Linux/WSL2 지원).

```powershell
# 1. 독립된 user_data 폴더, 무작위 로컬 API 자격 증명 및 8개 기본 템플릿 초기화 (STOPPED, dry_run=true)
./Initialize.ps1

# 2. 실행 전 설정, 포트 및 네이티브 전략 스키마 검증
./Start.ps1 -CheckOnly

# 3. UI 및 연구 이미지 빌드 후 서비스 시작 (http://localhost:8090/studio)
./Start.ps1 -Build
```
