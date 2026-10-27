<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import type { AxiosInstance } from 'axios';
import type { StrategyPreset } from '@/utils/strategyLibrary';
import CodeViewer from './CodeViewer.vue';

type Space = { id: string; label: string; enabled: boolean; reason?: string };
type Capabilities = {
  schema: { revision?: string; fields: Record<string, unknown>[] };
  spaces: Space[];
  losses: { id: string; label: string }[];
  sampler: string;
  max_epochs: number;
  max_workers: number;
  available?: boolean;
  unavailable_reason?: string | null;
};
type Job = {
  id: string;
  strategy?: string;
  revision?: string;
  preset?: StrategyPreset | null;
  status: string;
  created_at: string;
  settings: Record<string, unknown>;
  epochs: number;
  completed_epochs: number;
  spaces: string[];
  loss: string;
  random_state: number;
  min_trades: number;
  validation: string;
  train_timerange: string;
  oos_timerange?: string;
  error?: string;
};
type Epoch = {
  epoch: number;
  loss: number | null;
  eligible: boolean;
  params_details: Record<string, unknown>;
  metrics: {
    total_trades: number;
    profit_total_abs?: number;
    profit_total?: number;
    max_drawdown_account?: number;
    profit_factor?: number;
  };
};
const props = defineProps<{
  api: AxiosInstance;
  strategy: string;
  revision: string;
  settings: Record<string, unknown>;
  preset?: StrategyPreset;
  busy: boolean;
  onAccepted?: (id: string) => void | Promise<void>;
}>();
const emit = defineEmits<{
  busy: [value: boolean];
  running: [value: boolean];
  selected: [preset: StrategyPreset];
  'backtest-started': [id: string];
}>();
const capabilities = ref<Capabilities>();
const history = ref<Job[]>([]),
  job = ref<Job>(),
  rows = ref<Epoch[]>([]),
  selected = ref<Epoch>();
const epochs = ref(50),
  seed = ref(42),
  minTrades = ref(10),
  spaces = ref<string[]>([]),
  loss = ref('SharpeHyperOptLossDaily');
const validation = ref('split'),
  splitDate = ref(''),
  sort = ref('loss'),
  offset = ref(0),
  total = ref(0),
  label = ref('');
const requesting = ref(false),
  reading = ref(false),
  message = ref(''),
  bad = ref(false);
const review = ref<Record<string, unknown>>();
let mounted = true,
  generation = 0,
  timer: ReturnType<typeof setTimeout> | undefined;
const active = (item?: Job) =>
  !!item && ['prepared', 'pending', 'running', 'cancelling'].includes(item.status);
