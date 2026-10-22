import type { BotRow } from '@/gateway/types.gen';
import type { BotAction } from './types';

/** UI-owned Direct extension; never interpret the gateway's connection status as execution. */
export type ExecutionSnapshot = {
  state: 'running' | 'paused' | 'stopped' | 'reload_config' | 'unknown';
  as_of_ms: number;
  expires_ms: number;
  managed_paper: boolean;
};
export type ExecutionRow = BotRow & { execution?: ExecutionSnapshot };
export function executionSnapshot(bot: BotRow | null | undefined) {
  return (bot as ExecutionRow | null | undefined)?.execution;
}
export function executionState(bot: BotRow | null | undefined, nowMs: number) {
  const snapshot = executionSnapshot(bot);
  if (!snapshot) return 'unknown';
  return bot?.state.status !== 'online' || nowMs > snapshot.expires_ms ? 'stale' : snapshot.state;
}
export function isManagedPaper(bot: BotRow | null | undefined) {
  return executionSnapshot(bot)?.managed_paper === true;
}
export function isLifecycleAction(action: BotAction) {
  return ['start', 'stop', 'stopbuy', 'reload_config'].includes(action.kind);
}
export type ExecutionBlock =
  | 'managedPaper'
  | 'executionUnknown'
  | 'executionState'
  | 'openPositions';
export function executionBlock(
  bot: BotRow,
  action: BotAction,
  nowMs: number,
): ExecutionBlock | null {
  if (isManagedPaper(bot) && isLifecycleAction(action)) return 'managedPaper';
  // Gateway/legacy rows have no native lifecycle evidence. Keep their existing policy.
  if (!executionSnapshot(bot)) return null;
  if (!isLifecycleAction(action) && !['forceentry', 'forceexit'].includes(action.kind)) return null;
  const state = executionState(bot, nowMs);
  if (state === 'unknown' || state === 'stale' || state === 'reload_config')
    return 'executionUnknown';
  if (action.kind === 'start' && !['paused', 'stopped'].includes(state)) return 'executionState';
  if (['stopbuy', 'forceentry'].includes(action.kind) && state !== 'running')
    return 'executionState';
  if (action.kind === 'forceexit' && !['running', 'paused'].includes(state))
    return 'executionState';
  if (action.kind === 'stop') {
    if (state === 'stopped') return 'executionState';
    if (bot.state.open_trades > 0) return 'openPositions';
  }
  return null;
}
