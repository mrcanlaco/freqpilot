# Upstream and attribution

- UI: FreqUI Ultimate v2.1.0, https://github.com/titouannwtt/frequi-ultimate/tree/v2.1.0, derived from FreqUI. Full original license and source notices remain in ui/. New FreqPilot work adds a strategy-centered workspace and small integration changes.
- Main engine: official Freqtrade 2026.9 image pinned at sha256:9d67afb8eb5f4e1210f4fb067efcbd5e005bd4f1c27f6f3888b8b9fc7f9b5199. Backend Dockerfile adds authenticated research routers; it does not replace optimize/exchange/wallets/persistence engine modules.
- Comparison engine: titouannwtt/freqtrade-ultimate commit 878206c5a3be95d269ed2ff9418071df059171a4, stored and run separately. Its declared engine version is 2026.6. It is not used as the main FreqPilot engine.
- Strategy templates: https://github.com/freqtrade/freqtrade-strategies at f3340ce11f5bdf62f598522e64d1f5638eaa13f5. Per-file provenance, original hashes, installed hashes and compatibility-only changes are recorded in templates/PROVENANCE.json. No automatic tuning was performed.
- RoboQuant supplied workflow inspiration and capability references, not code. No private RoboQuant source was imported into this repo as part of FreqPilot development.

License: GPL-3.0. Preserve original authorship notices and satisfy upstream GPL obligations when distributing derivatives.
