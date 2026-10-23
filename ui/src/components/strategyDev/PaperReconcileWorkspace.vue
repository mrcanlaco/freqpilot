<script setup lang="ts">
import { onMounted, ref } from 'vue';
import type { AxiosInstance } from 'axios';

type SessionSummary = { id: string; profile_id: string; strategy: string; label?: string; status: string; started_at: string; closed_at?: string; trade_count: number; warning_count: number };
type Session = SessionSummary & { paper_trades?: Record<string, unknown>[]; gaps?: Record<string, unknown>[]; warnings?: string[]; evidence?: Record<string, string> };
type Comparison = { status: string; counts: { matched: number; different: number; insufficient: number }; trades: { paper_trade_id: string | number; status: string; reasons?: string[]; field_differences?: Record<string, unknown> }[]; warnings: string[] };
const props = defineProps<{ api: AxiosInstance; runId?: string }>();
const profiles = ref<{ id: string; label: string; strategy: string }[]>([]);
const activeProfile = ref('');
const sessions = ref<SessionSummary[]>([]);
const selected = ref<Session>();
const comparison = ref<Comparison>();
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
    <div v-if="selected" class="box"><h4>Phiên {{selected.id.slice(0,10)}} · {{selected.status}}</h4><p>{{selected.paper_trades?.length ?? selected.trade_count ?? 0}} lệnh paper được quan sát · {{selected.gaps?.length ?? 0}} khoảng thiếu quan sát. Tín hiệu không lưu được được đánh dấu chưa quan sát.</p><p v-for="warning in selected.warnings" :key="warning" class="hint">{{warning}}</p><div class="row"><button :disabled="busy || selected.status!=='observing'" @click="capture">Chụp bằng chứng hiện tại</button><button :disabled="busy || selected.status!=='observing'" @click="close">Đóng phiên quan sát</button><button :disabled="busy || selected.status!=='closed'" @click="backtestSession">Backtest cùng phiên bằng engine gốc</button></div><label>ID backtest cùng hồ sơ và cùng khoảng<input v-model="runIdInput" :placeholder="runId || 'Chọn hồ sơ backtest đã lưu'"></label><button :disabled="busy || selected.status!=='closed' || !(runIdInput || runId)" @click="compare">So sánh với backtest</button></div>
    <div v-if="comparison" class="box"><h4>Kết quả: {{comparison.status}}</h4><p>Khớp {{comparison.counts.matched}} · Khác {{comparison.counts.different}} · Chưa đủ bằng chứng {{comparison.counts.insufficient}}.</p><p v-for="warning in comparison.warnings" :key="warning" class="hint">{{warning}}</p><div class="table-wrap" v-if="comparison.trades.length"><table><thead><tr><th>Lệnh paper</th><th>Trạng thái</th><th>Lý do</th><th>Sai khác</th></tr></thead><tbody><tr v-for="(trade, index) in comparison.trades" :key="index"><td>{{trade.paper_trade_id ?? '—'}}</td><td>{{trade.status}}</td><td>{{trade.reasons?.join('; ') || '—'}}</td><td><pre>{{JSON.stringify(trade.field_differences ?? {}, null, 2)}}</pre></td></tr></tbody></table></div></div>
  </article>
</template>

<style scoped>
.reconcile{margin-top:24px;line-height:1.5}.reconcile p{color:var(--fg-2)}.row{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.row h3{margin-right:auto}.box{border:1px solid var(--line);border-radius:10px;padding:16px;margin:14px 0}button{border:1px solid var(--line-2);background:var(--bg-2);color:var(--fg);padding:8px 12px;border-radius:7px;cursor:pointer}button:disabled{opacity:.5}input{display:block;width:min(450px,100%);margin:8px 0 14px;padding:8px;background:var(--bg);color:var(--fg);border:1px solid var(--line-2);border-radius:6px}label{display:block}.sessions{display:flex;gap:8px;overflow:auto}.sessions button{min-width:220px;text-align:left;display:grid;gap:5px}.sessions button.active{border-color:var(--accent)}.sessions span{font-size:11px;color:var(--fg-2)}.error{color:#ffb4b4}.hint{padding:9px;background:var(--bg-2)}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:8px;text-align:left;border-bottom:1px solid var(--line)}pre{white-space:pre-wrap;max-width:400px}
</style>
