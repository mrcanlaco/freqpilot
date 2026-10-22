import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import type { AxiosInstance } from 'axios';
import OptimizationWorkspace from '@/components/strategyDev/OptimizationWorkspace.vue';
const settings = {
  timerange: '20260918-20261022',
  timeframe: '15m',
  timeframe_detail: '1m',
  dry_run_wallet: 1000,
  stake_amount: '100',
  max_open_trades: 2,
};
const capabilities = {
  schema: { revision: 'source-a', fields: [{ name: 'buy_rsi', space: 'buy', low: 10, high: 40 }] },
  spaces: [
    { id: 'buy', label: 'Vào lệnh', enabled: true },
    { id: 'sell', label: 'Ra lệnh', enabled: false, reason: 'Không có Parameter' },
  ],
  losses: [{ id: 'SharpeHyperOptLossDaily', label: 'Sharpe theo ngày' }],
  sampler: 'Optuna NSGAIII',
  max_epochs: 500,
  max_workers: 2,
};
const job = {
  id: 'opt1',
  strategy: 'Sample',
  revision: 'source-a',
  status: 'success',
  created_at: '2026-10-22T00:00:00Z',
  settings,
  epochs: 50,
  completed_epochs: 50,
  spaces: ['buy'],
  loss: 'SharpeHyperOptLossDaily',
  random_state: 42,
  min_trades: 10,
  validation: 'split',
  train_timerange: '20260918-20261010',
  oos_timerange: '20261010-20261022',
};
const rows = [
  {
    epoch: 1,
    loss: -1,
    eligible: true,
    params_details: { buy: { buy_rsi: 20 }, stoploss: { stoploss: -0.1 } },
    metrics: {
      total_trades: 15,
      profit_total_abs: 12,
      profit_total: 0.012,
      max_drawdown_account: 0.03,
      profit_factor: 1.4,
    },
  },
  {
    epoch: 2,
    loss: 1,
    eligible: false,
    params_details: { buy: { buy_rsi: 25 } },
    metrics: { total_trades: 2 },
  },
];
const wrappers: ReturnType<typeof mount>[] = [];
afterEach(() => {
  wrappers.forEach((w) => w.unmount());
  wrappers.length = 0;
  vi.useRealTimers();
});
function setup(initialJobs: unknown[] = [], extra: Record<string, unknown> = {}) {
  const api = {
    get: vi.fn(async (path: string) => ({
      data: path.includes('capabilities')
        ? capabilities
        : path.endsWith('/epochs')
          ? { epochs: rows, total: 30 }
          : path.endsWith('/opt1')
            ? job
            : { optimizations: initialJobs },
    })),
    post: vi.fn(async (path: string) => ({
      data: path.endsWith('/validate')
        ? { id: 'run-1' }
        : path.endsWith('/preset')
          ? { id: 'preset-1', label: 'Ứng viên lượt 1' }
          : { ...job, status: 'running' },
    })),
  };
  const wrapper = mount(OptimizationWorkspace, {
    props: {
      api: api as unknown as AxiosInstance,
      strategy: 'Sample',
      revision: 'source-a',
      settings,
      busy: false,
      ...extra,
    },
    global: { stubs: { CodeViewer: { props: ['code'], template: '<pre>{{code}}</pre>' } } },
  });
  wrappers.push(wrapper);
  return { api, wrapper };
}
function button(wrapper: ReturnType<typeof mount>, text: string) {
  return wrapper.findAll('button').find((b) => b.text() === text)!;
}
async function prepare(wrapper: ReturnType<typeof mount>) {
  await flushPromises();
  await button(wrapper, 'Đọc phạm vi tối ưu').trigger('click');
  await flushPromises();
  await wrapper.find('input[type="date"]').setValue('2026-10-10');
  await button(wrapper, 'Xem lại cấu hình tối ưu').trigger('click');
  await flushPromises();
}
async function open(wrapper: ReturnType<typeof mount>) {
  await flushPromises();
  await wrapper.find('.history button').trigger('click');
  await flushPromises();
}
describe('Optimization workspace', () => {
  it('marks an archived optimization stale when only the selected preset changes without clearing its results or submitting', async () => {
    const { api, wrapper } = setup([job]);
    await open(wrapper);
    await button(wrapper, 'Xem ứng viên').trigger('click');
    expect(wrapper.text()).not.toContain('Mã, bộ tham số hoặc thiết lập hiện tại khác phiên này');
    await wrapper.setProps({
      preset: {
        id: 'another-preset',
        label: 'Bộ tham số vừa chọn',
        strategy: 'Sample',
        revision: 'source-a',
        schema_revision: 'schema',
        parameter_revision: 'params',
        native_sha256: 'a'.repeat(64),
        values: { buy_rsi: 30 },
        created_at: '2026-10-22T00:00:00Z',
      },
    });
    expect(wrapper.text()).toContain('Mã, bộ tham số hoặc thiết lập hiện tại khác phiên này');
    expect(wrapper.text()).toContain('Ứng viên lượt 1');
    expect(wrapper.find('.candidate pre').text()).toContain('"buy_rsi": 20');
    expect(wrapper.findAll('tbody tr')).toHaveLength(2);
    expect(api.post).not.toHaveBeenCalled();
    await wrapper.setProps({ preset: undefined });
    expect(wrapper.text()).not.toContain('Mã, bộ tham số hoặc thiết lập hiện tại khác phiên này');
  });

  it('blocks start when native optimizer dependencies are unavailable', async () => {
    const { api, wrapper } = setup();
    api.get.mockImplementation(async (path: string) => ({
      data: path.includes('capabilities')
        ? { ...capabilities, available: false, unavailable_reason: 'Thiếu thư viện native: optuna' }
        : { optimizations: [] },
    }));
    await flushPromises();
    await button(wrapper, 'Đọc phạm vi tối ưu').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('Thiếu thư viện native: optuna');
    expect(button(wrapper, 'Xem lại cấu hình tối ưu').attributes('disabled')).toBeDefined();
    expect(api.post).not.toHaveBeenCalled();
  });
  it('rejects an invalid seed before showing a runnable review', async () => {
    const { api, wrapper } = setup();
    await prepare(wrapper);
    await wrapper
      .findAll('label')
      .find((l) => l.text().startsWith('Seed cố định'))!
      .find('input')
      .setValue('0');
    await button(wrapper, 'Xem lại cấu hình tối ưu').trigger('click');
    expect(wrapper.text()).toContain('Số lượt, seed và số lệnh tối thiểu phải là số nguyên hợp lệ');
    expect(button(wrapper, 'Bắt đầu tối ưu')).toBeUndefined();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('loads history read-only and requires review then explicit start with frozen context', async () => {
    const { api, wrapper } = setup();
    await prepare(wrapper);
    expect(api.post).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('Xác nhận phiên tối ưu');
    await button(wrapper, 'Bắt đầu tối ưu').trigger('click');
    await flushPromises();
    expect(api.post).toHaveBeenCalledWith('/studio/optimizations', {
      strategy: 'Sample',
      revision: 'source-a',
      settings,
      epochs: 50,
      spaces: ['buy'],
      loss: 'SharpeHyperOptLossDaily',
      random_state: 42,
      min_trades: 10,
      validation: 'split',
      split_date: '20261010',
    });
    expect(wrapper.emitted('running')?.at(-1)).toEqual([true]);
    expect(wrapper.emitted('selected')).toBeUndefined();
    expect(wrapper.emitted('backtest-started')).toBeUndefined();
  });
  it('invalidates review when external settings or an input changes', async () => {
    const { api, wrapper } = setup();
    await prepare(wrapper);
    await wrapper.setProps({ settings: { ...settings, stake_amount: '200' } });
    expect(button(wrapper, 'Bắt đầu tối ưu')).toBeUndefined();
    expect(api.post).not.toHaveBeenCalled();
  });
  it('blocks incomplete periods and stale capability revision', async () => {
    const { api, wrapper } = setup([], { settings: { ...settings, timerange: '20260918-' } });
    await flushPromises();
    await button(wrapper, 'Đọc phạm vi tối ưu').trigger('click');
    await flushPromises();
    expect(button(wrapper, 'Xem lại cấu hình tối ưu').attributes('disabled')).toBeDefined();
    await wrapper.setProps({ settings, revision: 'source-b' });
    await wrapper.find('input[type="date"]').setValue('2026-10-10');
    await button(wrapper, 'Xem lại cấu hình tối ưu').trigger('click');
    expect(wrapper.text()).toContain('Mã đã đổi');
    expect(api.post).not.toHaveBeenCalled();
  });
  it('paginates the entire result set and allows no automatic candidate choice', async () => {
    const { api, wrapper } = setup([job]);
    await open(wrapper);
    expect(wrapper.text()).toContain('30 lượt có kết quả');
    expect(wrapper.find('.candidate').exists()).toBe(false);
    expect(button(wrapper, 'Không đủ điều kiện').attributes('disabled')).toBeDefined();
    await button(wrapper, 'Trang sau').trigger('click');
    await flushPromises();
    expect(api.get).toHaveBeenLastCalledWith('/studio/optimizations/opt1/epochs', {
      params: { offset: 25, limit: 25, sort: 'loss' },
    });
    expect(wrapper.text()).toContain('26–30 / 30');
  });
  it('saves a fully displayed candidate only on command and emits selection', async () => {
    const { api, wrapper } = setup([job]);
    await open(wrapper);
    await button(wrapper, 'Xem ứng viên').trigger('click');
    expect(wrapper.text()).toContain('"stoploss": -0.1');
    expect(api.post).not.toHaveBeenCalled();
    await button(wrapper, 'Lưu bộ mới và chọn').trigger('click');
    await flushPromises();
    expect(api.post).toHaveBeenCalledWith('/studio/optimizations/opt1/epochs/1/preset', {
      label: 'Ứng viên lượt 1',
    });
    expect(wrapper.emitted('selected')?.[0]?.[0]).toMatchObject({ id: 'preset-1' });
  });
  it('validates explicitly using archived job even when current settings differ', async () => {
    const { api, wrapper } = setup([job], { revision: 'source-new' });
    await open(wrapper);
    expect(wrapper.text()).toContain('Mã, bộ tham số hoặc thiết lập hiện tại khác phiên này');
    await button(wrapper, 'Xem ứng viên').trigger('click');
    await button(wrapper, 'Backtest ngoài mẫu').trigger('click');
    await flushPromises();
    expect(api.post).toHaveBeenCalledWith('/studio/optimizations/opt1/epochs/1/validate', {
      mode: 'oos',
    });
    expect(wrapper.emitted('backtest-started')?.[0]).toEqual(['run-1']);
  });
  it('does not offer OOS for a whole-period job', async () => {
    const single = { ...job, validation: 'single', oos_timerange: undefined };
    const { api, wrapper } = setup([single]);
    api.get.mockImplementation(async (path: string) => ({
      data: path.endsWith('/epochs')
        ? { epochs: rows, total: 2 }
        : path.endsWith('/opt1')
          ? single
          : { optimizations: [single] },
    }));
    await open(wrapper);
    await button(wrapper, 'Xem ứng viên').trigger('click');
    expect(button(wrapper, 'Backtest ngoài mẫu')).toBeUndefined();
  });
  it('cancels only on request and prevents duplicate commands', async () => {
    const running = { ...job, status: 'running' };
    const { api, wrapper } = setup([running]);
    api.get.mockImplementation(async (path: string) => ({
      data: path.endsWith('/epochs')
        ? { epochs: rows, total: 2 }
        : path.endsWith('/opt1')
          ? running
          : { optimizations: [running] },
    }));
    await flushPromises();
    expect(api.post).not.toHaveBeenCalled();
    let complete!: (value: unknown) => void;
    api.post.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          complete = resolve as typeof complete;
        }),
    );
    await button(wrapper, 'Dừng tối ưu').trigger('click');
    await button(wrapper, 'Dừng tối ưu').trigger('click');
    expect(api.post).toHaveBeenCalledTimes(1);
    complete({ data: { ...running, status: 'cancelled' } });
    await flushPromises();
    expect(wrapper.text()).toContain('Đã dừng');
  });
  it('keeps accepted validation ownership after unmount and does not retry or cancel jobs', async () => {
    const accepted = vi.fn();
    const { api, wrapper } = setup([job], { onAccepted: accepted });
    await open(wrapper);
    await button(wrapper, 'Xem ứng viên').trigger('click');
    let complete!: (value: unknown) => void;
    api.post.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          complete = resolve as typeof complete;
        }),
    );
    await button(wrapper, 'Backtest lại tập học').trigger('click');
    wrapper.unmount();
    complete({ data: { id: 'late-run' } });
    await flushPromises();
    expect(accepted).toHaveBeenCalledOnce();
    expect(accepted).toHaveBeenCalledWith('late-run');
    expect(api.post).toHaveBeenCalledTimes(1);
  });
  it('cancels polling on unmount without cancelling optimization', async () => {
    vi.useFakeTimers();
    const running = { ...job, status: 'running' };
    const { api, wrapper } = setup([running]);
    api.get.mockImplementation(async (path: string) => ({
      data: path.endsWith('/epochs')
        ? { epochs: rows, total: 2 }
        : path.endsWith('/opt1')
          ? running
          : { optimizations: [running] },
    }));
    await flushPromises();
    const count = api.get.mock.calls.length;
    wrapper.unmount();
    await vi.advanceTimersByTimeAsync(10000);
    expect(api.get).toHaveBeenCalledTimes(count);
    expect(api.post).not.toHaveBeenCalled();
  });
});
