<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import type { AxiosInstance } from 'axios';
import WfaWindowTable from './WfaWindowTable.vue';
import { mapWalkForwardWindowRow } from '@/utils/strategyLibrary';

type Window = { index: number; train_timerange: string; oos_timerange: string; status: string; error?: string; baseline?: Record<string, unknown>; candidate?: Record<string, unknown>; hyperopt?: Record<string, unknown> };
type HoldoutPayload = { status?: string; selection?: { window?: number; epoch?: number }; baseline?: Record<string, unknown>; candidate?: Record<string, unknown>; [key: string]: unknown };
type RecordWfa = { id: string; status: string; strategy: string; created_at: string; completed_windows: number; incomplete_windows?: number; research_status?: string; current_stage?: string; windows: Window[]; holdout_timerange?: string; holdout_status?: string; holdout?: HoldoutPayload; error?: string; estimated_hyperopt_epochs?: number; estimated_backtests?: number; estimated_input_bytes?: number };
type Preview = { windows: Window[]; holdout_timerange?: string; estimated_hyperopt_epochs: number; estimated_backtests: number; estimated_input_bytes: number; warnings?: string[] };
const props = defineProps<{ api: AxiosInstance; strategy: string; revision: string; settings: Record<string, unknown>; presetId?: string; warmupCandles?: number; busy?: boolean }>();
const trainDays = ref(90), oosDays = ref(30), gapDays = ref(0), holdoutDays = ref(30), maxWindows = ref(4), epochs = ref(30), seed = ref(42), minTrades = ref(10);
const spaces = ref<string[]>(['buy', 'sell']);
const loss = ref('SharpeHyperOptLossDaily');
const capabilities = ref<{ spaces: { id: string; enabled: boolean }[]; losses: { id: string; label: string }[] }>();
const jobs = ref<RecordWfa[]>([]), selected = ref<RecordWfa>(), preview = ref<Preview>();
const working = ref(false), error = ref(''), notice = ref('');
let poll: ReturnType<typeof setInterval> | undefined;
const plan = computed(() => ({ strategy: props.strategy, revision: props.revision, preset_id: props.presetId, settings: props.settings, train_days: trainDays.value, oos_days: oosDays.value, gap_days: gapDays.value, holdout_days: holdoutDays.value, max_windows: maxWindows.value, epochs: epochs.value, spaces: spaces.value, loss: loss.value, random_state: seed.value, min_trades: minTrades.value, workers: 1 }));
function value(result: Record<string, unknown> | undefined, key: string): number | null { const summary = result?.summary as Record<string, unknown> | undefined; const raw = summary?.[key]; return typeof raw === 'number' && Number.isFinite(raw) ? raw : null; }
function money(result: Record<string, unknown> | undefined) { const raw = value(result, 'profit_total_abs'); return raw == null ? '—' : raw.toFixed(2) + ' USDT'; }
function pct(result: Record<string, unknown> | undefined, key: string) { const raw = value(result, key); return raw == null ? '—' : (raw * 100).toFixed(2) + '%'; }
function trades(result: Record<string, unknown> | undefined) { const raw = value(result, 'total_trades'); return raw == null ? '—' : String(raw); }
const nativeRows = computed(() => (selected.value?.windows ?? []).map(w => mapWalkForwardWindowRow(w)));
function message(e: unknown) { const x = e as { response?: { data?: { detail?: unknown } }; message?: string }; return String(x.response?.data?.detail ?? x.message ?? e); }
async function refresh() {
  try {
    jobs.value = (await props.api.get('/studio/walk-forward', { params: { strategy: props.strategy } })).data.jobs ?? [];
    if (selected.value) selected.value = (await props.api.get('/studio/walk-forward/' + selected.value.id)).data;
  } catch (e) { error.value = message(e); }
}
async function act(fn: () => Promise<void>) { working.value = true; error.value = ''; notice.value = ''; try { await fn(); } catch (e) { error.value = message(e); } finally { working.value = false; } }
async function inspect() { await act(async () => {
  const audit = (await props.api.get('/studio/data-quality', { params: { timerange: props.settings.timerange, timeframe: props.settings.timeframe, detail_timeframe: props.settings.timeframe_detail, warmup_candles: props.warmupCandles ?? 200, verify_funding: false } })).data as { status: string; issues?: { message: string }[] };
  if (['missing', 'invalid'].includes(audit.status)) throw Error('Dữ liệu chưa đủ cho walk-forward: ' + (audit.issues?.[0]?.message ?? audit.status) + '. Mở bước Dữ liệu để tải bù.');
  preview.value = (await props.api.post('/studio/walk-forward/preview', plan.value)).data;
}); }
async function start() { if (!preview.value) return; await act(async () => { selected.value = (await props.api.post('/studio/walk-forward', plan.value)).data; preview.value = undefined; notice.value = 'Đã bắt đầu chuỗi train/OOS đúng kế hoạch đã xem. Holdout vẫn khóa.'; await refresh(); }); }
async function open(id: string) { await act(async () => { selected.value = (await props.api.get('/studio/walk-forward/' + id)).data; }); }
async function cancel() { if (!selected.value) return; await act(async () => { selected.value = (await props.api.post('/studio/walk-forward/' + selected.value!.id + '/cancel', {})).data; await refresh(); }); }
async function holdout() { if (!selected.value) return; await act(async () => { selected.value = (await props.api.post('/studio/walk-forward/' + selected.value!.id + '/holdout', {})).data; await refresh(); }); }
onMounted(() => { void refresh(); void props.api.get('/studio/optimization-capabilities/' + props.strategy).then(response => { capabilities.value = response.data; const enabled = capabilities.value?.spaces.filter(item => item.enabled).map(item => item.id) ?? []; spaces.value = enabled.filter(id => ['buy', 'sell'].includes(id)); if (!spaces.value.length && enabled[0]) spaces.value = [enabled[0]]; if (!capabilities.value?.losses.some(item => item.id === loss.value)) loss.value = capabilities.value?.losses[0]?.id ?? ''; }).catch(e => { error.value = message(e); }); poll = setInterval(() => { if (selected.value && ['prepared', 'running', 'cancelling', 'holdout_running'].includes(selected.value.status)) void refresh(); }, 3500); });
onUnmounted(() => { if (poll) clearInterval(poll); });
</script>

