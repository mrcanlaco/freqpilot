<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import type { AxiosInstance } from 'axios';

type Cell = { pair: string; timeframe: string; status: string; issues?: { code?: string; severity?: string; message: string }[]; dataset_sha256?: string; files?: unknown[]; run_id?: string; summary?: Record<string, unknown>; error?: string; artifact_sha256?: string };
type MatrixJob = { id: string; status: string; total_cells: number; completed_cells: number; cells: Cell[]; error?: string };
type Preview = { ready: boolean; cells: Cell[]; estimated_runs: number; estimated_input_bytes: number; note?: string };
const props = defineProps<{ api: AxiosInstance; strategy: string; revision: string; settings: Record<string, unknown>; presetId?: string; busy?: boolean }>();
const pairs = ref<string[]>(['BTC/USDT:USDT', 'ETH/USDT:USDT']);
const timeframes = ref<string[]>(['15m', '1h']);
const preview = ref<Preview>();
const jobs = ref<MatrixJob[]>([]);
const selected = ref<MatrixJob>();
const working = ref(false);
const error = ref('');
const notice = ref('');
let poll: ReturnType<typeof setInterval> | undefined;
const plan = computed(() => ({ strategy: props.strategy, revision: props.revision, preset_id: props.presetId, settings: Object.fromEntries(Object.entries(props.settings).filter(([key]) => key !== 'timeframe')), pairs: pairs.value, timeframes: timeframes.value }));
watch(plan, () => { preview.value = undefined; }, { deep: true });
function message(e: unknown) { const x = e as { response?: { data?: { detail?: unknown } }; message?: string }; return String(x.response?.data?.detail ?? x.message ?? e); }
function show(value: unknown) { return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(2) : '—'; }
function metric(cell: Cell, key: string) { return show(cell.summary?.[key]); }
async function act(fn: () => Promise<void>) { working.value = true; error.value = ''; notice.value = ''; try { await fn(); } catch (e) { error.value = message(e); } finally { working.value = false; } }
async function refresh() {
  try {
    jobs.value = (await props.api.get('/studio/matrix', { params: { strategy: props.strategy } })).data.jobs ?? [];
    if (selected.value) selected.value = (await props.api.get('/studio/matrix/' + selected.value.id)).data;
  } catch (e) { error.value = message(e); }
}
async function inspect() { await act(async () => { preview.value = (await props.api.post('/studio/matrix/preview', plan.value)).data; }); }
async function start() { if (!preview.value?.ready) return; await act(async () => { selected.value = (await props.api.post('/studio/matrix', plan.value)).data; preview.value = undefined; notice.value = 'Đã bắt đầu từng backtest độc lập đúng ma trận đã xem.'; await refresh(); }); }
async function open(id: string) { await act(async () => { selected.value = (await props.api.get('/studio/matrix/' + id)).data; }); }
async function cancel() { if (!selected.value) return; await act(async () => { selected.value = (await props.api.post('/studio/matrix/' + selected.value!.id + '/cancel', {})).data; await refresh(); }); }
onMounted(() => { void refresh(); poll = setInterval(() => { if (selected.value && ['prepared', 'running', 'cancelling'].includes(selected.value.status)) void refresh(); }, 3500); });
onUnmounted(() => { if (poll) clearInterval(poll); });
</script>

