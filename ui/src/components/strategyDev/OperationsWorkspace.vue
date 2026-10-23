<script setup lang="ts">
import { onMounted, ref } from 'vue';
import type { AxiosInstance } from 'axios';

type Job = { id: string; strategy?: string; status: string; created_at?: string; finished_at?: string; error?: string };
type Operations = { checked_at: string; engine: string; market: { pair: string; type: string; latest_utc: string | null; age_hours: number | null }[]; storage: { research: { files: number; bytes: number }; data: { files: number; bytes: number } }; native_flags: { analysis_running: boolean; download_running: boolean }; jobs: Record<string, Job[]>; note: string };
const props = defineProps<{ api: AxiosInstance }>();
const snapshot = ref<Operations>(), error = ref(''), busy = ref(false);
function message(e: unknown) { const x = e as { response?: { data?: { detail?: unknown } }; message?: string }; return String(x.response?.data?.detail ?? x.message ?? e); }
async function refresh() { busy.value = true; error.value = ''; try { snapshot.value = (await props.api.get('/studio/operations')).data; } catch (e) { error.value = message(e); } finally { busy.value = false; } }
function megabytes(bytes: number) { return (bytes / 1048576).toFixed(1) + ' MB'; }
onMounted(() => void refresh());
</script>

<template>
  <div class="operations"><div class="row"><h3>Tình trạng nghiên cứu</h3><button :disabled="busy" @click="refresh">Tải lại ảnh chụp</button></div><p v-if="error" class="error" role="alert">{{error}}</p><template v-if="snapshot"><p>Đọc lúc {{new Date(snapshot.checked_at).toLocaleString('vi-VN')}} · {{snapshot.engine}}. {{snapshot.note}}</p><div class="cards"><div><small>Dữ liệu thị trường</small><b>{{megabytes(snapshot.storage.data.bytes)}}</b><span>{{snapshot.storage.data.files}} tệp</span></div><div><small>Hồ sơ nghiên cứu</small><b>{{megabytes(snapshot.storage.research.bytes)}}</b><span>{{snapshot.storage.research.files}} tệp</span></div><div><small>Engine nghiên cứu</small><b>{{snapshot.native_flags.analysis_running?'Đang xử lý':'Chưa có tác vụ active'}}</b><span>{{snapshot.native_flags.download_running?'Đang tải dữ liệu':'Không có tải dữ liệu active'}}</span></div></div><h4>Dữ liệu gần nhất trên máy</h4><div class="table-wrap"><table><thead><tr><th>Cặp</th><th>Loại</th><th>Mốc cuối UTC</th><th>Tuổi</th></tr></thead><tbody><tr v-for="item in snapshot.market" :key="item.pair+item.type"><td>{{item.pair}}</td><td>{{item.type}}</td><td>{{item.latest_utc || 'Chưa có'}}</td><td>{{(item.age_hours===null || item.age_hours===undefined)?'—':item.age_hours.toFixed(1)+' giờ'}}</td></tr></tbody></table></div><h4>Tác vụ đã ghi</h4><div v-for="(jobs, group) in snapshot.jobs" :key="group" class="group"><b>{{group}}</b><p v-if="!jobs.length">Chưa có tác vụ.</p><div v-for="job in jobs.slice(0,8)" :key="job.id" class="job"><span>{{job.id?.slice(0,10)}}</span><span>{{job.strategy || '—'}}</span><strong>{{job.status}}</strong><span>{{job.error || ''}}</span></div></div></template>
  </div>
</template>

<style scoped>
.operations{border:1px solid var(--line);background:var(--bg-1);border-radius:10px;padding:18px;margin-bottom:20px;line-height:1.5}.operations p{color:var(--fg-2)}.row{display:flex;align-items:center;gap:12px}.row h3{margin-right:auto}button{padding:8px 12px;color:var(--fg);background:var(--bg-2);border:1px solid var(--line-2);border-radius:7px;cursor:pointer}button:disabled{opacity:.5}.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.cards>div{display:flex;flex-direction:column;gap:7px;border:1px solid var(--line);border-radius:8px;padding:12px}.cards small,.cards span{color:var(--fg-2)}.cards b{font-size:18px}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:7px;text-align:left;border-bottom:1px solid var(--line)}.group{border-top:1px solid var(--line);padding:10px 0}.job{display:grid;grid-template-columns:100px 1fr 110px 2fr;gap:8px;font-size:12px;padding:6px}.error{color:#ffb4b4}@media(max-width:700px){.cards{grid-template-columns:1fr}.job{grid-template-columns:1fr 1fr}}
</style>
