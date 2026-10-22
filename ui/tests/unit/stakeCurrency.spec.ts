import { describe, it, expect } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { commonCurrency, currencyFromPair, requireCommonCurrency } from '@/utils/stakeCurrency';
import { useStakeCurrency } from '@/composables/useStakeCurrency';
import { useFqFleetStore } from '@/datasource/stores/fleet';
import { exitPlan } from '@/components/fq/lib/dialog';
describe('Monetary units', () => {
  it('uses settlement for futures and quote for spot, without guessing a stablecoin', () => {
    expect(currencyFromPair('BTC/USDT:USDT')).toBe('USDT');
    expect(currencyFromPair('BTC/USD:BTC')).toBe('BTC');
    expect(currencyFromPair('ETH/EUR')).toBe('EUR');
    expect(currencyFromPair('ETH')).toBeNull();
  });
  it('does not add different or unknown units as if they were one currency', () => {
    expect(commonCurrency(['usdt', ' USDT '])).toBe('USDT');
    for (const units of [
      ['USDT', 'USDC'],
      ['USDT', ''],
      ['BTC', 'USDT'],
    ]) {
      expect(commonCurrency(units)).toBeNull();
      expect(() => requireCommonCurrency(units)).toThrow();
    }
    expect(() => requireCommonCurrency([])).not.toThrow();
  });
  it('prefers the explicit target bot currency and preserves historical pair fallback', () => {
    setActivePinia(createPinia());
    const fleet = useFqFleetStore();
    fleet.bots['target'] = { bot_key: 'target', identity: { stake_currency: 'BTC' } } as never;
    expect(useStakeCurrency(() => ({ botKey: 'target', pair: 'ETH/USDT:USDT' })).value).toBe('BTC');
    expect(useStakeCurrency(() => ({ botKey: 'removed', pair: 'ETH/USDT:USDT' })).value).toBe(
      'USDT',
    );
    expect(useStakeCurrency(() => ({ botKey: 'removed' })).value).toBe('');
    expect(useStakeCurrency(() => ({ botKeys: ['target', 'removed'] })).value).toBe('');
    expect(useStakeCurrency(() => ({ botKeys: ['target'] })).value).toBe('BTC');
  });
  it('does not reuse the Hyperliquid notional floor on an exchange whose limit is unknown', () => {
    const p = { amount: 1, notional: 100, profitAbs: 3, currentRate: 100 };
    expect(exitPlan(p, 0.5, null).valid).toBe(false);
    expect(exitPlan(p, 1, null).valid).toBe(true);
    expect(exitPlan(p, 0.05).belowMin).toBe(true);
    expect(exitPlan(p, 0.5).valid).toBe(true);
  });
});
