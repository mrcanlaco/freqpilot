import { describe, it, expect } from 'vitest';
import { assessCheck, checkContext, type ResearchCheck } from '@/utils/researchChecks';
const base: ResearchCheck = {
  id: 'check',
  kind: 'lookahead',
  status: 'success',
  strategy: 'S',
  revision: 'code',
  created_at: '2026-10-22',
  settings: {
    timeframe: '1h',
    timerange: '20260918-20261022',
    minimum_trade_amount: 1,
    targeted_trade_amount: 20,
  },
  source_hashes: { 'strategies/S.py': 'code' },
};
describe('Research check interpretation', () => {
  it('does not equate successful execution with evidence when a result or sample is missing', () => {
    for (const result of [
      undefined,
      {},
      { has_bias: false, total_signals: 0 },
      { has_bias: false, total_signals: null },
    ])
      expect(assessCheck({ ...base, result }).tone).toBe('incomplete');
    expect(
      assessCheck({ ...base, status: 'failed', result: { has_bias: false, total_signals: 30 } })
        .tone,
    ).toBe('incomplete');
  });
  it('keeps a small no-bias sample limited and reports how many signals were examined', () => {
    const assessment = assessCheck({ ...base, result: { has_bias: false, total_signals: 2 } });
    expect(assessment.tone).toBe('limited');
    expect(assessment.signals).toBe(2);
    expect(assessment.detail).toContain('2/20');
    expect(
      assessCheck({
        ...base,
        settings: { minimum_trade_amount: 10 },
        result: { has_bias: false, total_signals: 2 },
      }).tone,
    ).toBe('incomplete');
  });
  it('prioritizes actual bias flags and positive indicator/signal evidence', () => {
    for (const result of [
      { has_bias: true, total_signals: 2 },
      { has_bias: false, total_signals: 2, biased_entry_signals: 1 },
      { has_bias: false, total_signals: 2, biased_indicators: ['adx'] },
    ])
      expect(assessCheck({ ...base, result }).tone).toBe('bias');
  });
  it('distinguishes null from zero and omitted recursive cells without inventing missing zeros', () => {
    const assessment = assessCheck({
      ...base,
      kind: 'recursive',
      result: {
        results: {
          adx: { 14: null, 100: -0.0009, 500: 0 },
          sma: { 14: null },
          long: { 14: null, 100: 0 },
        },
      },
    });
    expect(assessment.tone).toBe('attention');
    expect(assessment.missing).toBe(3);
    expect(assessment.changed).toBe(1);
    expect(assessCheck({ ...base, kind: 'recursive', result: { results: {} } }).tone).toBe(
      'limited',
    );
    expect(assessCheck({ ...base, kind: 'recursive', result: {} }).tone).toBe('incomplete');
  });
  it('compares code, parameter file, timeframe and date range separately from the outcome', () => {
    const ctx = {
      strategy: 'S',
      revision: 'code',
      parameterRevision: 'none',
      timeframe: '1h',
      timerange: '20260918-20261022',
    };
    expect(checkContext(base, ctx).state).toBe('same');
    expect(checkContext({ ...base, source_hashes: undefined }, ctx).state).toBe('unknown');
    expect(checkContext(base, { ...ctx, revision: 'new' }).state).toBe('different');
    expect(checkContext(base, { ...ctx, parameterRevision: 'changed' }).state).toBe('different');
    expect(checkContext(base, { ...ctx, timerange: '20260101-' }).state).toBe('different');
    expect(
      checkContext(
        { ...base, preset: { id: 'a', label: 'A', native_sha256: 'preset' } },
        { ...ctx, parameterRevision: 'preset' },
      ).state,
    ).toBe('same');
  });
});
