import { describe, it, expect, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import type { AxiosInstance } from 'axios';
import ParameterPresets from '@/components/strategyDev/ParameterPresets.vue';

const schema = {
  strategy: 'Sample',
  revision: 'source-a',
  parameter_revision: 'none',
  schema_revision: 'schema-a',
  fields: [
    {
      name: 'buy_length',
      space: 'buy',
      param_type: 'IntParameter',
      low: 2,
      high: 40,
      value: 12,
      load: true,
      optimize: true,
    },
    {
      name: 'protection_enabled',
      space: 'protection',
      param_type: 'BooleanParameter',
      opt_range: [true, false],
      value: true,
      load: true,
      optimize: true,
    },
    {
      name: 'buy_locked',
      space: 'buy',
      param_type: 'IntParameter',
      low: 1,
      high: 5,
      value: 2,
      load: false,
      optimize: false,
    },
  ],
};
function setup(revision = 'source-a') {
  const api = {
    get: vi.fn(async (path: string) => ({
      data: path.includes('/parameters/') ? schema : { presets: [] },
    })),
    post: vi.fn(async () => ({
      data: {
        id: 'new-id',
        label: 'Đối chiếu',
        strategy: 'Sample',
        revision: 'source-a',
        values: { buy_length: 17, protection_enabled: false },
      },
    })),
  };
  const wrapper = mount(ParameterPresets, {
    props: { api: api as unknown as AxiosInstance, strategy: 'Sample', revision, busy: false },
    global: { stubs: { CodeViewer: true } },
  });
  return { wrapper, api };
}
describe('Parameter preset input flow', () => {
  it('reads values on request and preserves numeric/boolean types without changing the default selection', async () => {
    const { wrapper, api } = setup();
    await flushPromises();
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(wrapper.emitted('selected')).toBeUndefined();
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Đọc / tải lại tham số')!
      .trigger('click');
    await flushPromises();
    const labels = wrapper.findAll('label');
    await labels
      .find((l) => l.text().startsWith('buy_length'))!
      .find('input')
      .setValue('17');
    await labels
      .find((l) => l.text().startsWith('protection_enabled'))!
      .find('select')
      .setValue('false');
    expect(
      labels
        .find((l) => l.text().startsWith('buy_locked'))!
        .find('input')
        .attributes('disabled'),
    ).toBeDefined();
    await labels
      .find((l) => l.text().startsWith('Tên bộ mới'))!
      .find('input')
      .setValue('Đối chiếu');
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Lưu thành bộ mới và chọn')!
      .trigger('click');
    await flushPromises();
    expect(api.post).toHaveBeenCalledWith(
      '/studio/presets/Sample',
      expect.objectContaining({
        revision: 'source-a',
        schema_revision: 'schema-a',
        values: { buy_length: 17, protection_enabled: false },
      }),
    );
    expect(wrapper.emitted('selected')?.[0]?.[0]).toMatchObject({ id: 'new-id' });
    expect(wrapper.text()).toContain('Chưa chạy backtest hoặc đổi bot paper');
  });
  it('blocks saving controls read from another source revision', async () => {
    const { wrapper, api } = setup('source-b');
    await flushPromises();
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Đọc / tải lại tham số')!
      .trigger('click');
    await flushPromises();
    await wrapper
      .find('input[placeholder="Ví dụ: Cấu hình gốc để đối chiếu"]')
      .setValue('Không lưu mã cũ');
    expect(
      wrapper
        .findAll('button')
        .find((b) => b.text() === 'Lưu thành bộ mới và chọn')!
        .attributes('disabled'),
    ).toBeDefined();
    expect(api.post).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('Mã đã đổi sau khi đọc tham số');
  });
  it('does not select a late save response after leaving the parameter panel', async () => {
    const { wrapper, api } = setup();
    await flushPromises();
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Đọc / tải lại tham số')!
      .trigger('click');
    await flushPromises();
    let complete!: () => void;
    api.post.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          complete = () =>
            resolve({
              data: {
                id: 'new-id',
                label: 'Đối chiếu',
                strategy: 'Sample',
                revision: 'source-a',
                values: { buy_length: 17, protection_enabled: false },
              },
            });
        }),
    );
    await wrapper
      .find('input[placeholder="Ví dụ: Cấu hình gốc để đối chiếu"]')
      .setValue('Đối chiếu');
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Lưu thành bộ mới và chọn')!
      .trigger('click');
    wrapper.unmount();
    complete();
    await flushPromises();
    expect(wrapper.emitted('selected')).toBeUndefined();
    expect(wrapper.emitted('busy')?.at(-1)).toEqual([false]);
  });
});

