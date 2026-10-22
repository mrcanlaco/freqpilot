import { describe, it, expect } from 'vitest';
import {
  executionState,
  executionSnapshot,
  executionBlock,
  type ExecutionRow,
} from '@/datasource/execution';
import { newRuntime, buildBotRow, type RowContext } from '@/datasource/direct/model';
import type { BotState } from '@/types';
const NOW = 1800000000000;
function native(state = 'stopped', paper = false) {
  const rt = newRuntime(
    'test',
    'local:' + (paper ? 8095 : 8090),
    'test',
    null,
    paper ? 8095 : 8090,
    0,
  );
  rt.reach = 'online';
  rt.lastContactMs = NOW;
  rt.config = {
    data: {
      state,
      dry_run: true,
      stake_currency: 'USDT',
      strategy: paper ? 'FPPaper_abc' : 'StarterFutures',
    } as BotState,
    atMs: NOW,
  };
  const ctx: RowContext = {
    nowMs: NOW,
    walletId: null,
    walletShared: false,
    alerts: { count: 0, max_severity: null },
    cadences: { statusMs: 30000, slowMs: 180000, digestMs: 60000, overviewMs: 60000 },
    statusCadenceMs: 5000,
    slowCadenceMs: 20000,
  };
  return { rt, ctx, row: () => buildBotRow(rt, ctx) as ExecutionRow };
}
describe('Native execution is separate from connectivity', () => {
  it('keeps a stopped trader connected and represents PAUSED without calling it stopped', () => {
    for (const state of ['running', 'paused', 'stopped', 'reload_config']) {
      const { row } = native(state);
      expect(row().state.status).toBe('online');
      expect(executionState(row(), NOW)).toBe(state);
    }
    expect(executionState(native('unrecognized').row(), NOW)).toBe('unknown');
  });
  it('expires the configuration observation even while positions/contact remain fresh', () => {
    const { rt, ctx, row } = native('running');
    ctx.nowMs = NOW + 61000;
    rt.lastContactMs = ctx.nowMs;
    rt.status = { data: [], atMs: ctx.nowMs };
    expect(row().freshness.state?.stale).toBe(false);
    expect(executionState(row(), ctx.nowMs)).toBe('stale');
    const disconnected = native('running').row();
    disconnected.state.status = 'offline';
    expect(executionState(disconnected, NOW)).toBe('stale');
  });
  it('does not display a requested transition as a confirmed native state', () => {
    const { rt, row } = native('running');
    rt.executionInvalidated = true;
    expect(executionSnapshot(row())?.state).toBe('running');
    expect(executionState(row(), NOW)).toBe('stale');
  });
  it('routes managed paper lifecycle to verified profiles and retains paused exits', () => {
    const row = native('paused', true).row();
    for (const kind of ['start', 'stop', 'stopbuy', 'reload_config'] as const)
      expect(executionBlock(row, { kind }, NOW)).toBe('managedPaper');
    expect(executionBlock(row, { kind: 'forceexit', tradeId: 'all' }, NOW)).toBeNull();
    expect(
      executionBlock(row, { kind: 'forceentry', pair: 'BTC/USDT:USDT', side: 'long' }, NOW),
    ).toBe('executionState');
  });
  it('applies state-specific lifecycle rules and does not treat gateway Online as RUNNING', () => {
    const row = native('stopped').row();
    expect(executionBlock(row, { kind: 'start' }, NOW)).toBeNull();
    expect(executionBlock(row, { kind: 'stopbuy' }, NOW)).toBe('executionState');
    const running = native('running').row();
    running.state.open_trades = 1;
    expect(executionBlock(running, { kind: 'stop' }, NOW)).toBe('openPositions');
    delete row.execution;
    expect(executionState(row, NOW)).toBe('unknown');
    expect(executionBlock(row, { kind: 'start' }, NOW)).toBeNull();
  });
});
