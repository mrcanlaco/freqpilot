<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue';
import type { AxiosInstance } from 'axios';

type ReplayComparison = {
  status: 'matched' | 'different' | 'unavailable';
  source_id: string;
  source_trades?: number;
  replayed_trades?: number;
  different_trades?: number;
  different_metrics?: string[];
  note?: string;
};
type ReplayRun = {
  id: string;
  strategy: string;
  status: string;
  replay_of?: { id: string; artifact_sha256: string };
  replay_comparison?: ReplayComparison;
};
type Preview = {
  id: string; strategy: string; revision: string; artifact_sha256: string;
  settings: Record<string, unknown>; pairs: string[]; fee: number; input_files: number;
  input_bytes: number; engine: string; note: string; preset?: { label: string };
};
const props = defineProps<{ api: AxiosInstance; run: ReplayRun; busy: boolean; onAccepted: (id: string) => void }>();
const preview = ref<Preview>(), loading = ref(false), error = ref('');
const comparison = computed(() => props.run.replay_comparison);
let generation = 0;
watch(() => props.run.id, () => { generation++; preview.value = undefined; error.value = ''; loading.value = false; });
onUnmounted(() => { generation++; });
function message(e: unknown) {
  const problem = e as { response?: { data?: { detail?: unknown } }; message?: string };
  return String(problem.response?.data?.detail ?? problem.message ?? e);
}
async function review() {
  if (props.busy || loading.value) return;
  const current = generation;
  loading.value = true; error.value = ''; preview.value = undefined;
  try {
    const response = await props.api.get<Preview>('/studio/runs/' + props.run.id + '/replay');
    if (current === generation) preview.value = response.data;
  } catch (e) { if (current === generation) error.value = message(e); }
  finally { if (current === generation) loading.value = false; }
}
async function start() {
  if (props.busy || loading.value || !preview.value || preview.value.id !== props.run.id) return;
  const current = generation;
  loading.value = true; error.value = '';
  try {
    const response = await props.api.post('/studio/runs/' + preview.value.id + '/replay', { artifact_sha256: preview.value.artifact_sha256 });
    if (current === generation) preview.value = undefined;
    // A native job survives changing reports/routes. Notify its owner even if this panel unmounted.
    props.onAccepted(response.data.id);
  } catch (e) { if (current === generation) { preview.value = undefined; error.value = message(e); } }
  finally { if (current === generation) loading.value = false; }
}
</script>

<template>
  <section class="replay" aria-label="Chạy lại backtest từ gói">
    <div v-if="run.replay_of" class="comparison" role="status">
      <b>Bản chạy lại của hồ sơ {{ run.replay_of.id.slice(0, 10) }}</b>
      <template v-if="comparison?.status === 'matched'">
        <p>Khớp toàn bộ {{ comparison.replayed_trades }} lệnh và các chỉ số đối chiếu.</p>
        <small>So sánh chính xác từng trường của lệnh, gồm lệnh con, phí và funding; không làm tròn để ép khớp.</small>
        <p v-if="comparison.replayed_trades === 0">Cả hai lần không có lệnh. Kết quả này chưa kiểm tra được hành vi khớp lệnh.</p>
      </template>
      <template v-else-if="comparison?.status === 'different'">
        <p>Kết quả khác gói gốc: {{ comparison.different_trades }} lệnh khác hoặc thiếu; số lệnh gốc / mới: {{ comparison.source_trades }} / {{ comparison.replayed_trades }}.</p>
        <p v-if="comparison.different_metrics?.length">Chỉ số khác: {{ comparison.different_metrics.join(', ') }}.</p>
        <small>Giữ cả hai báo cáo để điều tra, không sửa hoặc thay kết quả gốc.</small>
      </template>
      <p v-else-if="comparison?.status === 'unavailable'">Đã lưu kết quả mới nhưng chưa đủ gói gốc để đối chiếu. Không xác nhận khớp.</p>
      <p v-else>Đối chiếu sẽ được lưu khi backtest hoàn tất.</p>
      <small>Việc khớp trên dữ liệu này không chứng nhận lợi nhuận hoặc khả năng khớp lệnh thực tế.</small>
    </div>
    <button v-if="!preview" :disabled="busy || loading || run.status !== 'success'" @click="review">
      {{ loading ? 'Đang kiểm tra gói…' : 'Chạy lại từ gói đã lưu' }}
    </button>
    <div v-if="preview" class="review">
      <h4>Xem lại trước khi chạy</h4>
      <p>{{ preview.strategy }} · {{ preview.engine }} · mã {{ preview.revision.slice(0, 10) }}</p>
      <dl>
        <div><dt>Thị trường</dt><dd>{{ preview.pairs.join(', ') }}</dd></div>
        <div><dt>Ngày · khung · chi tiết</dt><dd>{{ preview.settings.timerange }} · {{ preview.settings.timeframe }} · {{ preview.settings.timeframe_detail }}</dd></div>
        <div><dt>Ví · mỗi lệnh · tối đa</dt><dd>{{ preview.settings.dry_run_wallet }} USDT · {{ preview.settings.stake_amount }} USDT · {{ preview.settings.max_open_trades }} lệnh</dd></div>
        <div><dt>Phí mỗi chiều</dt><dd>{{ (preview.fee * 100).toLocaleString('vi-VN', { maximumFractionDigits: 6 }) }}%</dd></div>
        <div><dt>Tham số</dt><dd>{{ preview.preset?.label ?? 'Bản tham số trong gói' }}</dd></div>
        <div><dt>Đầu vào riêng</dt><dd>{{ preview.input_files }} tệp · {{ (preview.input_bytes / 1048576).toFixed(2) }} MB</dd></div>
      </dl>
      <p>{{ preview.note }}</p>
      <small>Tạo hồ sơ mới từ bản lưu, bỏ qua mã và biểu mẫu đang mở. Backtest chưa bắt đầu.</small>
      <div class="actions">
        <button :disabled="busy || loading" @click="preview = undefined">Đóng</button>
        <button class="primary" :disabled="busy || loading" @click="start">{{ loading ? 'Đang gửi…' : 'Chạy bản sao & đối chiếu' }}</button>
      </div>
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>

<style scoped>
.replay{margin-top:18px;padding-top:18px;border-top:1px solid var(--line);font-size:13px}.comparison,.review{border:1px solid var(--line);padding:16px;border-radius:8px;margin-bottom:14px}.comparison p,.review p{line-height:1.6;margin:10px 0;color:var(--fg-2)}small{color:var(--fg-3);line-height:1.6}button{border:1px solid var(--line-2);background:var(--bg-2);color:var(--fg);padding:9px 13px;border-radius:7px;cursor:pointer;font:inherit}button:disabled{opacity:.4;cursor:default}.primary{background:#1b6a5c;color:#f2fff9}.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}h4{font-size:16px;margin:0 0 14px}dl{display:grid;gap:10px}dl>div{display:grid;grid-template-columns:180px minmax(0,1fr);gap:14px}dt{color:var(--fg-3)}dd{margin:0;overflow-wrap:anywhere}[role=alert]{padding:12px;color:#ffb4b4;background:#3c2024;border-radius:6px}@media(max-width:720px){dl>div{grid-template-columns:1fr;gap:4px}}
</style>
