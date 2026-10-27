<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import type { AxiosInstance } from 'axios';

type SessionSummary = { id: string; profile_id: string; strategy: string; label?: string; status: string; started_at: string; closed_at?: string; trade_count: number; warning_count: number };
type Session = SessionSummary & { paper_trades?: Record<string, unknown>[]; gaps?: Record<string, unknown>[]; warnings?: string[]; evidence?: Record<string, string> };
type Comparison = { status: string; counts: { matched: number; different: number; insufficient: number }; trades: { paper_trade_id: string | number; status: string; reasons?: string[]; field_differences?: Record<string, unknown> }[]; warnings: string[] };
const props = defineProps<{ api: AxiosInstance; runId?: string }>();
type AvailableRun = { id: string; strategy: string; status: string; settings?: Record<string, unknown>; summary?: { total_trades?: number; profit_total_abs?: number } };
const profiles = ref<{ id: string; label: string; strategy: string }[]>([]);
const activeProfile = ref('');
const sessions = ref<SessionSummary[]>([]);
const selected = ref<Session>();
const comparison = ref<Comparison>();
const availableRuns = ref<AvailableRun[]>([]);
const matchingRuns = computed(() => availableRuns.value.filter(r => r.status === 'success' && (!selected.value?.strategy || r.strategy === selected.value.strategy)));
const runIdInput = ref('');
const label = ref('');
const busy = ref(false);
const error = ref('');
const notice = ref('');
function message(e: unknown) { const x = e as { response?: { data?: { detail?: unknown } }; message?: string }; return String(x.response?.data?.detail ?? x.message ?? e); }
async function refresh() {
  try {
    const paper = (await props.api.get('/studio/paper')).data as { active_profile?: string; profiles?: { id: string; label: string; strategy: string }[] };
    profiles.value = paper.profiles ?? [];
    activeProfile.value = paper.active_profile ?? '';
    sessions.value = (await props.api.get('/studio/paper/reconcile/sessions')).data.sessions;
    if (selected.value) selected.value = (await props.api.get('/studio/paper/reconcile/sessions/' + selected.value.id)).data;
    try {
      const runsResp = (await props.api.get('/studio/runs')).data as { runs?: AvailableRun[] };
      availableRuns.value = (runsResp.runs ?? []).filter(r => r.status === 'success');
    } catch { /* Optional run list for quick selection must not fail paper reconcile refresh. */ }
  } catch (e) { error.value = message(e); }
}
async function act(task: () => Promise<void>) {
  busy.value = true; error.value = ''; notice.value = '';
  try { await task(); await refresh(); } catch (e) { error.value = message(e); }
  finally { busy.value = false; }
}
async function openSession(id: string) { await act(async () => { selected.value = (await props.api.get('/studio/paper/reconcile/sessions/' + id)).data; comparison.value = undefined; }); }
async function create() { if (!activeProfile.value) return; await act(async () => { selected.value = (await props.api.post('/studio/paper/reconcile/sessions', { profile_id: activeProfile.value, label: label.value || undefined })).data; notice.value = 'Đã bắt đầu quan sát từ bây giờ; không hồi tố lịch sử.'; }); }
async function capture() { if (!selected.value) return; await act(async () => { selected.value = (await props.api.post('/studio/paper/reconcile/sessions/' + selected.value!.id + '/capture', {})).data; notice.value = 'Đã chụp bằng chứng paper mới nhất.'; }); }
async function close() { if (!selected.value) return; await act(async () => { selected.value = (await props.api.post('/studio/paper/reconcile/sessions/' + selected.value!.id + '/close', {})).data; notice.value = 'Đã đóng phiên quan sát.'; }); }
async function backtestSession() { if (!selected.value) return; await act(async () => { const result = (await props.api.post('/studio/paper/reconcile/sessions/' + selected.value!.id + '/backtest', {})).data as { id: string }; runIdInput.value = result.id; notice.value = 'Đã gửi backtest native từ đúng hồ sơ paper. Chờ hồ sơ hoàn tất trước khi so sánh; không gửi lại tự động.'; }); }
async function compare() { if (!selected.value || !(runIdInput.value || props.runId)) return; await act(async () => { comparison.value = (await props.api.post('/studio/paper/reconcile/sessions/' + selected.value!.id + '/compare', { run_id: runIdInput.value || props.runId })).data; }); }
onMounted(() => { runIdInput.value = props.runId ?? ''; void refresh(); });
</script>

