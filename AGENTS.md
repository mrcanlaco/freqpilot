# FreqPilot
User goal: evolve the existing Freqtrade setup toward RoboQuant's strategy-centered workflow, reusing FreqUI Ultimate and official Freqtrade features first. Keep official Freqtrade 2026.9 engine unchanged.
Only backtesting and paper trading on Binance Futures isolated at 1x are authorized. Never set dry_run=false, add trading keys, auto-optimize, or replace the paper strategy silently.
Runtime data/config/databases live outside this repo in ../freqtrade/user_data. Never commit them or credentials. Ultimate comparison stays separate in ../freqtrade-ultimate-compare.
UI is a GPL-3.0 derivative of FreqUI Ultimate v2.1.0; preserve notices. Reuse native stores, API, charts, reports, and Monaco. Backend extensions may manage research files but must not replace engine modules.
Maintain evidence of feature status and comparisons. Do not present planned AI, tick/L2 fills, validation or deployment features as implemented. User has requested 5–10 existing strategies be backtested and compared after development; use a common frozen protocol, record provenance and compatibility changes, no parameter tuning.
