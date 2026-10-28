# ⚡ FreqPilot — Студия количественных исследований, валидации и 1x Paper-трейдинга на базе официального Freqtrade 2026.9

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL%203.0-blue.svg)](SOURCES.md)
[![Engine: Freqtrade 2026.9](https://img.shields.io/badge/Engine-Freqtrade%202026.9-brightgreen.svg)](#)
[![Tests: 1,878+ Passed](https://img.shields.io/badge/Tests-1%2C878%2B%20Passed-brightgreen.svg)](#)
[![Languages](https://img.shields.io/badge/Language-Vi%E1%BA%BFt%20%7C%20English%20%7C%20%E4%B8%AD%E6%96%87%20%7C%20%D0%A0%D0%BE%D1%81%D1%81%D0%B8%D1%8F%20%7C%20%ED%95%9C%EA%B5%AD%EC%96%B4-blue)](#)

[🇻🇳 Tiếng Việt](README.md) | [🇬🇧 English](README.en.md) | [🇨🇳 简体中文](README.zh-CN.md) | [🇷🇺 Русский](README.ru.md) | [🇰🇷 한국어](README.ko.md)

---

**FreqPilot** ([freqpilot.dev](https://freqpilot.dev)) — это рабочая среда для полного цикла разработки торговых стратегий (*Идея → Код → Аудит данных и фандинга → Замороженный бэктест → Проверка Lookahead/Recursive → 2D-матрица чувствительности и Walk-Forward → 1x Paper-трейдинг и сверка сделок*), построенная на базе **FreqUI Ultimate v2.1.0** и **100% неизменённого официального движка Freqtrade `2026.9`**.

- **Без привязки к кастомным форкам (Zero Fork Lock-In)**: Работает напрямую на официальном образе `freqtradeorg/freqtrade` `2026.9` (все 118 базовых файлов движка идентичны оригиналу байт-в-байт).
- **Криптографическая воспроизводимость (`SHA-256` Frozen Bundles)**: Каждый запуск упаковывает локальный `.py` код стратегии, именной пресет параметров, конфигурацию и файлы `feather` (свечи, mark-цены и 8-часовой фандинг) в проверяемый архив `freqpilot-<id>.zip` с возможностью экспорта `Dossier (.md)`, импорта на другой машине и побитовой сверки сделок через `Archive Replay`.
- **Безопасность по умолчанию**: Жёсткое ограничение `dry_run=true`, изолированная маржа `1x` на Binance USDT-M Futures, отсутствие реальных торговых ключей и запрет на скрытую авто-оптимизацию.

---

## 1. Результаты аудита 10 публичных стратегий на официальном Freqtrade 2026.9

Все прогоны выполнены по единому замороженному протоколу на **официальном Freqtrade `2026.9`** (`BTC/USDT:USDT` + `ETH/USDT:USDT`, Isolated `1x`, депозит `1,000 USDT`, ставка `100 USDT`, макс. `2` позиции, комиссия `0.05%` за сторону, реальные mark-цены и 8ч фандинг, **без подгонки параметров**). Полный отчёт: **[`docs/SCANNED-STRATEGIES-TRIAL.md`](docs/SCANNED-STRATEGIES-TRIAL.md)**.

| Стратегия (`IStrategy` 1x) | Источник и коммит | Таймфрейм | 1 месяц (`1m` детализация) | 6.7 месяцев (`5m` детализация) | Макс. просадка | Profit Factor | Lookahead / Recursive | Итог аудита |
| :--- | :--- | :---: | ---: | ---: | ---: | ---: | :---: | :--- |
| **`RocketHunterSma501h`** | `rocket-hunter-research` (`d8dae34e`) | `1h (+1d)` | `+6.80 USDT` (2 сделки) | **`+61.83 USDT`** (8 сделок) | `0.35%` | **`18.29`** | `has_bias=false / ok` | **Прошла · Готов профиль Paper 1x** |
| **`DikibagastEmaRsi1h`** | `Dikibagast EMA RSI` (`a7af9593`) | `1h` | `+8.99 USDT` (5 сделок) | **`+44.23 USDT`** (30 сделок) | `0.73%` | **`3.96`** | `has_bias=false / ok` | **Прошла · 9/9 ячеек 2D-матрицы в плюсе** |
| **`BdrEmaRideFutures1h`** | `BDR-Pro/crypto-futures` (`0df59de9`) | `1h (+1d)` | `+5.55 USDT` (2 сделки) | **`+9.37 USDT`** (8 сделок) | `1.41%` | **`1.67`** | `has_bias=false / ok` | **Прибыльна на обоих окнах** |
| **`TrendCoreBagging1h`** | `0x-boss/quant_crypto_strategy` | `1h (+1d)` | `+5.55 USDT` (2 сделки) | **`+2.15 USDT`** (2 сделки) | `0.15%` | **`2.45`** | `has_bias=false / ok` | **Прошла · Мин. просадка (`0.15%`)** |
| **`CodexBotVibe4h`** | `erfanrhb/CodexBot` (`922e26ee`) | `4h (+1d)` | `+3.30 USDT` (5 сделок) | **`-20.02 USDT`** (30 сделок) | `2.96%` | `0.67` | `has_bias=false / ok` | **Отсеяна на окне 6.7 месяцев** |

---

## 2. Быстрый старт за 3 шага

Требования: **Node.js 24**, **pnpm 10.33.2**, **Docker Desktop** и **PowerShell** (Windows PowerShell 5.1, PowerShell 7 или Linux/WSL2).

```powershell
# 1. Инициализация изолированной папки user_data, случайных локальных ключей API и 8 базовых шаблонов (STOPPED, dry_run=true)
./Initialize.ps1

# 2. Проверка конфигурации, портов и схем стратегий перед запуском
./Start.ps1 -CheckOnly

# 3. Сборка интерфейса и исследовательского образа, запуск сервисов на http://localhost:8090/studio
./Start.ps1 -Build
```
