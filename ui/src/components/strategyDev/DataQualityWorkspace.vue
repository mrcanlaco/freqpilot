<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue';
import type { AxiosInstance } from 'axios';

type Issue = { code: string; severity: string; message: string; start?: string; end?: string };
type FileRow = { pair: string; timeframe: string; type: string; rows: number; start: string; end: string; last_closed?: string; sha256: string; status: string; issues: Issue[] };
type Quality = { status: string; checked_at: string; files: FileRow[]; issues: Issue[]; funding_verification: { status: string; reason?: string } };
type RepairPreview = { id: string; expires_at: string; operations: { pair: string; timeframe: string; type: string; start: string; end: string; reason: string }[]; estimated_files: number; estimated_candles: number; note: string };
type Repair = { id: string; status: string; error?: string };
const props = defineProps<{ api: AxiosInstance; timerange: string; timeframe: string; detailTimeframe: string; warmupCandles: number }>();
const emit = defineEmits<{ updated: [] }>();
const quality = ref<Quality>();
const preview = ref<RepairPreview>();
const repair = ref<Repair>();
const busy = ref(false);
const error = ref('');
let poll: ReturnType<typeof setInterval> | undefined;
const params = computed(() => ({ timerange: props.timerange, timeframe: props.timeframe, detail_timeframe: props.detailTimeframe, warmup_candles: props.warmupCandles }));
const valid = computed(() => /^\d{8}-\d{8}$/.test(props.timerange));
function message(e: unknown) { const x = e as { response?: { data?: { detail?: unknown } }; message?: string }; return String(x.response?.data?.detail ?? x.message ?? e); }
async function inspect(verifyFunding = false) {
  if (!valid.value) { error.value = 'Chọn ngày bắt đầu và kết thúc trước khi kiểm tra.'; return; }
  busy.value = true; error.value = ''; preview.value = undefined;
  try { quality.value = (await props.api.get('/studio/data-quality', { params: { ...params.value, verify_funding: verifyFunding } })).data; }
  catch (e) { error.value = message(e); }
  finally { busy.value = false; }
}
async function planRepair() {
  if (!valid.value) { error.value = 'Chọn khoảng ngày đóng trước khi xem kế hoạch tải bù.'; return; }
  busy.value = true; error.value = '';
  try { preview.value = (await props.api.get('/studio/data-repair/preview', { params: { ...params.value, verify_funding: true } })).data; }
  catch (e) { error.value = message(e); }
  finally { busy.value = false; }
}
async function refreshRepair() {
  if (!repair.value) return;
  try {
    repair.value = (await props.api.get('/studio/data-repair/' + repair.value.id)).data;
    if (!['pending', 'running'].includes(repair.value?.status ?? '')) {
      if (poll) clearInterval(poll);
      poll = undefined;
      if (repair.value?.status === 'success') { emit('updated'); await inspect(); }
    }
  } catch (e) { error.value = message(e); if (poll) clearInterval(poll); poll = undefined; }
}
async function startRepair() {
  if (!preview.value || busy.value) return;
  busy.value = true; error.value = '';
  try {
    repair.value = (await props.api.post('/studio/data-repair', { preview_id: preview.value.id })).data;
    if (poll) clearInterval(poll);
    poll = setInterval(() => void refreshRepair(), 2500);
  } catch (e) { error.value = message(e); }
  finally { busy.value = false; }
}
onUnmounted(() => { if (poll) clearInterval(poll); });
</script>

