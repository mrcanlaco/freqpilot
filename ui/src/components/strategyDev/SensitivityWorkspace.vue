<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import type { AxiosInstance } from 'axios';

type Field = { name: string; param_type: string; load: boolean; low: number; high: number; value: number };
type Cell = { index: number; parameters: Record<string, number>; fee: number; status: string; result: Record<string, unknown> | null; error?: string };
type Sensitivity = { id: string; status: string; completed_cells: number; cells: Cell[]; axes: { name: string; base: number; values: number[] }[]; estimated_backtests: number; current_cell?: number; error?: string };
const props = defineProps<{ api: AxiosInstance; strategy: string; revision: string; settings: Record<string, unknown>; presetId?: string; baseFee?: number; busy?: boolean }>();
const fields = ref<Field[]>([]);
const first = ref(''), second = ref('');
const firstStep = ref(1), secondStep = ref(1), radius = ref(1);
const extraFeePercent = ref('');
const preview = ref<Sensitivity>();
const selected = ref<Sensitivity>();
const jobs = ref<Sensitivity[]>([]);
const working = ref(false), error = ref('');
let poll: ReturnType<typeof setInterval> | undefined;
const numericFields = computed(() => fields.value.filter(x => x.load && ['IntParameter', 'RealParameter', 'DecimalParameter'].includes(x.param_type)));
const nativeFee = computed(() => typeof props.baseFee === 'number' && Number.isFinite(props.baseFee) ? props.baseFee : 0);
const body = computed(() => ({ strategy: props.strategy, revision: props.revision, preset_id: props.presetId, settings: props.settings,
  axes: [...(first.value ? [{ name: first.value, step: firstStep.value, radius: radius.value }] : []), ...(second.value ? [{ name: second.value, step: secondStep.value, radius: radius.value }] : [])],
  fee_scenarios: extraFeePercent.value.trim() ? [nativeFee.value, Number(extraFeePercent.value) / 100] : [nativeFee.value] }));
function message(e: unknown) { const x = e as { response?: { data?: { detail?: unknown } }; message?: string }; return String(x.response?.data?.detail ?? x.message ?? e); }
async function refresh() { try { jobs.value = (await props.api.get('/studio/sensitivity', { params: { strategy: props.strategy } })).data.jobs ?? []; if (selected.value) selected.value = (await props.api.get('/studio/sensitivity/' + selected.value.id)).data; } catch (e) { error.value = message(e); } }
async function act(task: () => Promise<void>) { working.value = true; error.value = ''; try { await task(); } catch (e) { error.value = message(e); } finally { working.value = false; } }
async function inspect() { await act(async () => { preview.value = (await props.api.post('/studio/sensitivity/preview', body.value)).data; }); }
async function start() { if (!preview.value) return; await act(async () => { selected.value = (await props.api.post('/studio/sensitivity', body.value)).data; preview.value = undefined; await refresh(); }); }
async function open(id: string) { await act(async () => { selected.value = (await props.api.get('/studio/sensitivity/' + id)).data; }); }
async function cancel() { if (!selected.value) return; await act(async () => { selected.value = (await props.api.post('/studio/sensitivity/' + selected.value!.id + '/cancel', {})).data; }); }
function profit(cell: Cell) { const summary = cell.result?.summary as Record<string, unknown> | undefined; const raw = summary?.profit_total_abs; return typeof raw === 'number' && Number.isFinite(raw) ? raw.toFixed(2) + ' USDT' : '—'; }
onMounted(() => { void refresh(); void props.api.get('/studio/optimization-capabilities/' + props.strategy).then(response => { fields.value = response.data.schema?.fields ?? []; first.value = numericFields.value[0]?.name ?? ''; }).catch(e => { error.value = message(e); }); poll = setInterval(() => { if (selected.value && ['prepared', 'running', 'cancelling'].includes(selected.value.status)) void refresh(); }, 3500); });
onUnmounted(() => { if (poll) clearInterval(poll); });
</script>

