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
    expect(w.text()).toContain('Worker đang chọn hồ sơ này nên chưa thể lưu trữ.');
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
    expect(w.text()).toContain('Cần kết nối worker để xác nhận hồ sơ không đang được chọn trước khi lưu trữ.');
    expect(api.post).not.toHaveBeenCalled();
  });
  it('does not describe a received start response as confirmed execution without native evidence',async()=>{
    const {w,api}=await page();
    api.post.mockResolvedValueOnce({data:{online:true,state:'stopped',action_result:{outcome:'unconfirmed'}}});
    await button(w,'Bật paper hồ sơ này').trigger('click');await flushPromises();
    expect(w.text()).toContain('chưa xác nhận trạng thái đích');
    expect(w.text()).not.toContain('Đã quan sát worker chạy paper');
  });
  it('keeps worker controls available when history alone fails',async()=>{
    const {w,api}=await page('running');
    api.get.mockResolvedValueOnce({data:{online:true,state:'running',open_trades:0,active_profile:'one',profiles:[profile('one','StarterFuturesResearch')],history_error:'journal unavailable'}});
    await button(w,'Tải lại trạng thái').trigger('click');await flushPromises();
    expect(w.text()).toContain('lỗi lịch sử không đồng nghĩa bot đã dừng');
    expect(button(w,'Tạm ngừng vào lệnh').attributes('disabled')).toBeUndefined();
    expect(api.post).not.toHaveBeenCalled();
  });
  it('keeps confirmed pause evidence visible when storing its history failed',async()=>{
    const {w,api}=await page('running');
    api.post.mockResolvedValueOnce({data:{online:true,state:'paused',action_result:{outcome:'observed',logged:false},history_error:'journal unavailable'}});
    await button(w,'Tạm ngừng vào lệnh').trigger('click');await flushPromises();
    expect(w.text()).toContain('Đã quan sát worker tạm ngừng vào lệnh');
    expect(w.text()).toContain('Trạng thái worker và lỗi lưu lịch sử được xử lý riêng: journal unavailable');
    expect(api.post).toHaveBeenCalledTimes(1);
  });
  it('archives only an inactive profile and can restore it without a paper lifecycle action', async () => {
    const { w, api } = await page();
    let archived = false;
    api.get.mockImplementation(async (url: string) => ({
      data: url === '/studio/paper'
        ? { online: true, state: 'stopped', open_trades: 0, active_profile: 'one',
            profiles: [profile('one', 'StarterFuturesResearch'),
              { ...profile('two', 'FAdxSmaStrategy'), archived }] }
        : { events: [] },
    }));
    api.post.mockImplementation(async (url: string) => {
      archived = url.endsWith('/archive');
      return { data: { archived } };
    });
    const archiveButtons = w.findAll('button').filter((b) => b.text() === 'Lưu trữ hồ sơ');
    expect(archiveButtons[0]?.attributes('disabled')).toBeDefined();
    expect(archiveButtons[1]?.attributes('disabled')).toBeUndefined();
    await archiveButtons[1]!.trigger('click');
    await flushPromises();
    expect(api.post).toHaveBeenCalledWith('/studio/paper/profiles/two/archive');
    expect(w.findAll('.profile')).toHaveLength(1);
    await button(w, 'Xem 1 hồ sơ đã lưu trữ').trigger('click');
    expect(w.findAll('.profile')).toHaveLength(2);
    expect(w.findAll('.profile')[1]!.find('button.primary').attributes('disabled')).toBeDefined();
    await button(w, 'Hiện lại hồ sơ').trigger('click');
    await flushPromises();
    expect(api.post).toHaveBeenCalledWith('/studio/paper/profiles/two/restore');
    expect(w.findAll('.profile')).toHaveLength(2);
  });
});