<template>
  <div class="wfa">
    <h3>Walk-forward · rolling train/OOS</h3>
    <p>Mỗi cửa sổ tối ưu bằng Hyperopt chính thức trên tập học, sau đó backtest độc lập trên OOS. Holdout cuối được đánh giá bằng thao tác riêng. Cần dữ liệu đầy đủ và ngày kết thúc đã chọn ở Backtest.</p>
    <div class="grid"><label>Train (ngày)<input v-model.number="trainDays" type="number" min="14" max="730" @input="preview=undefined"></label><label>OOS (ngày)<input v-model.number="oosDays" type="number" min="7" max="180" @input="preview=undefined"></label><label>Gap (ngày)<input v-model.number="gapDays" type="number" min="0" max="60" @input="preview=undefined"></label><label>Holdout (ngày)<input v-model.number="holdoutDays" type="number" min="7" max="180" @input="preview=undefined"></label><label>Số cửa sổ tối đa<input v-model.number="maxWindows" type="number" min="2" max="12" @input="preview=undefined"></label><label>Epoch mỗi cửa sổ<input v-model.number="epochs" type="number" min="1" max="1000" @input="preview=undefined"></label><label>Seed<input v-model.number="seed" type="number" @input="preview=undefined"></label><label>Số lệnh tối thiểu<input v-model.number="minTrades" type="number" min="1" @input="preview=undefined"></label><label>Nhóm tham số (Ctrl để chọn nhiều)<select v-model="spaces" multiple @change="preview=undefined"><option v-for="item in capabilities?.spaces.filter(x=>x.enabled)" :key="item.id" :value="item.id">{{item.id}}</option></select></label><label>Loss native<select v-model="loss" @change="preview=undefined"><option v-for="item in capabilities?.losses" :key="item.id" :value="item.id">{{item.label}}</option></select></label></div>
    <div class="actions"><button :disabled="working || busy" @click="inspect">Xem kế hoạch</button><button :disabled="working || busy || !preview" @click="start">Chạy đúng kế hoạch đã xem</button><button :disabled="working" @click="refresh">Tải lại</button></div>
    <p v-if="error" class="error" role="alert">{{error}}</p><p v-if="notice" role="status">{{notice}}</p>
    <div v-if="preview" class="box">
      <h4>Kế hoạch trước khi chạy</h4>
      <p>{{preview.windows.length}} cửa sổ · {{preview.estimated_hyperopt_epochs}} epoch Hyperopt · {{preview.estimated_backtests}} backtest · khoảng {{(preview.estimated_input_bytes/1048576).toFixed(1)}} MB dữ liệu. Holdout: {{preview.holdout_timerange || 'chưa có'}}.</p>
      <p v-for="warning in preview.warnings" :key="warning" class="hint">{{warning}}</p>
      <div class="wfa-timeline">
        <div v-for="w in preview.windows" :key="w.index" class="wfa-timeline-row">
          <span class="wfa-win-idx">#{{w.index}}</span>
          <span class="wfa-seg train">Train: {{w.train_timerange}}</span>
          <span v-if="gapDays > 0" class="wfa-seg gap">Gap {{gapDays}}d</span>
          <span class="wfa-seg oos">OOS: {{w.oos_timerange}}</span>
        </div>
        <div v-if="preview.holdout_timerange" class="wfa-timeline-row">
          <span class="wfa-win-idx">🔒</span>
          <span class="wfa-seg holdout">Holdout niêm phong: {{preview.holdout_timerange}}</span>
        </div>
      </div>
    </div>
    <div class="box"><h4>Thí nghiệm đã lưu</h4><p v-if="!jobs.length">Chưa có chuỗi walk-forward.</p><div class="jobs"><button v-for="job in jobs" :key="job.id" @click="open(job.id)">{{job.id.slice(0,10)}} · {{job.status}} · {{job.completed_windows}} cửa sổ</button></div></div>
    <div v-if="selected" class="box">
      <div class="actions"><h4>Chuỗi {{selected.id.slice(0,10)}} · {{selected.status}}</h4><button v-if="['prepared','running'].includes(selected.status)" :disabled="working" @click="cancel">Dừng chuỗi</button></div>
      <p>{{selected.current_stage || '—'}} · {{selected.completed_windows}}/{{selected.windows.length}} cửa sổ đã xử lý · nghiên cứu: {{selected.research_status || 'chưa kết luận'}} · cửa sổ chưa đủ: {{selected.incomplete_windows ?? '—'}}. {{selected.error || ''}}</p>
      <div class="wfa-timeline">
        <div v-for="w in selected.windows" :key="w.index" class="wfa-timeline-row">
          <span class="wfa-win-idx">#{{w.index}}</span>
          <span class="wfa-seg train">Train: {{w.train_timerange}}</span>
          <span v-if="gapDays > 0" class="wfa-seg gap">Gap {{gapDays}}d</span>
          <span class="wfa-seg oos">OOS: {{w.oos_timerange}} · {{w.status}}</span>
        </div>
        <div v-if="selected.holdout_timerange" class="wfa-timeline-row">
          <span class="wfa-win-idx">🔒</span>
          <span class="wfa-seg holdout">Holdout ({{selected.holdout_status || 'sealed'}}): {{selected.holdout_timerange}}</span>
        </div>
      </div>
      <WfaWindowTable :windows="nativeRows"/>
      <div class="table-wrap">
        <table>
          <thead><tr><th>#</th><th>Train</th><th>OOS</th><th>Trạng thái</th><th>Train tốt nhất</th><th>Baseline OOS</th><th>Ứng viên OOS</th><th>Lý do lỗi</th></tr></thead>
          <tbody>
            <tr v-for="w in selected.windows" :key="w.index">
              <td>{{w.index}}</td>
              <td>{{w.train_timerange}}</td>
              <td>{{w.oos_timerange}}</td>
              <td>{{w.status}}</td>
              <td>{{mapWalkForwardWindowRow(w).train_profit_abs != null ? mapWalkForwardWindowRow(w).train_profit_abs!.toFixed(2) + ' USDT' : '—'}} · {{mapWalkForwardWindowRow(w).train_trades ?? '—'}} lệnh</td>
              <td>{{money(w.baseline)}} · {{trades(w.baseline)}} lệnh</td>
              <td>{{money(w.candidate)}} · {{trades(w.candidate)}} lệnh</td>
              <td>{{w.error || String(w.candidate?.error || '—')}}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="hint">Mỗi OOS bắt đầu không vị thế. Các tỷ suất phần trăm và drawdown của các cửa sổ không được cộng để gọi là kết quả toàn kỳ.</p>
      <div class="box">
        <h4>Holdout {{selected.holdout_timerange || '—'}}</h4>
        <p>Trạng thái: {{selected.holdout_status || 'sealed'}}. Chỉ mở sau khi toàn bộ OOS hoàn tất; mỗi lần mở được lưu lại.</p>
        <button :disabled="working || selected.status!=='success' || selected.holdout_status!=='sealed'" @click="holdout">Đánh giá holdout một lần</button>
        <template v-if="selected.holdout">
          <div class="holdout-grid">
            <div class="holdout-card">
              <h5>Baseline (không tối ưu)</h5>
              <dl>
                <div><dt>Trạng thái</dt><dd>{{String(selected.holdout.baseline?.status ?? selected.holdout.status ?? '—')}}</dd></div>
                <div><dt>Lãi/lỗ USDT</dt><dd>{{money(selected.holdout.baseline)}}</dd></div>
                <div><dt>Lợi nhuận %</dt><dd>{{pct(selected.holdout.baseline, 'profit_total')}}</dd></div>
                <div><dt>Drawdown tối đa</dt><dd>{{pct(selected.holdout.baseline, 'max_drawdown_account')}}</dd></div>
                <div><dt>Số lệnh</dt><dd>{{trades(selected.holdout.baseline)}}</dd></div>
              </dl>
            </div>
            <div class="holdout-card">
              <h5>Ứng viên (từ cửa sổ #{{selected.holdout.selection?.window ?? '—'}}, lượt {{selected.holdout.selection?.epoch ?? '—'}})</h5>
              <dl>
                <div><dt>Trạng thái</dt><dd>{{String(selected.holdout.candidate?.status ?? selected.holdout.status ?? '—')}}</dd></div>
                <div><dt>Lãi/lỗ USDT</dt><dd>{{money(selected.holdout.candidate)}}</dd></div>
                <div><dt>Lợi nhuận %</dt><dd>{{pct(selected.holdout.candidate, 'profit_total')}}</dd></div>
                <div><dt>Drawdown tối đa</dt><dd>{{pct(selected.holdout.candidate, 'max_drawdown_account')}}</dd></div>
                <div><dt>Số lệnh</dt><dd>{{trades(selected.holdout.candidate)}}</dd></div>
              </dl>
            </div>
          </div>
          <details><summary>Xem JSON holdout gốc</summary><pre>{{JSON.stringify(selected.holdout,null,2)}}</pre></details>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wfa,.wfa *{text-align:left}.wfa{line-height:1.55}.wfa h3{margin:0 0 8px;font-size:18px;font-weight:650}.wfa h4{margin:0 0 8px;font-size:14.5px;font-weight:600}.wfa h5{margin:0 0 10px;font-size:13.5px;font-weight:600;color:var(--fg)}.wfa p{color:var(--fg-2);margin:8px 0}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:14px 0}.grid label{font-size:12px;color:var(--fg-2);font-weight:500}.grid input,.grid select{display:block;width:100%;padding:8px 10px;margin-top:5px;background:var(--bg);color:var(--fg);border:1px solid var(--line-2);border-radius:6px;font:inherit;font-size:12.5px}.actions,.jobs{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:12px 0}.actions h4{margin-right:auto}button{padding:8px 12px;border:1px solid var(--line-2);border-radius:7px;background:var(--bg-2);color:var(--fg);font:inherit;font-size:12.5px;font-weight:500;cursor:pointer}button:hover:not(:disabled){border-color:var(--accent);color:var(--accent)}button:disabled{opacity:.45}.box{border:1px solid var(--line);background:var(--bg);border-radius:10px;padding:16px;margin:14px 0}.error{color:#ffb4b4;padding:10px 12px;background:#3c2024;border-radius:6px}.hint{padding:10px 12px;background:var(--bg-2);border-left:3px solid var(--accent);border-radius:6px;font-size:12.5px}.wfa-timeline{display:grid;gap:6px;margin:10px 0}.wfa-timeline-row{display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:12px;font-variant-numeric:tabular-nums}.wfa-win-idx{min-width:28px;font-weight:650;color:var(--fg-3)}.wfa-seg{padding:4px 9px;border-radius:5px;border:1px solid var(--line-2);background:var(--bg-1)}.wfa-seg.train{border-color:#266d5e;background:color-mix(in srgb,#268b77 14%,var(--bg-1))}.wfa-seg.gap{border-style:dashed;color:var(--fg-3)}.wfa-seg.oos{border-color:#3a5c8c;background:color-mix(in srgb,#4a7ec7 14%,var(--bg-1))}.wfa-seg.holdout{border-color:#8c6a2b;background:color-mix(in srgb,#e7bb72 14%,var(--bg-1))}.holdout-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:12px 0}.holdout-card{border:1px solid var(--line);background:var(--bg-1);border-radius:8px;padding:12px}.holdout-card dl{margin:0;display:grid;gap:6px}.holdout-card dl div{display:flex;justify-content:space-between;gap:8px;font-size:12.5px;font-variant-numeric:tabular-nums}.holdout-card dt{color:var(--fg-2)}.holdout-card dd{margin:0;font-weight:600}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:8px;margin-top:10px}table{width:100%;border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums}th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}th{background:var(--bg-2);color:var(--fg-3);font-weight:600}pre{overflow:auto;font-size:11.5px;background:var(--bg-1);padding:12px;border-radius:6px}@media(max-width:850px){.grid,.holdout-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:540px){.grid,.holdout-grid{grid-template-columns:1fr}}
</style>
