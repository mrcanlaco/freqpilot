import { describe, it, expect } from 'vitest';
import {
  buildEvidenceCodexPrompt,
  buildResearchDossierMarkdown,
  buildSensitivityPivot,
  buildTradeAnalytics,
  formatLibraryRunSummary,
  latestLibraryRuns,
  libraryMatches,
  libraryUpdated,
  mapWalkForwardWindowRow,
} from '@/utils/strategyLibrary';
import type { LibraryRun } from '@/utils/strategyLibrary';

function run(id: string, created_at: string, status = 'success', profit = 10): LibraryRun {
  return {
    id,
    strategy: 'Fibo',
    revision: id,
    status,
    created_at,
    settings: { timeframe: '5m' },
    summary: { profit_total_abs: profit, total_trades: 2 },
  };
}
describe('Strategy library evidence', () => {
  it('chooses the latest completed run, never the best profit or a failed attempt', () => {
    const latest = latestLibraryRuns([
      run('best', '2026-10-20', 'success', 100),
      run('latest', '2026-10-21', 'success', -5),
      run('failed', '2026-10-22', 'failed'),
    ]);
    expect(latest.get('Fibo')?.id).toBe('latest');
    expect(latest.get('Fibo')?.summary?.profit_total_abs).toBe(-5);
  });
  it('does not invent completed metrics for missing/running/failed results', () => {
    expect(latestLibraryRuns([run('pending', '2026-10-22', 'running')]).size).toBe(0);
    const zero = latestLibraryRuns([run('zero', '2026-10-22', 'success', 0)]).get('Fibo');
    expect(zero?.summary?.profit_total_abs).toBe(0);
    expect(zero?.summary?.max_drawdown_account).toBeUndefined();

    const noSummary = latestLibraryRuns([
      { id: 'bare', strategy: 'Fibo', revision: 'r1', status: 'success', created_at: '2026-10-23', settings: {} },
    ]).get('Fibo');
    expect(formatLibraryRunSummary(noSummary)).toMatchObject({
      hasProfit: false,
      hasTrades: false,
      profitText: '—',
      signedProfitText: '—',
      tradesText: '— lệnh',
      contextText: '— · — lệnh',
    });
    const nonFinite = formatLibraryRunSummary({
      id: 'nan',
      strategy: 'Fibo',
      revision: 'r1',
      status: 'success',
      created_at: '2026-10-23',
      settings: {},
      summary: { profit_total_abs: Number.NaN, total_trades: Number.POSITIVE_INFINITY },
    });
    expect(nonFinite.contextText).toBe('— · — lệnh');
    const exactZero = formatLibraryRunSummary({
      id: 'zero-trades',
      strategy: 'Fibo',
      revision: 'r1',
      status: 'success',
      created_at: '2026-10-23',
      settings: {},
      summary: { profit_total_abs: 0, total_trades: 0 },
    });
    expect(exactZero.contextText).toBe('0.00 USDT · 0 lệnh');
    expect(exactZero.signedProfitText).toBe('+0.00 USDT');
  });
  it('searches names, description and tags together without executing strategies', () => {
    const item = {
      name: 'FiboResearch',
      research: { idea: 'Hồi giá sau đợt tăng', notes: '', tags: ['short', 'ETH'] },
    };
    expect(libraryMatches(item, 'FIBO short eth')).toBe(true);
    expect(libraryMatches(item, 'hồi giá')).toBe(true);
    expect(libraryMatches(item, 'long')).toBe(false);
    expect(libraryMatches({ name: 'Invalid', invalid: true }, 'Invalid')).toBe(true);
  });
  it('sorts by the newer source or metadata date, retaining legacy records', () => {
    expect(libraryUpdated({ name: 'A', modified: 10 })).toBe(10000);
    expect(
      libraryUpdated({
        name: 'A',
        modified: 10,
        research: { idea: '', notes: '', tags: [], updated_at: '2026-10-22' },
      }),
    ).toBe(Date.parse('2026-10-22'));
  });

  it('maps walk-forward windows with train metrics from successful hyperopt without inventing WFE or degradation', () => {
    const successRow = mapWalkForwardWindowRow({
      index: 1,
      train_timerange: '20260701-20260930',
      oos_timerange: '20261001-20261031',
      status: 'success',
      hyperopt: {
        status: 'success',
        best_epoch: {
          epoch: 12,
          metrics: { profit_total: 0.145, profit_total_abs: 145.2, total_trades: 24 },
        },
      },
      baseline: { summary: { profit_total_abs: 20.5, total_trades: 18 } },
      candidate: { summary: { profit_total: 0.062, profit_total_abs: 62.1, total_trades: 15 } },
    });
    expect(successRow).toEqual({
      index: 1,
      train_timerange: '20260701-20260930',
      test_timerange: '20261001-20261031',
      status: 'success',
      train_profit: 0.145,
      train_profit_abs: 145.2,
      train_trades: 24,
      baseline_profit_abs: 20.5,
      baseline_trades: 18,
      test_profit: 0.062,
      test_profit_abs: 62.1,
      test_trades: 15,
      wfe: null,
      degradation: null,
    });

    const failedHyperoptRow = mapWalkForwardWindowRow({
      index: 2,
      train_timerange: '20260801-20261031',
      oos_timerange: '20261101-20261130',
      status: 'failed',
      hyperopt: {
        status: 'failed',
        best_epoch: {
          metrics: { profit_total: 0.5, profit_total_abs: 500, total_trades: 30 },
        },
      },
      candidate: { summary: { profit_total: Number.NaN, profit_total_abs: Number.POSITIVE_INFINITY } },
    });
    expect(failedHyperoptRow.train_profit).toBeNull();
    expect(failedHyperoptRow.train_profit_abs).toBeNull();
    expect(failedHyperoptRow.train_trades).toBeNull();
    expect(failedHyperoptRow.test_profit).toBeNull();
    expect(failedHyperoptRow.test_profit_abs).toBeNull();
    expect(failedHyperoptRow.wfe).toBeNull();
    expect(failedHyperoptRow.degradation).toBeNull();
  });

  it('builds a 2D sensitivity pivot marking baseline and preserving exact zero vs pending/failed', () => {
    const pivot = buildSensitivityPivot({
      axes: [
        { name: 'buy_rsi', base: 30, values: [25, 30] },
        { name: 'sell_rsi', base: 70, values: [65, 70] },
      ],
      cells: [
        {
          index: 0,
          parameters: { buy_rsi: 25, sell_rsi: 65 },
          fee: 0.0005,
          status: 'pending',
          result: null,
        },
        {
          index: 1,
          parameters: { buy_rsi: 25, sell_rsi: 70 },
          fee: 0.0005,
          status: 'failed',
          result: { summary: { profit_total_abs: 99, total_trades: 5 } },
          error: 'Timeout',
        },
        {
          index: 2,
          parameters: { buy_rsi: 30, sell_rsi: 65 },
          fee: 0.0005,
          status: 'success',
          result: { summary: { profit_total_abs: 0, total_trades: 0, max_drawdown_account: 0 } },
        },
        {
          index: 3,
          parameters: { buy_rsi: 30, sell_rsi: 70 },
          fee: 0.0005,
          status: 'success',
          result: { summary: { profit_total_abs: 42.5, total_trades: 14, max_drawdown_account: 0.035 } },
        },
      ],
    });

    expect(pivot.rowAxis.name).toBe('buy_rsi');
    expect(pivot.colAxis.name).toBe('sell_rsi');
    expect(pivot.matrix).toHaveLength(2);
    expect(pivot.matrix[0]).toHaveLength(2);

    expect(pivot.matrix[0]![0]).toMatchObject({
      status: 'pending',
      isBaseline: false,
      profitText: '—',
      tradesText: '—',
      drawdownText: '—',
    });
    expect(pivot.matrix[0]![1]).toMatchObject({
      status: 'failed',
      isBaseline: false,
      profitText: '—',
      tradesText: '—',
      drawdownText: '—',
      error: 'Timeout',
    });
    expect(pivot.matrix[1]![0]).toMatchObject({
      status: 'success',
      isBaseline: false,
      profitText: '0.00 USDT',
      tradesText: '0 lệnh',
      drawdownText: '0.00%',
    });
    expect(pivot.matrix[1]![1]).toMatchObject({
      status: 'success',
      isBaseline: true,
      profitText: '42.50 USDT',
      tradesText: '14 lệnh',
      drawdownText: '3.50%',
    });
  });

  it('builds a Codex prompt with current local run evidence and dash placeholders when summary is missing', () => {
    const withSummary = buildEvidenceCodexPrompt({
      strategy: 'Fibo',
      revision: 'abcdef1234567890',
      timeframe: '15m',
      idea: 'Short hồi Fibo',
      notes: 'Kiểm tra funding',
      latestRun: {
        id: 'run1234567890',
        strategy: 'Fibo',
        revision: 'abcdef1234567890',
        status: 'success',
        created_at: '2026-10-22T00:00:00Z',
        settings: { timerange: '20260918-20261022' },
        summary: { profit_total_abs: 18.4, total_trades: 12 },
      },
      latestCheck: { kind: 'lookahead', status: 'passed' },
    });
    expect(withSummary).toContain('chiến lược Fibo (mã abcdef1234, khung 15m)');
    expect(withSummary).toContain('run1234567 · khoảng 20260918-20261022 · 18.40 USDT · 12 lệnh (khớp mã hiện tại)');
    expect(withSummary).toContain('lookahead · passed');

    const withoutSummary = buildEvidenceCodexPrompt({
      strategy: 'Fibo',
      revision: 'newrev999999',
      idea: '',
      notes: '',
      latestRun: {
        id: 'runbare000000',
        strategy: 'Fibo',
        revision: 'oldrev000000',
        status: 'success',
        created_at: '2026-10-22T00:00:00Z',
        settings: { timerange: '20260918-20261022' },
      },
    });
    expect(withoutSummary).toContain('runbare000 · khoảng 20260918-20261022 · — · — lệnh (mã đã sửa sau lần chạy này)');
  });

  it('computes underwater drawdown, monthly returns, exit reasons, and UTC hourly/weekday patterns from native trades', () => {
    const analytics = buildTradeAnalytics(
      [
        {
          open_date: '2026-09-21T08:15:00Z',
          close_date: '2026-09-21T10:00:00Z',
          profit_abs: 100,
          profit_ratio: 0.1,
          exit_reason: 'roi',
        },
        {
          open_date: '2026-10-06T14:30:00Z',
          close_date: '2026-10-06T16:00:00Z',
          profit_abs: -55,
          profit_ratio: -0.05,
          exit_reason: 'stop_loss',
        },
      ],
      1000,
    );

    expect(analytics.underwater).toHaveLength(2);
    expect(analytics.underwater[0]!.dd_pct).toBeCloseTo(0, 5);
    expect(analytics.underwater[1]!.dd_pct).toBeCloseTo(5, 5);

    expect(analytics.monthly).toEqual([
      { year: 2026, month: 9, profit_abs: 100, trades: 1 },
      { year: 2026, month: 10, profit_abs: -55, trades: 1 },
    ]);

    expect(analytics.exitReasons).toEqual([
      { reason: 'roi', count: 1, avg_profit: 10, total_profit: 100, wins: 1, losses: 0, winrate: 1 },
      { reason: 'stop_loss', count: 1, avg_profit: -5, total_profit: -55, wins: 0, losses: 1, winrate: 0 },
    ]);

    expect(analytics.hourly.hours[8]).toEqual({ hour: 8, avg_profit: 0.1, winrate: 1, trades: 1 });
    expect(analytics.hourly.hours[14]).toEqual({ hour: 14, avg_profit: -0.05, winrate: 0, trades: 1 });
    expect(analytics.weekday.days[0]).toMatchObject({ day: 'Mon', day_index: 0, trades: 1, total_profit: 100, winrate: 1 });
    expect(analytics.weekday.days[1]).toMatchObject({ day: 'Tue', day_index: 1, trades: 1, total_profit: -55, winrate: 0 });
  });

  it('preserves unavailable null vs real zero for missing profit_ratio, zero-trade buckets, and partial-year coverage', () => {
    const partial = buildTradeAnalytics(
      [
        {
          open_date: '2026-08-10T09:00:00Z',
          close_date: '2026-08-10T10:00:00Z',
          profit_abs: 0,
          profit_ratio: 0,
          exit_reason: 'breakeven',
        },
        {
          open_date: '2026-10-12T11:00:00Z',
          close_date: '2026-10-12T12:00:00Z',
          profit_abs: 25,
          profit_ratio: Number.NaN,
          exit_reason: 'roi',
        },
      ],
      1000,
      { start: '2026-08-01T00:00:00Z', end: '2026-10-31T23:59:59Z' },
    );

    // Covered months Aug..Oct exist (Sep has 0 trades -> real 0), months outside Aug..Oct are not invented
    expect(partial.monthly).toEqual([
      { year: 2026, month: 8, profit_abs: 0, trades: 1 },
      { year: 2026, month: 9, profit_abs: 0, trades: 0 },
      { year: 2026, month: 10, profit_abs: 25, trades: 1 },
    ]);

    // Real zero profit_ratio stays 0; missing/NaN profit_ratio yields null (never 0 or diluted average)
    const breakeven = partial.exitReasons.find((r) => r.reason === 'breakeven');
    const roiMissingRatio = partial.exitReasons.find((r) => r.reason === 'roi');
    expect(breakeven).toMatchObject({ avg_profit: 0, total_profit: 0, winrate: 0 });
    expect(roiMissingRatio).toMatchObject({ avg_profit: null, total_profit: 25, winrate: 1 });

    // Hour 9 has real zero; Hour 11 has missing ratio -> avg_profit null; Hour 0 has 0 trades -> null
    expect(partial.hourly.hours[9]).toEqual({ hour: 9, avg_profit: 0, winrate: 0, trades: 1 });
    expect(partial.hourly.hours[11]).toEqual({ hour: 11, avg_profit: null, winrate: 1, trades: 1 });
    expect(partial.hourly.hours[0]).toEqual({ hour: 0, avg_profit: null, winrate: null, trades: 0 });

    // Monday (index 0) had 2 trades, one with NaN profit_ratio -> avg_profit must be null, not 0/2
    expect(partial.weekday.days[0]).toMatchObject({
      day: 'Mon',
      trades: 2,
      avg_profit: null,
      total_profit: 25,
      winrate: 0.5,
    });
    // Tuesday (index 1) had 0 trades -> avg_profit, total_profit, winrate are all null
    expect(partial.weekday.days[1]).toEqual({
      day: 'Tue',
      day_index: 1,
      trades: 0,
      avg_profit: null,
      total_profit: null,
      winrate: null,
    });

    // Non-finite profit_abs in any trade suppresses underwater and monthly curves instead of partial sums
    const corrupt = buildTradeAnalytics([
      { close_date: '2026-09-21T10:00:00Z', profit_abs: 10, profit_ratio: 0.01 },
      { close_date: '2026-09-22T10:00:00Z', profit_abs: Number.NaN, profit_ratio: 0.01 },
    ]);
    expect(corrupt.underwater).toEqual([]);
    expect(corrupt.monthly).toEqual([]);
  });

  it('builds a research dossier markdown with provenance, SHA256 verification steps, and explicit limitations', () => {
    const md = buildResearchDossierMarkdown({
      strategy: 'FAdxSmaStrategy',
      revision: '450ed20d7f123456',
      idea: 'Theo xu hướng ADX + SMA',
      notes: 'Chỉ đánh khung 1h',
      tags: ['trend', 'adx'],
      run: {
        id: 'aabbccddeeff00112233445566778899',
        strategy: 'FAdxSmaStrategy',
        revision: '450ed20d7f123456',
        status: 'success',
        created_at: '2026-10-22T00:00:00Z',
        artifact_sha256: '11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff',
        settings: {
          timerange: '20260918-20261022',
          timeframe: '1h',
          timeframe_detail: '1m',
          dry_run_wallet: 1000,
          stake_amount: '100',
          max_open_trades: 2,
        },
        summary: {
          total_trades: 14,
          profit_total_abs: 28.5,
          profit_total: 0.0285,
          max_drawdown_account: 0.012,
          profit_factor: 1.45,
        },
      },
      checks: [{ kind: 'lookahead', status: 'passed' }],
      exitReasons: [{ reason: 'roi', count: 10, avg_profit: 1.2, total_profit: 35, winrate: 1 }],
    });

    expect(md).toContain('# Hồ sơ nghiên cứu (Dossier): FAdxSmaStrategy');
    expect(md).toContain('`11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff`');
    expect(md).toContain('+28.50 USDT');
    expect(md).toContain('| `roi` | 10 | 100.0% | +1.20% | +35.00 USDT |');
    expect(md).toContain('không đóng băng metadata thị trường trực tuyến của Binance');
  });
});
