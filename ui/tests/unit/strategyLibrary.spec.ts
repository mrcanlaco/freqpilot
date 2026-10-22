import { describe, it, expect } from 'vitest';
import { latestLibraryRuns, libraryMatches, libraryUpdated } from '@/utils/strategyLibrary';
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
});