const hasActive = computed(() => history.value.some(active) || active(job.value));
const locked = computed(() => props.busy || requesting.value);
const fields = computed(() => capabilities.value?.schema?.fields ?? []);
const timerange = computed(() => String(props.settings.timerange ?? ''));
const closed = computed(
  () =>
    /^\d{8}-\d{8}$/.test(timerange.value) &&
    timerange.value.split('-')[0]! < timerange.value.split('-')[1]!,
);
const suggestedSplit = computed(() => {
  if (!closed.value) return '';
  const [from, to] = timerange.value.split('-');
  if (!from || !to) return '';
  const startMs = Date.UTC(
    Number(from.slice(0, 4)),
    Number(from.slice(4, 6)) - 1,
    Number(from.slice(6, 8)),
  );
  const endMs = Date.UTC(Number(to.slice(0, 4)), Number(to.slice(4, 6)) - 1, Number(to.slice(6, 8)));
  const diffDays = Math.round((endMs - startMs) / 86_400_000);
  if (diffDays < 2) return '';
  const trainDays = Math.max(1, Math.min(diffDays - 1, Math.round(diffDays * 0.7)));
  return new Date(startMs + trainDays * 86_400_000).toISOString().slice(0, 10);
});
const stale = computed(
  () =>
    !!job.value &&
    ((job.value.revision && job.value.revision !== props.revision) ||
      JSON.stringify(job.value.settings) !== JSON.stringify(props.settings) ||
      (job.value.preset?.id ?? '') !== (props.preset?.id ?? '')),
);
const formSignature = computed(() =>
  JSON.stringify([
    props.strategy,
    props.revision,
    props.settings,
    props.preset?.id,
    epochs.value,
    seed.value,
    minTrades.value,
    spaces.value,
    loss.value,
    validation.value,
    splitDate.value,
  ]),
);
watch(formSignature, () => {
  review.value = undefined;
});
watch(hasActive, (value) => emit('running', value), { immediate: true });
const statusLabel: Record<string, string> = {
  running: 'Đang tối ưu',
  prepared: 'Đã chuẩn bị',
  pending: 'Đang chờ',
  cancelling: 'Đang dừng',
  success: 'Hoàn tất',
  completed: 'Hoàn tất',
  failed: 'Thất bại',
  cancelled: 'Đã dừng',
  interrupted: 'Bị gián đoạn',
};
function failure(error: unknown) {
  const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
  return typeof detail === 'string'
    ? detail
    : 'Không hoàn tất yêu cầu. Kiểm tra kết nối rồi thử lại thủ công.';
}
function report(error: unknown) {
  if (mounted) {
    message.value = failure(error);
    bad.value = true;
  }
}
async function command(action: () => Promise<void>) {
  if (locked.value) return;
  requesting.value = true;
  emit('busy', true);
  bad.value = false;
  try {
    await action();
  } catch (error) {
    report(error);
  } finally {
    requesting.value = false;
    emit('busy', false);
  }
}
function upsert(item: Job) {
  history.value = [item, ...history.value.filter((x) => x.id !== item.id)];
}
function schedule() {
  if (timer) clearTimeout(timer);
  if (mounted && active(job.value)) timer = setTimeout(() => void refresh(), 1500);
}
async function loadEpochs() {
  if (!job.value) return;
  const current = ++generation,
    id = job.value.id;
  const { data } = await props.api.get(`/studio/optimizations/${id}/epochs`, {
    params: { offset: offset.value, limit: 25, sort: sort.value },
  });
  if (!mounted || current !== generation || job.value?.id !== id) return;
  rows.value = data.epochs;
  total.value = data.total;
}
async function refresh() {
  if (!mounted || !job.value) return;
  if (reading.value) {
    schedule();
    return;
  }
  const id = job.value.id;
  reading.value = true;
  try {
    const { data } = await props.api.get(`/studio/optimizations/${id}`);
    if (!mounted || job.value?.id !== id) return;
    job.value = data;
    upsert(data);
    await loadEpochs();
  } catch (error) {
    report(error);
    return;
  } finally {
    reading.value = false;
  }
  schedule();
}
async function open(item: Job) {
  if (requesting.value || reading.value) return;
  if (timer) clearTimeout(timer);
  generation++;
  job.value = item;
  selected.value = undefined;
  offset.value = 0;
  rows.value = [];
  total.value = 0;
  review.value = undefined;
  await refresh();
}
async function inspect() {
  await command(async () => {
    const { data } = await props.api.get(
      `/studio/optimization-capabilities/${encodeURIComponent(props.strategy)}`,
    );
    if (!mounted) return;
    capabilities.value = data;
    spaces.value = data.spaces
      .filter(
        (space: Space) => space.enabled && ['buy', 'sell', 'enter', 'exit'].includes(space.id),
      )
      .map((space: Space) => space.id);
    if (!data.losses.some((item: { id: string }) => item.id === loss.value))
      loss.value = data.losses[0]?.id ?? '';
    message.value = 'Đã đọc phạm vi từ chiến lược. Chọn thiết lập rồi xem lại trước khi chạy.';
  });
}
function prepare() {
  if (
    locked.value ||
    hasActive.value ||
    !capabilities.value ||
    capabilities.value.available === false ||
    !closed.value ||
    !spaces.value.length ||
    !loss.value
  )
    return;
  if (capabilities.value.schema.revision && capabilities.value.schema.revision !== props.revision) {
    message.value = 'Mã đã đổi. Đọc lại phạm vi tối ưu trước khi chạy.';
    bad.value = true;
    return;
  }
  if (
    !Number.isInteger(epochs.value) ||
    epochs.value < 1 ||
    epochs.value > capabilities.value.max_epochs ||
    !Number.isInteger(seed.value) ||
    seed.value < 1 ||
    seed.value > 2147483647 ||
    !Number.isInteger(minTrades.value) ||
    minTrades.value < 1 ||
    minTrades.value > 10000
  ) {
    message.value = 'Số lượt, seed và số lệnh tối thiểu phải là số nguyên hợp lệ.';
    bad.value = true;
    return;
  }
  const date = splitDate.value.replaceAll('-', '');
  const [from, to] = timerange.value.split('-');
  if (validation.value === 'split' && (!/^\d{8}$/.test(date) || date <= from! || date >= to!)) {
    message.value = 'Chọn ngày chia nằm giữa ngày bắt đầu và kết thúc.';
    bad.value = true;
    return;
  }
  review.value = JSON.parse(
    JSON.stringify({
      strategy: props.strategy,
      revision: props.revision,
      ...(props.preset ? { preset_id: props.preset.id } : {}),
      settings: props.settings,
      epochs: epochs.value,
      spaces: spaces.value,
      loss: loss.value,
      random_state: seed.value,
      min_trades: minTrades.value,
      validation: validation.value,
      ...(validation.value === 'split' ? { split_date: date } : {}),
    }),
  );
  bad.value = false;
}
async function start() {
  if (!review.value || hasActive.value) return;
  const payload = review.value;
  await command(async () => {
    const { data } = await props.api.post('/studio/optimizations', payload);
    if (!mounted) return;
    job.value = data;
    upsert(data);
    review.value = undefined;
    selected.value = undefined;
    offset.value = 0;
    message.value = 'Đã nhận yêu cầu tối ưu. Không tự chọn tham số hoặc bật paper.';
    schedule();
  });
}
async function cancel() {
  if (!job.value || !active(job.value)) return;
  const id = job.value.id;
  await command(async () => {
    const { data } = await props.api.post(`/studio/optimizations/${id}/cancel`);
    if (mounted && job.value?.id === id) {
      job.value = data;
      upsert(data);
      message.value = 'Đã gửi yêu cầu dừng; chờ trạng thái xác nhận.';
      schedule();
    }
  });
}
async function page(delta: number) {
  if (reading.value || requesting.value) return;
  const next = offset.value + delta;
  if (next < 0 || next >= total.value) return;
  offset.value = next;
  selected.value = undefined;
  reading.value = true;
  try {
    await loadEpochs();
  } catch (error) {
    report(error);
  } finally {
    reading.value = false;
  }
}
async function changeSort() {
  if (reading.value || requesting.value) return;
  offset.value = 0;
  selected.value = undefined;
  reading.value = true;
  try {
    await loadEpochs();
  } catch (error) {
    report(error);
  } finally {
    reading.value = false;
  }
}
async function savePreset() {
  if (!job.value || !selected.value?.eligible || !label.value.trim() || active(job.value)) return;
  const id = job.value.id,
    epoch = selected.value.epoch;
  await command(async () => {
    const { data } = await props.api.post(`/studio/optimizations/${id}/epochs/${epoch}/preset`, {
      label: label.value.trim(),
    });
    if (mounted) {
      emit('selected', data);
      message.value = 'Đã lưu và chọn bộ tham số mới. Chưa chạy backtest hoặc paper.';
    }
  });
}
async function validate(mode: 'train' | 'oos') {
  if (
    !job.value ||
    !selected.value?.eligible ||
    active(job.value) ||
    (mode === 'oos' && !job.value.oos_timerange)
  )
    return;
  const id = job.value.id,
    epoch = selected.value.epoch,
    accepted = props.onAccepted;
  await command(async () => {
    const { data } = await props.api.post(`/studio/optimizations/${id}/epochs/${epoch}/validate`, {
      mode,
    });
    if (accepted) await accepted(data.id);
    else if (mounted) emit('backtest-started', data.id);
    if (mounted) message.value = 'Đã nhận backtest kiểm định với đầu vào của phiên tối ưu đã lưu.';
  });
}
function number(value?: number | null, percent = false) {
  return value == null || !Number.isFinite(value)
    ? '—'
    : `${(percent ? value * 100 : value).toLocaleString('vi-VN', { maximumFractionDigits: 4 })}${percent ? '%' : ''}`;
}
onMounted(async () => {
  try {
    const { data } = await props.api.get('/studio/optimizations', {
      params: { strategy: props.strategy },
    });
    if (mounted) {
      history.value = data.optimizations ?? data.jobs ?? [];
      const running = history.value.find(active);
      if (running) await open(running);
    }
  } catch (error) {
    report(error);
  }
});
onUnmounted(() => {
  emit('busy', false);
  mounted = false;
  generation++;
  if (timer) clearTimeout(timer);
});
</script>