<template>
  <div class="matrix">
    <h3>Ma trận BTC/ETH × khung nến</h3>
    <p>Mỗi ô chạy Freqtrade 2026.9 với dữ liệu và ví mô phỏng riêng. Chọn khoảng ngày ở Backtest; bản xem trước kiểm tra dữ liệu từng ô trước khi chạy. Kết quả các ô chỉ để so sánh, không cộng thành lợi nhuận danh mục.</p>
    <div class="choices"><fieldset><legend>Cặp Binance Futures</legend><label v-for="pair in ['BTC/USDT:USDT', 'ETH/USDT:USDT']" :key="pair"><input v-model="pairs" type="checkbox" :value="pair"> {{pair}}</label></fieldset><fieldset><legend>Khung nến · tối đa 3</legend><label v-for="frame in ['5m', '15m', '1h', '4h']" :key="frame"><input v-model="timeframes" type="checkbox" :value="frame" :disabled="!timeframes.includes(frame) && timeframes.length>=3"> {{frame}}</label></fieldset></div>
    <div class="actions"><button :disabled="working || busy || !pairs.length || !timeframes.length || pairs.length*timeframes.length>6" @click="inspect">Kiểm tra ma trận</button><button :disabled="working || busy || !preview?.ready" @click="start">Chạy ma trận đã xem</button><button :disabled="working" @click="refresh">Tải lại</button></div>
    <p v-if="error" class="error" role="alert">{{error}}</p><p v-if="notice" role="status">{{notice}}</p>
    <div v-if="preview" class="box"><h4>Bản xem trước · {{preview.ready ? 'đủ dữ liệu' : 'cần xử lý dữ liệu'}}</h4><p>{{preview.estimated_runs}} backtest, khoảng {{(preview.estimated_input_bytes/1048576).toFixed(1)}} MB đầu vào. {{preview.note}}</p><div class="table-wrap"><table><thead><tr><th>Cặp</th><th>Khung</th><th>Trạng thái</th><th>Vấn đề</th><th>Hash dữ liệu</th></tr></thead><tbody><tr v-for="cell in preview.cells" :key="cell.pair+cell.timeframe"><td>{{cell.pair}}</td><td>{{cell.timeframe}}</td><td>{{cell.status}}</td><td>{{cell.issues?.map(issue=>issue.message).join('; ') || '—'}}</td><td>{{cell.dataset_sha256?.slice(0,12) || '—'}}</td></tr></tbody></table></div></div>
    <div class="box"><h4>Ma trận đã lưu</h4><p v-if="!jobs.length">Chưa có ma trận.</p><div class="actions"><button v-for="job in jobs" :key="job.id" @click="open(job.id)">{{job.id.slice(0,10)}} · {{job.status}} · {{job.completed_cells}}/{{job.total_cells}}</button></div></div>
    <div v-if="selected" class="box"><div class="actions"><h4>Ma trận {{selected.id.slice(0,10)}} · {{selected.status}}</h4><button v-if="['prepared','running'].includes(selected.status)" :disabled="working" @click="cancel">Dừng phần còn lại</button></div><p>{{selected.completed_cells}}/{{selected.total_cells}} ô đã xử lý. {{selected.error}}</p><div class="table-wrap"><table><thead><tr><th>Cặp</th><th>Khung</th><th>Trạng thái</th><th>Lệnh</th><th>Lãi/lỗ USDT</th><th>Chi tiết</th></tr></thead><tbody><tr v-for="cell in selected.cells" :key="cell.pair+cell.timeframe"><td>{{cell.pair}}</td><td>{{cell.timeframe}}</td><td>{{cell.status}}</td><td>{{metric(cell,'total_trades')}}</td><td>{{metric(cell,'profit_total_abs')}}</td><td>{{cell.error || cell.run_id || cell.artifact_sha256?.slice(0,12) || '—'}}</td></tr></tbody></table></div><p class="hint">Mỗi ô có vốn khởi đầu và vị thế riêng. Không cộng phần trăm lợi nhuận hoặc drawdown giữa các ô.</p></div>
  </div>
</template>

<style scoped>
.matrix,.matrix *{text-align:left}.matrix{line-height:1.55}.matrix h3{margin:0 0 8px;font-size:18px;font-weight:650}.matrix h4{margin:0 0 8px;font-size:14.5px;font-weight:600}.matrix p{color:var(--fg-2);margin:8px 0}.choices,.actions{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0}.choices fieldset{border:1px solid var(--line);background:var(--bg);border-radius:9px;padding:12px 16px;min-width:240px}.choices legend{font-size:12px;font-weight:600;color:var(--accent);padding:0 6px}.choices label{display:flex;align-items:center;gap:8px;margin:7px 0;font-size:13px;cursor:pointer}.choices input{width:auto;margin:0;accent-color:var(--accent)}.box{border:1px solid var(--line);background:var(--bg);border-radius:10px;padding:16px;margin:14px 0}.actions{align-items:center}.actions h4{margin-right:auto}button{padding:8px 12px;border:1px solid var(--line-2);border-radius:7px;background:var(--bg-2);color:var(--fg);font:inherit;font-size:12.5px;font-weight:500;cursor:pointer}button:hover:not(:disabled){border-color:var(--accent);color:var(--accent)}button:disabled{opacity:.45}.error{color:#ffb4b4}.hint{padding:10px 12px;background:var(--bg-2);border-left:3px solid var(--accent);border-radius:6px}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:8px;margin-top:10px}table{width:100%;border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums}th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}th{background:var(--bg-2);color:var(--fg-3);font-weight:600}
</style>