<template>
  <div class="sensitivity"><h3>Độ nhạy tham số và kịch bản phí</h3><p>Mỗi ô là một backtest native độc lập trên bản dữ liệu đã đóng băng. Phí được đưa vào engine trước khi chạy; ô chưa chạy không có kết quả. Seed chỉ tác động Hyperopt, không làm đổi backtest tất định của cùng một bộ tham số.</p>
    <div class="grid"><label>Tham số 1<select v-model="first" @change="preview=undefined"><option v-for="item in numericFields" :key="item.name" :value="item.name">{{item.name}} ({{item.low}}–{{item.high}})</option></select></label><label>Bước 1<input v-model.number="firstStep" type="number" min="0.000001" step="any" @input="preview=undefined"></label><label>Tham số 2 (tùy chọn)<select v-model="second" @change="preview=undefined"><option value="">Không chọn</option><option v-for="item in numericFields.filter(x=>x.name!==first)" :key="item.name" :value="item.name">{{item.name}}</option></select></label><label>Bước 2<input v-model.number="secondStep" type="number" min="0.000001" step="any" @input="preview=undefined"></label><label>Số bước mỗi phía<select v-model.number="radius" @change="preview=undefined"><option :value="1">1</option><option :value="2">2</option></select></label><label>Phí thêm mỗi chiều (%)<input v-model="extraFeePercent" type="number" min="0" max="1" step="0.001" :placeholder="(nativeFee*100).toFixed(3)" @input="preview=undefined"></label></div>
    <p v-if="!numericFields.length" class="hint">Chiến lược chưa có tham số số native có thể quét. Hãy định nghĩa Parameter và lưu mã trước.</p><div class="actions"><button :disabled="working || busy || !first" @click="inspect">Xem ma trận & ngân sách</button><button :disabled="working || busy || !preview" @click="start">Chạy ma trận đã xem</button><button :disabled="working" @click="refresh">Tải lại</button></div><p v-if="error" class="error" role="alert">{{error}}</p>
    <div v-if="preview" class="box"><h4>Xem trước {{preview.estimated_backtests}} backtest</h4><p>{{preview.axes.map(x=>x.name+': '+x.values.join(', ')).join(' · ')}}. Phí gồm {{[...new Set(preview.cells.map(x=>x.fee))].map(x=>(x*100).toFixed(3)+'%').join(', ')}} mỗi chiều.</p><p>Chỉ các ô được chạy thành công mới có số liệu. Không tự chọn bộ tham số hay đổi paper.</p></div>
    <div class="box"><h4>Lịch sử ma trận</h4><p v-if="!jobs.length">Chưa có tác vụ.</p><div class="actions"><button v-for="job in jobs" :key="job.id" @click="open(job.id)">{{job.id.slice(0,10)}} · {{job.status}} · {{job.completed_cells}}/{{job.cells.length}}</button></div></div>
    <div v-if="selected" class="box"><div class="actions"><h4>Ma trận {{selected.id.slice(0,10)}} · {{selected.status}}</h4><button v-if="['prepared','running'].includes(selected.status)" :disabled="working" @click="cancel">Dừng</button></div><p>{{selected.completed_cells}}/{{selected.cells.length}} ô đã xử lý. {{selected.error || ''}}</p><div class="table-wrap"><table><thead><tr><th>Tham số</th><th>Phí mỗi chiều</th><th>Trạng thái</th><th>Lãi/lỗ ròng</th><th>Lý do</th></tr></thead><tbody><tr v-for="cell in selected.cells" :key="cell.index"><td>{{JSON.stringify(cell.parameters)}}</td><td>{{(cell.fee*100).toFixed(3)}}%</td><td>{{cell.status}}</td><td>{{profit(cell)}}</td><td>{{cell.error || '—'}}</td></tr></tbody></table></div></div>
  </div>
</template>

<style scoped>
.sensitivity{line-height:1.5}.sensitivity p{color:var(--fg-2)}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.grid label{font-size:12px}.grid input,.grid select{display:block;width:100%;padding:8px;margin-top:5px;color:var(--fg);background:var(--bg);border:1px solid var(--line-2);border-radius:6px}.actions{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin:14px 0}.actions h4{margin-right:auto}button{padding:8px 12px;color:var(--fg);background:var(--bg-2);border:1px solid var(--line-2);border-radius:7px;cursor:pointer}button:disabled{opacity:.5}.box{padding:15px;margin:15px 0;border:1px solid var(--line);border-radius:9px}.hint{padding:10px;background:var(--bg-2)}.error{color:#ffb4b4}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:8px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}@media(max-width:800px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:550px){.grid{grid-template-columns:1fr}}
</style>
