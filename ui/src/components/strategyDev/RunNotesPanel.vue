<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import type { AxiosInstance } from 'axios';

type Note = { run_id: string; label: string; tags: string[]; notes: string; pinned_baseline: boolean; note_revision: string; verification?: string };
type Compare = { comparable: boolean; differences: Record<string, unknown[]>; missing_fields: string[]; protocol_hash?: string; runs: { run_id: string; source_revision: string; summary?: Record<string, unknown> }[] };
const props = defineProps<{ api: AxiosInstance; runId: string; alternatives: { id: string; strategy: string; status: string }[]; strategy: string }>();
const note = ref<Note>();
const label = ref(''), tags = ref(''), body = ref(''), pinned = ref(false), compareId = ref('');
const comparison = ref<Compare>();
const busy = ref(false), error = ref(''), messageText = ref('');
function message(e: unknown) { const x = e as { response?: { data?: { detail?: unknown } }; message?: string }; return String(x.response?.data?.detail ?? x.message ?? e); }
async function load() { if (!props.runId) return; try { note.value = (await props.api.get('/studio/run-notes/' + props.runId)).data; label.value = note.value?.label ?? ''; tags.value = note.value?.tags.join(', ') ?? ''; body.value = note.value?.notes ?? ''; pinned.value = note.value?.pinned_baseline ?? false; } catch (e) { error.value = message(e); } }
async function save() { if (!note.value) return; busy.value = true; error.value = ''; messageText.value = ''; try { note.value = (await props.api.put('/studio/run-notes/' + props.runId, { expected_note_revision: note.value.note_revision, label: label.value, tags: tags.value.split(',').map(x=>x.trim()).filter(Boolean), notes: body.value, pinned_baseline: pinned.value })).data; messageText.value = 'Đã lưu nhãn và ghi chú riêng của hồ sơ. Gói kết quả native không bị sửa.'; } catch (e) { error.value = message(e); } finally { busy.value = false; } }
async function compare() { if (!compareId.value) return; busy.value = true; error.value = ''; try { comparison.value = (await props.api.post('/studio/run-notes/compare', { run_ids: [props.runId, compareId.value] })).data; } catch (e) { error.value = message(e); } finally { busy.value = false; } }
watch(() => props.runId, () => { note.value = undefined; comparison.value = undefined; void load(); });
onMounted(() => void load());
</script>

<template>
  <div class="notes"><h3>Ghi chú thí nghiệm</h3><p>Nhãn và baseline chỉ giúp tổ chức nghiên cứu; không sửa dữ liệu, kết quả hay hồ sơ paper.</p><p v-if="error" class="error" role="alert">{{error}}</p><p v-if="messageText" role="status">{{messageText}}</p><template v-if="note"><div class="grid"><label>Nhãn<input v-model="label" maxlength="70"></label><label>Nhãn tìm kiếm<input v-model="tags" placeholder="baseline, short, kiểm tra" maxlength="300"></label></div><label>Ghi chú<textarea v-model="body" rows="3" maxlength="4000" /></label><label class="pin"><input v-model="pinned" type="checkbox"> Ghim làm baseline tham khảo</label><button :disabled="busy" @click="save">Lưu ghi chú</button></template>
    <div class="compare"><h4>So sánh đúng giao thức</h4><p>Chỉ kết luận so sánh được khi các bản chạy có cùng khoảng, dữ liệu, phí, vốn, tham số thực thi và engine. Khác giao thức sẽ được liệt kê.</p><select v-model="compareId"><option value="">Chọn hồ sơ khác</option><option v-for="run in alternatives.filter(x=>x.id!==runId&&x.status==='success'&&x.strategy===strategy)" :key="run.id" :value="run.id">{{run.id.slice(0,10)}}</option></select><button :disabled="busy || !compareId" @click="compare">Kiểm tra và so sánh</button><div v-if="comparison" class="result"><b>{{comparison.comparable?'Cùng giao thức':'Chưa so sánh trực tiếp được'}}</b><p v-if="comparison.protocol_hash">Protocol {{comparison.protocol_hash.slice(0,12)}}</p><p v-for="[field, values] in Object.entries(comparison.differences)" :key="field">Khác {{field}}: {{JSON.stringify(values)}}</p><p v-for="field in comparison.missing_fields" :key="field">Thiếu bằng chứng: {{field}}</p><div v-if="comparison.comparable" class="grid"><div v-for="run in comparison.runs" :key="run.run_id"><b>{{run.run_id.slice(0,10)}}</b><p>{{run.summary?.total_trades ?? '—'}} lệnh · {{run.summary?.profit_total_abs ?? '—'}} USDT</p></div></div></div></div>
  </div>
</template>

<style scoped>
.notes{border-top:1px solid var(--line);margin-top:18px;padding-top:18px;line-height:1.5}.notes p{color:var(--fg-2)}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.notes label{display:block;margin:10px 0;font-size:12px}.notes input,.notes textarea,.notes select{display:block;width:100%;padding:9px;margin-top:5px;color:var(--fg);background:var(--bg);border:1px solid var(--line-2);border-radius:6px}.notes .pin{display:flex;align-items:center;gap:8px}.pin input{width:auto;margin:0}button{padding:9px 12px;margin:6px 8px 6px 0;border:1px solid var(--line-2);border-radius:7px;color:var(--fg);background:var(--bg-2);cursor:pointer}button:disabled{opacity:.5}.compare{margin-top:18px}.compare select{max-width:300px}.result{border:1px solid var(--line);border-radius:8px;padding:13px;margin-top:10px}.error{color:#ffb4b4}@media(max-width:600px){.grid{grid-template-columns:1fr}}
</style>
