import { describe, it, expect } from 'vitest';
import { formatBacktestProfitFactor } from '@/utils/backtestMetrics';

describe('native backtest profit-factor sentinel', () => {
  it('distinguishes zero gross losses from an all-loss sample', () => {
    expect(formatBacktestProfitFactor({ total_trades: 2, profit_factor: 0,
      trades: [{ profit_abs: 1.542 }, { profit_abs: .784 }] })).toContain('chưa có lệnh lỗ');
    expect(formatBacktestProfitFactor({ total_trades: 2, profit_factor: 0,
      trades: [{ profit_abs: -.711 }, { profit_abs: -2.675 }] })).toBe('0');
  });
  it('does not interpret an empty sample as a zero factor', () => {
    expect(formatBacktestProfitFactor({ total_trades: 0, profit_factor: 0, trades: [] })).toBe('—');
  });
  it('preserves measured profit factor when there are recorded losses', () => {
    expect(formatBacktestProfitFactor({ total_trades: 2, profit_factor: 2.14354,
      trades: [{ profit_abs: 2.14354 }, { profit_abs: -1 }] })).toBe('2.144');
  });
});