describe('Native optimization preset provenance', () => {
  it('shows complete special native values and blocks lossy copying into the ordinary parameter form', async () => {
    const { wrapper, api } = setup();
    await wrapper.setProps({
      selected: {
        id: 'optimized',
        label: 'Ứng viên ROI',
        strategy: 'Sample',
        revision: 'source-a',
        schema_revision: 'schema-a',
        parameter_revision: 'none',
        native_sha256: 'a'.repeat(64),
        values: { buy_length: 17, protection_enabled: false },
        created_at: '2026-10-22T00:00:00Z',
        optimization: {
          id: 'optimization-123',
          epoch: 7,
          spaces: ['buy', 'roi'],
          loss: 'SharpeHyperOptLossDaily',
          train_timerange: '20260918-20261010',
          oos_timerange: '20261010-20261022',
        },
        special_params: {
          roi: { '0': 0.03 },
          stoploss: { stoploss: -0.08 },
          trailing: { trailing_stop: true, trailing_stop_positive: 0.01 },
        },
      },
    });
    await flushPromises();
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Đọc / tải lại tham số')!
      .trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('lượt 7');
    expect(wrapper.text()).toContain('20260918-20261010');
    expect(wrapper.text()).toContain('ROI / cắt lỗ / trailing native');
    const viewer = wrapper.findComponent({ name: 'CodeViewer' });
    const displayed = JSON.parse(viewer.props('code'));
    expect(displayed.native_special_parameters).toEqual({
      roi: { '0': 0.03 },
      stoploss: { stoploss: -0.08 },
      trailing: { trailing_stop: true, trailing_stop_positive: 0.01 },
    });
    const copy = wrapper
      .findAll('button')
      .find((b) => b.text() === 'Nạp bộ đang chọn vào biểu mẫu')!;
    expect(copy.attributes('disabled')).toBeDefined();
    await copy.trigger('click');
    expect(wrapper.emitted('selected')).toBeUndefined();
    expect(api.post).not.toHaveBeenCalled();
    wrapper.unmount();
  });
  it('continues to allow fixed parameter presets without special native overrides', async () => {
    const { wrapper } = setup();
    await wrapper.setProps({
      selected: {
        id: 'ordinary',
        label: 'Tham số cố định',
        strategy: 'Sample',
        revision: 'source-a',
        schema_revision: 'schema-a',
        parameter_revision: 'none',
        native_sha256: 'a'.repeat(64),
        values: { buy_length: 17, protection_enabled: false },
        created_at: '2026-10-22T00:00:00Z',
        special_params: {},
      },
    });
    await flushPromises();
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Đọc / tải lại tham số')!
      .trigger('click');
    await flushPromises();
    const copy = wrapper
      .findAll('button')
      .find((b) => b.text() === 'Nạp bộ đang chọn vào biểu mẫu')!;
    expect(copy.attributes('disabled')).toBeUndefined();
    await copy.trigger('click');
    expect(
      (
        wrapper
          .findAll('label')
          .find((l) => l.text().startsWith('buy_length'))!
          .find('input').element as HTMLInputElement
      ).value,
    ).toBe('17');
    wrapper.unmount();
  });
});