<template>
  <article class="reconcile">
    <div class="row"><h3>Đối chiếu paper với backtest</h3><button :disabled="busy" @click="refresh">Tải lại</button></div>
    <p>Quan sát lệnh từ database dry-run của Freqtrade. Phiên chỉ bắt đầu khi bạn nhấn nút, không tự chạy hay đổi bot. Giá paper có thể khác giá mô phỏng backtest.</p>
    <p v-if="error" class="error" role="alert">{{error}}</p><p v-if="notice" role="status">{{notice}}</p>
    <div class="box"><b>Hồ sơ paper đang chọn</b><p>{{profiles.find(p=>p.id===activeProfile)?.label || 'Chưa có hồ sơ active'}}</p><label>Nhãn phiên quan sát<input v-model="label" placeholder="Ví dụ: tuần này" maxlength="70"></label><button :disabled="busy || !activeProfile" @click="create">Bắt đầu phiên quan sát</button></div>
    <div class="box"><h4>Lịch sử quan sát</h4><p v-if="!sessions.length">Chưa có phiên nào.</p><div class="sessions"><button v-for="session in sessions" :key="session.id" :class="{active:selected?.id===session.id}" @click="openSession(session.id)"><b>{{session.label || session.strategy}}</b><span>{{session.status}} · {{session.trade_count}} lệnh · {{new Date(session.started_at).toLocaleString('vi-VN')}}</span></button></div></div>
    <div v-if="selected" class="box"><h4>Phiên {{selected.id.slice(0,10)}} · {{selected.status}}</h4><p>{{selected.paper_trades?.length ?? selected.trade_count ?? 0}} lệnh paper được quan sát · {{selected.gaps?.length ?? 0}} khoảng thiếu quan sát. Tín hiệu không lưu được được đánh dấu chưa quan sát.</p><p v-for="warning in selected.warnings" :key="warning" class="hint">{{warning}}</p><div class="row"><button :disabled="busy || selected.status!=='observing'" @click="capture">Chụp bằng chứng hiện tại</button><button :disabled="busy || selected.status!=='observing'" @click="close">Đóng phiên quan sát</button><button :disabled="busy || selected.status!=='closed'" @click="backtestSession">Backtest cùng phiên bằng engine gốc</button></div><label v-if="matchingRuns.length">Chọn nhanh gói backtest hoàn tất cùng chiến lược<select v-model="runIdInput"><option value="">— Chọn gói backtest đã lưu —</option><option v-for="r in matchingRuns" :key="r.id" :value="r.id">{{r.id.slice(0,10)}} · {{r.settings?.timerange ?? '—'}} · {{r.summary?.total_trades ?? '—'}} lệnh</option></select></label><label>ID backtest cùng hồ sơ và cùng khoảng<input v-model="runIdInput" :placeholder="runId || 'Chọn hồ sơ backtest đã lưu'"></label><button :disabled="busy || selected.status!=='closed' || !(runIdInput || runId)" @click="compare">So sánh với backtest</button></div>
    <div v-if="comparison" class="box"><h4>Kết quả: {{comparison.status}}</h4><p>Khớp {{comparison.counts.matched}} · Khác {{comparison.counts.different}} · Chưa đủ bằng chứng {{comparison.counts.insufficient}}.</p><p v-for="warning in comparison.warnings" :key="warning" class="hint">{{warning}}</p><div class="table-wrap" v-if="comparison.trades.length"><table><thead><tr><th>Lệnh paper</th><th>Trạng thái</th><th>Lý do</th><th>Sai khác</th></tr></thead><tbody><tr v-for="(trade, index) in comparison.trades" :key="index"><td>{{trade.paper_trade_id ?? '—'}}</td><td>{{trade.status}}</td><td>{{trade.reasons?.join('; ') || '—'}}</td><td><pre>{{JSON.stringify(trade.field_differences ?? {}, null, 2)}}</pre></td></tr></tbody></table></div></div>
  </article>
</template>

<style scoped>
.reconcile,.reconcile *{text-align:left}.reconcile{margin-top:20px;padding:20px;border:1px solid var(--line);background:var(--bg-1);border-radius:12px;line-height:1.55}.reconcile h3{margin:0;font-size:18px;font-weight:650}.reconcile h4{margin:0 0 8px;font-size:15px;font-weight:600}.reconcile p{color:var(--fg-2);font-size:13px;margin:8px 0}.row{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.row h3{margin-right:auto}.box{border:1px solid var(--line);background:var(--bg);border-radius:10px;padding:16px;margin:14px 0}button{border:1px solid var(--line-2);background:var(--bg-2);color:var(--fg);padding:8px 13px;border-radius:7px;font:inherit;font-size:12.5px;font-weight:500;cursor:pointer}button:hover:not(:disabled){border-color:var(--accent);color:var(--accent)}button:disabled{opacity:.45}input,select{display:block;width:min(450px,100%);margin:6px 0 12px;padding:8px 11px;background:var(--bg-1);color:var(--fg);border:1px solid var(--line-2);border-radius:6px;font:inherit;font-size:13px}label{display:block;font-size:12px;color:var(--fg-2);font-weight:500;margin-top:8px}.sessions{display:flex;gap:8px;overflow:auto;padding-bottom:4px}.sessions button{min-width:220px;text-align:left;display:grid;gap:5px;background:var(--bg-1)}.sessions button.active{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 12%,var(--bg-1))}.sessions span{font-size:11px;color:var(--fg-2)}.error{color:#ffb4b4;padding:10px 12px;background:#3c2024;border-radius:6px}.hint{padding:10px 12px;background:var(--bg-2);border-left:3px solid var(--accent);border-radius:6px}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:8px;margin-top:10px}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--line)}th{background:var(--bg-2);color:var(--fg-3);font-weight:600}pre{white-space:pre-wrap;max-width:400px;margin:0;font-size:11.5px}
</style>