<template>
  <div class="quality">
    <h3>Kiểm tra dữ liệu Binance Futures</h3>
    <p>Khoảng ngày dùng chung với Backtest: <b>{{timerange}}</b> UTC, gồm nến khởi động {{warmupCandles}} cây. Ngày kết thúc không được tính. Kết quả kiểm tra gắn với dấu vân tay của dữ liệu tại thời điểm kiểm tra.</p>
    <div class="actions"><button :disabled="busy || !valid" @click="inspect(false)">Kiểm tra dữ liệu trên máy</button><button :disabled="busy || !valid" @click="inspect(true)">Đối chiếu funding với Binance</button><button :disabled="busy || !valid" @click="planRepair">Xem kế hoạch tải bù</button></div>
    <p v-if="error" class="error" role="alert">{{error}}</p>
    <div v-if="quality" class="card" role="status"><b>Trạng thái: {{quality.status}}</b><span>Kiểm tra {{new Date(quality.checked_at).toLocaleString('vi-VN')}}</span><span>Funding từ Binance: {{quality.funding_verification.status}} · {{quality.funding_verification.reason || 'Xem trạng thái từng cặp'}}</span></div>
    <div v-if="quality?.issues.length" class="card"><h4>Vấn đề cần xử lý</h4><ul><li v-for="(issue, i) in quality.issues" :key="i">{{issue.code}}: {{issue.message}} <small>{{issue.start}} {{issue.end}}</small></li></ul></div>
    <div v-if="quality?.files.length" class="table-wrap"><table><thead><tr><th>Cặp</th><th>Loại</th><th>Khung</th><th>Trạng thái</th><th>Từ UTC</th><th>Đến UTC</th><th>Nến đóng cuối</th><th>Bản ghi</th><th>Dấu vân tay</th></tr></thead><tbody><tr v-for="file in quality.files" :key="file.pair+file.type+file.timeframe"><td>{{file.pair}}</td><td>{{file.type}}</td><td>{{file.timeframe}}</td><td>{{file.status}}</td><td>{{file.start}}</td><td>{{file.end}}</td><td>{{file.last_closed || '—'}}</td><td>{{file.rows}}</td><td><code>{{file.sha256?.slice(0,10) || '—'}}</code></td></tr></tbody></table></div>
    <div v-if="preview" class="card"><h4>Kế hoạch tải bù · chỉ xem trước</h4><p>{{preview.operations.length}} phần · dự kiến {{preview.estimated_candles}} nến. Hết hạn {{new Date(preview.expires_at).toLocaleString('vi-VN')}}.</p><p>{{preview.note}}</p><ul><li v-for="(op, i) in preview.operations" :key="i">{{op.pair}} · {{op.type}} {{op.timeframe}} · {{op.start}} → {{op.end}} · {{op.reason}}</li></ul><button v-if="preview.operations.length" :disabled="busy || !!repair && ['pending','running'].includes(repair.status)" @click="startRepair">Tải bổ sung đúng kế hoạch này</button></div>
    <p v-if="repair" role="status">Tác vụ tải bù {{repair.id.slice(0,10)}}: {{repair.status}} <span v-if="repair.error">· {{repair.error}}</span></p>
  </div>
</template>

<style scoped>
.quality,.quality *{text-align:left}.quality{line-height:1.55}.quality h3{margin:0 0 8px;font-size:18px;font-weight:650}.quality h4{margin:0 0 8px;font-size:14.5px;font-weight:600}.quality p{color:var(--fg-2);margin:8px 0}.actions{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}.actions button,.card button{border:1px solid var(--line-2);border-radius:7px;background:var(--bg-2);color:var(--fg);padding:8px 13px;font-size:12.5px;font-weight:500;cursor:pointer;transition:border-color .15s}.actions button:hover:not(:disabled),.card button:hover:not(:disabled){border-color:var(--accent);color:var(--accent)}.actions button:disabled,.card button:disabled{opacity:.45;cursor:default}.card{padding:16px;border:1px solid var(--line);background:var(--bg);border-radius:9px;margin:14px 0}.card>span{display:block;margin-top:6px;color:var(--fg-2);font-size:12.5px}.error{padding:12px 14px;background:#3c2024;border-left:3px solid #ee8989;border-radius:6px;color:#ffb4b4}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:8px;background:var(--bg);margin-top:12px}table{width:100%;border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums}th,td{padding:9px 11px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}th{color:var(--fg-3);font-weight:600;background:var(--bg-2)}li{margin:6px 0;font-size:13px}small{color:var(--fg-3)}
</style>