<template>
  <section class="optimization" aria-label="Tối ưu tham số">
    <div class="row">
      <div>
        <h3>Tối ưu tham số</h3>
        <p>
          Tìm ứng viên bằng Hyperopt Freqtrade, rồi backtest kiểm định trước khi quyết định sử dụng.
        </p>
      </div>
      <button :disabled="locked || hasActive" @click="inspect">Đọc phạm vi tối ưu</button>
    </div>
    <div class="context">
      {{ strategy }} · mã {{ revision.slice(0, 10) }} · {{ settings.timeframe }} / chi tiết
      {{ settings.timeframe_detail }} · {{ timerange }} · vốn {{ settings.dry_run_wallet }} USDT ·
      mỗi lệnh {{ settings.stake_amount }} · tối đa {{ settings.max_open_trades }} lệnh<template
        v-if="preset"
      >
        · bộ {{ preset.label }}</template
      >
    </div>
    <p v-if="!closed" class="notice bad">
      Chọn đủ ngày bắt đầu và ngày kết thúc ở biểu mẫu Backtest trước khi tối ưu.
    </p>
    <p v-if="message" role="status" class="notice" :class="{ bad }">{{ message }}</p>
    <template v-if="capabilities">
      <p v-if="capabilities.available === false" class="notice bad">
        {{ capabilities.unavailable_reason ?? 'Dịch vụ chưa sẵn sàng chạy Hyperopt.' }}
      </p>
      <p>
        {{ capabilities.sampler }} · tối đa {{ capabilities.max_epochs }} lượt,
        {{ capabilities.max_workers }} tiến trình. Số lượt là giới hạn yêu cầu, không đảm bảo tìm
        được kết quả tốt.
      </p>
      <fieldset :disabled="locked || hasActive">
        <legend>Phạm vi tìm kiếm</legend>
        <label v-for="space in capabilities.spaces" :key="space.id" class="choice"
          ><input v-model="spaces" type="checkbox" :value="space.id" :disabled="!space.enabled" />{{
            space.label
          }}<small v-if="space.reason"> · {{ space.reason }}</small></label
        >
      </fieldset>
      <details>
        <summary>Khai báo tham số gốc ({{ fields.length }})</summary>
        <CodeViewer :code="JSON.stringify(fields, null, 2)" language="json" />
      </details>
      <div class="grid">
        <label
          >Số lượt thử<input
            v-model.number="epochs"
            type="number"
            min="1"
            :max="capabilities.max_epochs"
            :disabled="locked || hasActive"
        /></label>
        <label
          >Seed cố định<input
            v-model.number="seed"
            type="number"
            min="1"
            max="2147483647"
            :disabled="locked || hasActive"
        /></label>
        <label
          >Số lệnh tối thiểu<input
            v-model.number="minTrades"
            type="number"
            min="1"
            max="10000"
            :disabled="locked || hasActive"
        /></label>
        <label
          >Tiêu chí tìm kiếm<select v-model="loss" :disabled="locked || hasActive">
            <option v-for="item in capabilities.losses" :key="item.id" :value="item.id">
              {{ item.label }}
            </option>
          </select></label
        >
        <label
          >Kiểm định<select v-model="validation" :disabled="locked || hasActive">
            <option value="split">Chia tập học / ngoài mẫu</option>
            <option value="single">Toàn kỳ · chưa có ngoài mẫu</option>
          </select></label
        >
        <label v-if="validation === 'split'"
          >Ngày bắt đầu ngoài mẫu<input
            v-model="splitDate"
            type="date"
            :disabled="locked || hasActive"
        /></label>
      </div>
      <div class="hint-row">
        <p class="hint">
          Điểm tối ưu được tính trên tập học. Tập ngoài mẫu được giữ lại để kiểm tra riêng; một lần
          chia không chứng minh chiến lược bền vững. Ưu tiên số lệnh, drawdown và kết quả ngoài mẫu
          cùng với lợi nhuận.
        </p>
        <button
          v-if="validation === 'split' && closed && suggestedSplit && splitDate !== suggestedSplit"
          type="button"
          class="split-btn"
          :disabled="locked || hasActive"
          @click="splitDate = suggestedSplit"
        >
          Gợi ý tách 70/30 ({{ suggestedSplit }})
        </button>
      </div>
      <button
        :disabled="
          locked || hasActive || !closed || !spaces.length || capabilities.available === false
        "
        @click="prepare"
      >
        Xem lại cấu hình tối ưu
      </button>
      <div v-if="review" class="review">
        <h4>Xác nhận phiên tối ưu</h4>
        <p>
          {{ review.epochs }} lượt · {{ (review.spaces as string[]).join(', ') }} ·
          {{ review.loss }} · seed {{ review.random_state }} · tối thiểu
          {{ review.min_trades }} lệnh
        </p>
        <p>
          {{
            review.validation === 'split'
              ? 'Chia tập tại ' + review.split_date
              : 'Toàn kỳ, chưa có tập ngoài mẫu'
          }}
          · {{ timerange }}
        </p>
        <p>
          Mã, tham số và dữ liệu được sao chép riêng cho phiên chạy. Không ghi đè chiến lược đang
          dùng.
        </p>
        <button class="primary" :disabled="locked || hasActive" @click="start">
          Bắt đầu tối ưu</button
        ><button :disabled="locked" @click="review = undefined">Quay lại chỉnh</button>
      </div>
    </template>
    <div class="history">
      <h4>Lịch sử tối ưu</h4>
      <p v-if="!history.length">Chưa có phiên tối ưu của chiến lược này.</p>
      <button
        v-for="item in history"
        :key="item.id"
        :disabled="requesting || reading"
        :class="{ chosen: job?.id === item.id }"
        @click="open(item)"
      >
        {{ new Date(item.created_at).toLocaleString('vi-VN') }} ·
        {{ statusLabel[item.status] ?? item.status }} · {{ item.completed_epochs }}/{{
          item.epochs
        }}
        lượt
      </button>
    </div>
    <article v-if="job" class="job">
      <div class="row">
        <h4>{{ statusLabel[job.status] ?? job.status }} · {{ job.id.slice(0, 10) }}</h4>
        <button :disabled="requesting || reading" @click="refresh">Tải lại phiên</button
        ><button v-if="active(job)" :disabled="locked" @click="cancel">Dừng tối ưu</button>
      </div>
      <progress v-if="active(job)" :value="job.completed_epochs" :max="job.epochs" />
      <p>
        {{ job.completed_epochs }}/{{ job.epochs }} lượt · tập học {{ job.train_timerange
        }}<template v-if="job.oos_timerange"> · ngoài mẫu {{ job.oos_timerange }}</template> ·
        {{ job.loss }} · seed {{ job.random_state }}
      </p>
      <p v-if="job.error" class="notice bad">{{ job.error }}</p>
      <p v-if="stale" class="notice">
        Mã, bộ tham số hoặc thiết lập hiện tại khác phiên này. Xem và kiểm định ứng viên vẫn dùng
        đầu vào của phiên đã lưu.
      </p>
      <div class="row">
        <label
          >Sắp xếp<select v-model="sort" :disabled="reading || requesting" @change="changeSort">
            <option value="loss">Điểm tối ưu tăng dần</option>
            <option value="epoch">Thứ tự lượt thử</option>
          </select></label
        ><span>{{ total }} lượt có kết quả · điểm thấp hơn được xếp trước</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Lượt</th>
              <th>Điểm</th>
              <th>Lệnh</th>
              <th>Lãi/lỗ USDT</th>
              <th>Lãi/lỗ %</th>
              <th>Drawdown</th>
              <th>Profit factor</th>
              <th>Ứng viên</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in rows"
              :key="item.epoch"
              :class="{ chosen: selected?.epoch === item.epoch }"
            >
              <td>{{ item.epoch }}</td>
              <td>{{ number(item.loss) }}</td>
              <td>{{ item.metrics.total_trades }}</td>
              <td>{{ number(item.metrics.profit_total_abs) }}</td>
              <td>{{ number(item.metrics.profit_total, true) }}</td>
              <td>{{ number(item.metrics.max_drawdown_account, true) }}</td>
              <td>{{ number(item.metrics.profit_factor) }}</td>
              <td>
                <button
                  :disabled="requesting || !item.eligible"
                  @click="
                    selected = item;
                    label = 'Ứng viên lượt ' + item.epoch;
                  "
                >
                  {{ item.eligible ? 'Xem ứng viên' : 'Không đủ điều kiện' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="row">
        <button :disabled="offset === 0 || reading || requesting" @click="page(-25)">
          Trang trước</button
        ><span>{{ total ? offset + 1 : 0 }}–{{ Math.min(offset + 25, total) }} / {{ total }}</span
        ><button :disabled="offset + 25 >= total || reading || requesting" @click="page(25)">
          Trang sau
        </button>
      </div>
      <div v-if="selected" class="candidate">
        <h4>Ứng viên lượt {{ selected.epoch }}</h4>
        <CodeViewer :code="JSON.stringify(selected.params_details, null, 2)" language="json" />
        <p>
          Lưu nguyên tham số ứng viên, gồm ROI/cắt lỗ/trailing nếu có. Việc lưu chỉ chọn bộ mới
          trong giao diện.
        </p>
        <label>Tên bộ mới<input v-model="label" maxlength="70" :disabled="locked" /></label>
        <div class="row">
          <button
            :disabled="locked || active(job) || !label.trim() || !selected.eligible"
            @click="savePreset"
          >
            Lưu bộ mới và chọn</button
          ><button
            :disabled="locked || active(job) || !selected.eligible"
            @click="validate('train')"
          >
            Backtest lại tập học</button
          ><button
            v-if="job.oos_timerange"
            :disabled="locked || active(job) || !selected.eligible"
            @click="validate('oos')"
          >
            Backtest ngoài mẫu
          </button>
        </div>
      </div>
    </article>
  </section>
</template>

<style scoped>
.optimization,
.optimization * {
  text-align: left;
}
.optimization {
  min-width: 0;
  display: grid;
  gap: 1rem;
}
.hint-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.split-btn {
  font-size: 12px;
  white-space: nowrap;
  border-color: var(--accent);
  color: var(--accent);
}
.row {
  display: flex;
  gap: 0.7rem;
  align-items: center;
  flex-wrap: wrap;
  justify-content: space-between;
}
.row h3,
.row h4 {
  margin: 0;
}
p {
  color: var(--fg-2);
  margin: 0.4rem 0;
  line-height: 1.6;
}
.context,
.notice,
.review,
.candidate {
  padding: 1rem;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--bg-2);
}
.notice.bad {
  color: var(--danger, #e78585);
}
.hint,
small {
  font-size: 0.85rem;
  color: var(--fg-2);
}
.grid {
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 1rem;
}
label {
  min-width: 0;
  display: grid;
  gap: 0.45rem;
}
label.choice {
  display: inline-flex;
  align-items: center;
  margin: 0.5rem 1rem 0.5rem 0;
}
input,
select,
button {
  font: inherit;
  color: inherit;
  background: var(--bg-1);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.55rem 0.7rem;
}
button {
  cursor: pointer;
}
button:disabled {
  opacity: 0.45;
  cursor: default;
}
.primary,
.chosen {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, var(--bg-1));
}
input:not([type='checkbox']),
select {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
}
.optimization > *,
.grid > *,
.job > *,
.row > * {
  min-width: 0;
}
input[type='checkbox'] {
  width: 1rem;
  height: 1rem;
  padding: 0;
  accent-color: var(--accent);
}
fieldset {
  border: 1px solid var(--line);
  border-radius: 10px;
}
.history {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}
.history h4,
.history p {
  flex-basis: 100%;
  margin: 0.25rem 0;
}
.job {
  display: grid;
  gap: 0.8rem;
  border-top: 1px solid var(--line);
  padding-top: 1rem;
}
.table-wrap {
  min-width: 0;
  max-width: 100%;
  overflow: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
  white-space: nowrap;
}
th,
td {
  padding: 0.6rem;
  text-align: left;
  border-bottom: 1px solid var(--line);
}
th {
  font-size: 0.8rem;
  color: var(--fg-2);
}
progress {
  width: 100%;
}
.candidate {
  display: grid;
  gap: 0.8rem;
}
details summary {
  cursor: pointer;
  color: var(--fg-2);
}
</style>
