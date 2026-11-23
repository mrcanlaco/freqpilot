# Public site regression evidence · 2026-11-23

The deployed home and demo HTML matched commit `6bf9794` after line-ending normalization. On the live EN home, iPhone 15 emulation measured 393 CSS px for the viewport and 454 px for the document. Selecting RocketHunter in step 08 showed its ZIP hash alongside Dikibagast's holdout results. [Home before](before-home-en.png) · [RocketHunter before](before-rocket-en.png)

## Seven public demo records

Each row was checked against its successful backtest record, strategy revision and SHA-256 computed over the saved backtest archive. The five Starter/Verified Pack release copies also matched. The last column identifies a separate Walk-forward job for the published 10,000 USDT protocol. An em dash indicates that the public benchmark has no matching result. [Benchmark source](../../../benchmarks/scanned-strategies-summary.json)

| Strategy | Revision prefix | Backtest ID prefix | Backtest ZIP SHA-256 prefix | Walk-forward ID prefix |
| --- | --- | --- | --- | --- |
| DikibagastEmaRsi1h | b82e4ae101 | b9f8eb39c3 | 355afab9d588 | 3215a26798 |
| RocketHunterSma501h | 484cebfefa | fd368e3110 | a97bd2aa06dc | — |
| TarsisVolTargetSma501h | 71d5550cb1 | f29c4c1d9a | d3a223a86af4 | — |
| BdrEmaRideFutures1h | 1474053fd7 | 92ea977e05 | 9ab6887c4d22 | — |
| TrendCoreBagging1h | f1260f2655 | b0692cd1ca | 2c5d5ff39e72 | — |
| CodexBotVibe4h | c1e250bee2 | 916aad1ea4 | 2ae3b88a63f1 | — |
| StarterFuturesResearch | b336e80227 | 813a9807e1 | 44ac8d16221b | — |

Dikibagast's successful holdout record covers September 16 through October 21. The original parameters returned +94.44 USDT across five trades. The Hyperopt candidate returned −50.85 USDT across three. The separately recorded 1,000 USDT Walk-forward jobs for Dikibagast and Tarsis belong to another protocol. [Matched holdout in VI](dikibagast-vi.png) · [Missing result in EN](after-rocket-en.png)

## Published groups and Starter access

The leaderboard contains 15 distinct discovery strategies. Ten have a long-window backtest (April 1 through October 21, 5m detail), of which five had positive P&L. Five have only the shorter screen (September 18 through October 21, 1m detail). CodeAlchemy has both runs and appears once using its long-window result. The bundled StarterFuturesResearch control is outside the discovery list.

From a fresh browser, the Starter card opened TrendCoreBagging1h with its public +28.58 USDT, two trades and the long test period. The second action opens free Whop registration for one SHA-256 Starter bundle containing the configuration and backtest logs. Starter requires no password from the project owner. The full library is reserved for paying customers. The public Whop page displayed “Join for free” and the private library displayed its password form to an anonymous visitor. Verification covered public entry points up to sign-up. [Whop Starter](https://whop.com/freqpilot/freqpilot-free-starter-bundle-sha-256-verified/) · [Paid library](https://strategies.freqpilot.dev/) · [Starter card](starter-vi.png) · [Public sample](sample-vi.png)

## Browser checks

With the UI dependencies installed and Chrome available, run `node --test ui/scripts/check-public-site.mjs` from the repository root. The suite compares all audit rows to the public benchmark, exercises the seven strategy selections in five languages, rejects mismatched evidence identities and checks the home matrix after a strategy change. The EN and VI paths exercise Open Studio, sample results, Walk-forward and the correct Whop offer at 393 × 852 and 1280 × 900 CSS px. Studio and external checkout requests are intercepted in the automated checks.

The local preview also exercised the Starter link and selected results in Orca. Document width matched the viewport in the tested mobile and desktop journeys. [Home after at 393 px](after-home-en.png)
