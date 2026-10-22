import { beforeEach, afterEach, describe, it, expect, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import type { AxiosInstance } from 'axios';
import PaperWorkspace from '@/components/strategyDev/PaperWorkspace.vue';
import { mountFq, setupWorld, teardownWorld } from './helpers';
beforeEach(() => setupWorld());
afterEach(teardownWorld);
const profile = (id: string, strategy: string) => ({
  id,
  label: id,
  strategy,
  revision: 'abcd1234',
  run_id: 'run',
  warnings: [],
  valid: true,
  settings: {
    pairs: ['BTC/USDT:USDT'],
    timeframe: '15m',
    wallet: 1000,
    stake: 100,
    max_open_trades: 2,
    fee: 0.0005,
  },
  summary: { total_trades: 144, profit_total_abs: -22.18 },
});
async function page(state = 'stopped', open = 0) {
  const api = {
    get: vi
      .fn()
      .mockResolvedValue({
        data: {
          online: true,
          state,
          open_trades: open,
          active_profile: 'one',
          profiles: [profile('one', 'StarterFuturesResearch'), profile('two', 'FAdxSmaStrategy')],
        },
      }),
    post: vi.fn(),
  };
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  });
  const w = mountFq(PaperWorkspace, {
    props: { api: api as unknown as AxiosInstance, strategy: '', revision: '' },
    global: { plugins: [router] },
  });
  await flushPromises();
  return { w, api };
}
const button = (w: Awaited<ReturnType<typeof page>>['w'], text: string) =>
  w.findAll('button').find((b) => b.text() === text)!;
describe('Research paper workspace', () => {
  it('lists profiles across strategies and leaves a stopped worker stopped while inspecting', async () => {
    const { w, api } = await page();
    expect(w.text()).toContain('FAdxSmaStrategy');
    expect(w.text()).toContain('StarterFuturesResearch');
    expect(button(w, 'Tạm ngừng vào lệnh').attributes('disabled')).toBeDefined();
    expect(button(w, 'Dừng khi đã hết vị thế').attributes('disabled')).toBeDefined();
    expect(button(w, 'Bật paper hồ sơ này').attributes('disabled')).toBeUndefined();
    expect(api.post).not.toHaveBeenCalled();
    expect(w.text()).not.toContain('1 · Chuẩn bị từ bản đã backtest');
    await button(w,'＋ Chuẩn bị từ kết quả backtest').trigger('click');
    expect(w.emitted('openResults')).toHaveLength(1);
  });
  it('offers resume when paused and blocks switching or stopping while a position remains', async () => {
    const { w, api } = await page('paused', 1);
    expect(button(w, 'Tiếp tục paper').attributes('disabled')).toBeUndefined();
    expect(button(w, 'Bật paper hồ sơ này').attributes('disabled')).toBeDefined();
    expect(button(w, 'Dừng khi đã hết vị thế').attributes('disabled')).toBeDefined();
    expect(api.post).not.toHaveBeenCalled();
  });
  it('does not offer to start an already running profile', async () => {
    const { w, api } = await page('running');
    expect(button(w, 'Đang chạy paper').attributes('disabled')).toBeDefined();
    expect(button(w, 'Tạm ngừng vào lệnh').attributes('disabled')).toBeUndefined();
    expect(api.post).not.toHaveBeenCalled();
  });
  it('can explicitly resume exit management when a stopped worker still owns positions', async () => {
    const { w, api } = await page('stopped', 1);
    expect(button(w, 'Tiếp tục quản lý thoát lệnh').attributes('disabled')).toBeUndefined();
    expect(button(w, 'Dừng khi đã hết vị thế').attributes('disabled')).toBeDefined();
    expect(api.post).not.toHaveBeenCalled();
  });
  it('waits for configuration reload to finish before enabling lifecycle controls', async () => {
    const { w, api } = await page('reload_config');
    expect(button(w, 'Bật paper hồ sơ này').attributes('disabled')).toBeDefined();
    expect(button(w, 'Dừng khi đã hết vị thế').attributes('disabled')).toBeDefined();
    expect(button(w, 'Tạm ngừng vào lệnh').attributes('disabled')).toBeDefined();
    expect(api.post).not.toHaveBeenCalled();
  });
  it('disables controls after a failed status refresh instead of trusting old online state', async () => {
    const { w, api } = await page('running');
    api.get.mockRejectedValueOnce(new Error('service unavailable'));
    await button(w, 'Tải lại trạng thái').trigger('click');
    await flushPromises();
    expect(button(w, 'Tạm ngừng vào lệnh').attributes('disabled')).toBeDefined();
    expect(button(w, 'Mở giám sát paper').attributes('disabled')).toBeDefined();
    expect(w.text()).toContain('service unavailable');
    expect(api.post).not.toHaveBeenCalled();
  });
});
