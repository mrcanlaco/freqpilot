<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import type { AxiosInstance } from 'axios';
import type { BacktestHistoryEntry } from '@/types';
import CodeEditor from '@/components/strategyDev/CodeEditor.vue';
import PaperWorkspace from '@/components/strategyDev/PaperWorkspace.vue';
import ParameterPresets from '@/components/strategyDev/ParameterPresets.vue';
import ResearchCheckReport from '@/components/strategyDev/ResearchCheckReport.vue';
import ReplayBacktest from '@/components/strategyDev/ReplayBacktest.vue';
import ResearchConnectionNotice from '@/components/strategyDev/ResearchConnectionNotice.vue';
import OptimizationWorkspace from '@/components/strategyDev/OptimizationWorkspace.vue';
import DataQualityWorkspace from '@/components/strategyDev/DataQualityWorkspace.vue';
import WalkForwardWorkspace from '@/components/strategyDev/WalkForwardWorkspace.vue';
import SensitivityWorkspace from '@/components/strategyDev/SensitivityWorkspace.vue';
import SeedExperimentsWorkspace from '@/components/strategyDev/SeedExperimentsWorkspace.vue';
import RunNotesPanel from '@/components/strategyDev/RunNotesPanel.vue';
import OperationsWorkspace from '@/components/strategyDev/OperationsWorkspace.vue';
import MatrixWorkspace from '@/components/strategyDev/MatrixWorkspace.vue';
import PaperReconcileWorkspace from '@/components/strategyDev/PaperReconcileWorkspace.vue';
import { discoverResearchConnection } from '@/utils/researchConnection';
import { useResearchBootstrap } from '@/composables/useResearchBootstrap';
import type { ResearchCheck } from '@/utils/researchChecks';
import StrategyLibrary from '@/components/strategyDev/StrategyLibrary.vue';
import DiffViewer from '@/components/strategyDev/DiffViewer.vue';
import { buildEvidenceCodexPrompt, buildResearchDossierMarkdown, buildTradeAnalytics, filterAndSortStrategies, formatLibraryRunSummary, latestLibraryRuns, STUDIO_UI_TEXT, type LibraryStrategy, type LibraryRun, type StrategyPreset, type StrategySortKey, type StudioLocale } from '@/utils/strategyLibrary';
import EquityCurveChart from '@/components/strategyDev/EquityCurveChart.vue';
import UnderwaterChart from '@/components/strategyDev/UnderwaterChart.vue';
import MonthlyReturnsHeatmap from '@/components/strategyDev/MonthlyReturnsHeatmap.vue';
import ExitReasonChart from '@/components/strategyDev/ExitReasonChart.vue';
import HourlyPatternChart from '@/components/strategyDev/HourlyPatternChart.vue';
import WeekdayPatternChart from '@/components/strategyDev/WeekdayPatternChart.vue';
import BacktestSummaryCards from '@/components/strategyDev/BacktestSummaryCards.vue';
import BacktestResultAnalysis from '@/components/ftbot/BacktestResultAnalysis.vue';
import BacktestResultComparison from '@/components/ftbot/BacktestResultComparison.vue';
import BacktestResultChart from '@/components/ftbot/BacktestResultChart.vue';
import BacktestGraphs from '@/components/ftbot/BacktestGraphs.vue';
import { useApi } from '@/composables/api';
import { useLoginInfo } from '@/composables/loginInfo';
import { useBotStore } from '@/stores/ftbotwrapper';
import { formatBacktestProfitFactor } from '@/utils/backtestMetrics';

type Item = LibraryStrategy;
type DataRow = { pair: string; timeframe: string; type: string; rows: number; start: string | null; end: string | null; duplicates: number; sorted: boolean; error?: string };
type Version = { id: string; saved_at: number };
type FrozenRun = LibraryRun & { filename?:string; native_run_id?:string; artifact_sha256?:string; input_files:number; input_bytes:number; error?:string; optimization?:{id:string;epoch:number;mode:'train'|'oos';train_timerange?:string;oos_timerange?:string}; replay_of?:{id:string;artifact_sha256:string}; replay_comparison?:{status:'matched'|'different'|'unavailable';source_id:string;source_trades?:number;replayed_trades?:number;different_trades?:number;different_metrics?:string[]} };
const router=useRouter(); const route=useRoute(); const bots=useBotStore();
const paperView=computed(()=>route.name==='research-paper'||route.query.paper==='active');
function openLibrary(){libraryOpen.value=true;void router.push('/studio');}
const items=ref<Item[]>([]), query=ref(''), sidebarFilter=ref<'all'|'favorite'|'archived'|'profitable'|'short'>('all'), sidebarSort=ref<StrategySortKey>('evidence'), selected=ref(''), tab=ref('idea'), studioLang=ref<StudioLocale>('vi');
const uiText=computed(()=>STUDIO_UI_TEXT[studioLang.value]??STUDIO_UI_TEXT.vi);
const preset=ref<StrategyPreset>(),parameterBusy=ref(false);
const libraryOpen=ref(true), sidebarOpen=ref(true), sidebarWidth=ref(275), runSplitEditor=ref(false), tagsText=ref(''), favorite=ref(false), versionPreview=ref('');
function startSidebarResize(event:MouseEvent){
  event.preventDefault();
  const startX=event.clientX;
  const startW=sidebarWidth.value;
  function onMove(ev:MouseEvent){sidebarWidth.value=Math.max(220,Math.min(440,startW+(ev.clientX-startX)));}
  function onUp(){document.removeEventListener('mousemove',onMove);document.removeEventListener('mouseup',onUp);document.body.style.cursor='';document.body.style.userSelect='';}
  document.body.style.cursor='col-resize';
  document.body.style.userSelect='none';
  document.addEventListener('mousemove',onMove);
  document.addEventListener('mouseup',onUp);
}
watch(()=>route.name,(name)=>{if(name==='research-data'){libraryOpen.value=false;tab.value='data';}else if(name==='research-jobs'){libraryOpen.value=false;tab.value='walk';}},{immediate:true});
const tabs=computed(()=>uiText.value.tabs);
const code=ref(''), original=ref(''), revision=ref(''), idea=ref(''), notes=ref('');
function draftKey(name:string){return 'freqpilot.strategy-draft.'+name;}
watch([selected,code,revision],()=>{if(!selected.value||!revision.value)return;try{if(code.value===original.value)localStorage.removeItem(draftKey(selected.value));else localStorage.setItem(draftKey(selected.value),JSON.stringify({revision:revision.value,code:code.value,updated_at:Date.now()}));}catch{/* The editor still retains the in-memory draft if browser storage is unavailable. */}});
function warnBeforeUnload(event:BeforeUnloadEvent){if(dirty.value||researchDirty.value){event.preventDefault();event.returnValue='';}}
const message=ref(''), failure=ref(false), working=ref(false), api=ref<AxiosInstance>();
type CheckRun=ResearchCheck;
const checks=ref<CheckRun[]>([]), minSignals=ref(10), targetSignals=ref(20);
const checking=computed(()=>checks.value.some(c=>['pending','running'].includes(c.status)));
const optimizationRunning=ref(false), optimizationBusy=ref(false);
const importFileBase64=ref(''), importFileName=ref(''), importExpectedSha=ref(''), importInstallMissing=ref(true);
const optimizationSettings=computed(()=>({timerange:start.value.replaceAll('-','')+'-'+end.value.replaceAll('-',''),timeframe:interval.value||selectedItem.value?.timeframe,timeframe_detail:detail.value,dry_run_wallet:wallet.value,max_open_trades:maxTrades.value,stake_amount:String(stake.value),enable_protections:false}));
let optimizationReading=false, workspaceMounted=true, activityTick=0;
async function readOptimizationActivity(){
  if(!api.value||optimizationReading)return;
  optimizationReading=true;
  try{const response=await api.value.get('/studio/optimizations');if(workspaceMounted)optimizationRunning.value=(response.data.optimizations??[]).some((job:{status:string;orphan_process_alive?:boolean})=>['prepared','running','cancelling'].includes(job.status)||job.orphan_process_alive===true);if(optimizationRunning.value&&active.value)active.value.backtestRunning=false;}
  catch{/* Older services may not yet expose optimization; commands still enforce server activity. */}
  finally{optimizationReading=false;}
}
const versions=ref<Version[]>([]), versionId=ref(''), newOpen=ref(false), newName=ref(''), sourceName=ref('');
const data=ref<{files: DataRow[]; fee?: number; wallet?: number; stake?:number; max_open_trades?:number; pairs:string[]}>();
const start=ref('2026-09-18'), end=ref(''), wallet=ref(1000), stake=ref(100), maxTrades=ref(2), detail=ref('1m');
const timerange=computed(()=>start.value.replaceAll('-','')+'-'+end.value.replaceAll('-',''));
const interval=ref<string>(), manifestId=ref(''), resultMode=ref('summary');
const runs=ref<FrozenRun[]>([]), sourcePreview=ref(''), artifactValid=ref<boolean|null>(null);
const latestRunsMap=computed(()=>latestLibraryRuns(runs.value));
const frozenRun=computed(()=>runs.value.find(r=>r.filename===active.value?.selectedBacktestMetadata?.filename));
const pendingArtifact=computed(()=>runs.value.some(r=>r.status==='running'));
const recentRuns=computed(()=>runs.value.filter(r=>r.strategy===selected.value).slice(0,5));
const runStatus:Record<string,string>={prepared:'Đã chuẩn bị',running:'Đang xử lý',success:'Đã lưu đầy đủ',failed:'Không hoàn tất',interrupted:'Bị gián đoạn'};
const comparisonIds=ref<string[]>([]);
const comparison=computed(()=>Object.fromEntries(Object.entries(active.value?.backtestHistory??{}).filter(([,r])=>comparisonIds.value.includes(String(r.metadata.run_id??'')))));
let poll: ReturnType<typeof setInterval>|undefined;
const selectedItem=computed(()=>items.value.find(x=>x.name===selected.value));
const filtered=computed(()=>filterAndSortStrategies(items.value,latestRunsMap.value,{
  query:query.value,
  favorites:sidebarFilter.value==='favorite',
  status:sidebarFilter.value==='archived'?'archived':'all',
  outcome:sidebarFilter.value==='profitable'?'profitable':'all',
  direction:sidebarFilter.value==='short'?'short':'all',
  sort:sidebarSort.value,
}));
const selectedLatestRun=computed(()=>latestRunsMap.value.get(selected.value));
const dataBounds=computed(()=>{
  const tf=interval.value||selectedItem.value?.timeframe;
  const candidates=(data.value?.files??[]).filter(f=>f.type==='futures'&&f.start&&f.end&&(!tf||f.timeframe===tf));
  const list=candidates.length?candidates:(data.value?.files??[]).filter(f=>f.type==='futures'&&f.start&&f.end);
  if(!list.length)return null;
  const starts=list.map(f=>f.start!.slice(0,10)).sort();
  const ends=list.map(f=>f.end!.slice(0,10)).sort();
  return {start:starts[starts.length-1]!,end:ends[0]!};
});
function applyDatePreset(days?:number){
  const bounds=dataBounds.value;
  const maxEnd=bounds?.end||'2026-10-22';
  const minStart=bounds?.start||'2026-09-18';
  end.value=maxEnd;
  if(!days){start.value=minStart;return;}
  const endMs=Date.parse(maxEnd+'T00:00:00Z');
  if(!Number.isFinite(endMs)){start.value=minStart;return;}
  const candidate=new Date(endMs-days*86_400_000).toISOString().slice(0,10);
  start.value=candidate<minStart?minStart:candidate;
}
function runForHistory(entry:BacktestHistoryEntry){
  return runs.value.find(r=>r.filename===entry.filename&&r.strategy===entry.strategy);
}
function pnlClass(n:number|undefined){
  if(n==null||!Number.isFinite(n)||n===0)return '';
  return n>0?'pos':'neg';
}
const dirty=computed(()=>code.value!==original.value);
const researchDirty=computed(()=>!!selected.value&&(idea.value!==(selectedItem.value?.research?.idea??'')||notes.value!==(selectedItem.value?.research?.notes??'')||tagsText.value!==(selectedItem.value?.research?.tags??[]).join(', ')||favorite.value!==!!selectedItem.value?.research?.is_favorite));
type RecommendedAction = { label: string; actionLabel: string; targetTab?: string; run?: () => void; tone: 'warn' | 'info' | 'ok' };
const recommendedAction=computed<RecommendedAction>(()=>{
  if(dirty.value)return {label:'Mã nguồn có thay đổi chưa lưu',actionLabel:'Mở Mã & lưu phiên bản →',targetTab:'code',tone:'warn'};
  if(!end.value)return {label:'Chưa chọn ngày kết thúc cho khoảng chạy thử',actionLabel:'Đặt theo dữ liệu sẵn có',run:()=>applyDatePreset(),tone:'info'};
  if(!selectedLatestRun.value)return {label:'Chiến lược chưa có gói backtest đóng băng',actionLabel:'Đến bước 04 · Backtest →',targetTab:'run',tone:'info'};
  if(selectedLatestRun.value.revision!==revision.value)return {label:'Mã hiện tại đã thay đổi so với gói backtest gần nhất',actionLabel:'Chạy lại Backtest cho mã mới →',targetTab:'run',tone:'warn'};
  if(!checks.value.length)return {label:'Đã có gói backtest khớp mã · Chưa kiểm định Lookahead / Recursive',actionLabel:'Đến bước 06 · Kiểm định →',targetTab:'checks',tone:'info'};
  return {label:'Đã có gói backtest khớp mã và báo cáo kiểm định',actionLabel:'Xem Kết quả / Chuẩn bị Paper →',targetTab:'results',tone:'ok'};
});
function triggerRecommendedAction(){
  const act=recommendedAction.value;
  if(act.run)act.run();
  else if(act.targetTab)tab.value=act.targetTab;
}
function discardDraft(){
  if(!dirty.value)return;
  if(!window.confirm('Bỏ các thay đổi chưa lưu trong editor và quay về bản đã lưu?'))return;
  code.value=original.value;
  try{localStorage.removeItem(draftKey(selected.value));}catch{/* ignore storage errors */}
  notify('Đã bỏ bản nháp và khôi phục mã đã lưu.');
}
function handleWorkspaceKeydown(event:KeyboardEvent){
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='b'){
    const target=event.target;
    if(target instanceof HTMLElement&&(['INPUT','TEXTAREA','SELECT'].includes(target.tagName)||target.isContentEditable||!!target.closest('.monaco-editor')))return;
    event.preventDefault();
    sidebarOpen.value=!sidebarOpen.value;
  }
}
const active=shallowRef<typeof bots.activeBot>();
let researchBot: typeof bots.activeBot | undefined;
const results=computed(()=>active.value?.backtestHistoryList.filter(x=>x.strategy===selected.value)??[]);
const result=computed(()=>active.value?.selectedBacktestResult?.strategy_name===selected.value?active.value.selectedBacktestResult:undefined);
const running=computed(()=>!optimizationRunning.value&&(active.value?.backtestRunning??false));
const realizedEquity=computed(()=>{
  if(!result.value)return [];
  let balance=result.value.starting_balance;
  const points=[{date:result.value.backtest_start,balance}];
  for(const trade of [...result.value.trades].sort((a,b)=>Date.parse(a.close_date)-Date.parse(b.close_date))){const profit=trade.profit_abs;if(typeof profit!=='number'||!Number.isFinite(profit))return [];balance+=profit;points.push({date:trade.close_date,balance});}
  return points;
});
const tradeAnalytics=computed(()=>buildTradeAnalytics((result.value?.trades??[]) as unknown as Record<string,unknown>[],result.value?.starting_balance,{start:result.value?.backtest_start,end:result.value?.backtest_end}));
watch(tab,(nextTab)=>{
  if(nextTab==='results'&&!result.value&&results.value.length&&!working.value){
    const entry=latestResearchEntry(selected.value)??results.value[0];
    if(entry)void loadResult(entry);
  }
});
function notify(s:string,error=false){message.value=s;failure.value=error;}
function errorMessage(e:unknown){const err=e as {response?:{data?:{detail?:unknown}},message?:string};return String(err.response?.data?.detail??err.message??e);}
async function guard(fn:()=>Promise<void>){working.value=true;try{await fn();}catch(e){notify(errorMessage(e),true);}finally{working.value=false;}}
async function loadRuns(){if(api.value)runs.value=(await api.value.get('/studio/runs')).data.runs;}
function latestResearchEntry(name:string){const frozen=runs.value.filter(r=>r.strategy===name&&r.status==='success').sort((a,b)=>Date.parse(b.created_at)-Date.parse(a.created_at))[0];return active.value?.backtestHistoryList.find(x=>x.strategy===name&&x.filename===frozen?.filename)??active.value?.backtestHistoryList.find(x=>x.strategy===name);}
async function refresh(){if(!api.value)return;const response=await api.value.get('/studio/library');items.value=response.data.strategies;await active.value?.getBacktestHistory();await loadRuns();}
async function select(name:string){if(parameterBusy.value||optimizationBusy.value){notify('Chờ thao tác tham số hoặc tối ưu hoàn tất trước khi đổi chiến lược.',true);return false;}if((dirty.value||researchDirty.value)&&!window.confirm('Bỏ thay đổi mã hoặc nghiên cứu chưa lưu?'))return false;let opened=false;await guard(async()=>{
  const response=await api.value!.get('/local-strategies/'+name);selected.value=name;code.value=original.value=response.data.content;revision.value=response.data.revision;
  try{const saved=JSON.parse(localStorage.getItem(draftKey(name))??'null') as {revision?:string;code?:string;updated_at?:number}|null;if(saved?.revision===revision.value&&saved.code&&saved.code!==original.value&&window.confirm('Có bản nháp mã chưa lưu của '+name+' từ '+new Date(saved.updated_at??0).toLocaleString('vi-VN')+'. Khôi phục vào editor?'))code.value=saved.code;}catch{/* Invalid or inaccessible browser storage must not block the library. */}
  const meta=await api.value!.get('/studio/research/'+name);idea.value=meta.data.idea;notes.value=meta.data.notes;tagsText.value=meta.data.tags.join(', ');favorite.value=!!meta.data.is_favorite;
  versions.value=(await api.value!.get('/studio/versions/'+name)).data.versions;
  checks.value=(await api.value!.get('/studio/checks/'+name)).data.checks;
  preset.value=undefined;versionId.value='';versionPreview.value='';manifestId.value='';sourcePreview.value='';artifactValid.value=null;interval.value=selectedItem.value?.timeframe;
  const latest=latestResearchEntry(name);if(latest)await active.value?.getBacktestHistoryResult(latest);
  notify('Đang nghiên cứu '+name+'. Lưu mã không đổi bot paper đang chạy.');opened=true;
});return opened;}
async function openStrategy(name:string,nextTab='idea'){if(await select(name)){libraryOpen.value=false;tab.value=nextTab;}}
async function toggleFavorite(name:string,value:boolean){await guard(async()=>{await api.value!.put('/studio/research/'+name,{is_favorite:value});if(selected.value===name)favorite.value=value;await refresh();notify(value?'Đã đánh dấu yêu thích '+name+'.':'Đã bỏ yêu thích '+name+'.');});}
async function save(){if(!selected.value||selectedItem.value?.protected)return;await guard(async()=>{
  const response=await api.value!.put('/local-strategies/'+selected.value,{content:code.value,revision:revision.value});original.value=code.value;revision.value=response.data.revision;await refresh();versions.value=(await api.value!.get('/studio/versions/'+selected.value)).data.versions;notify('Đã lưu mã, kiểm tra cú pháp và tạo bản sao dự phòng.');
});}
async function saveResearch(){await guard(async()=>{const response=await api.value!.put('/studio/research/'+selected.value,{idea:idea.value,notes:notes.value,tags:tagsText.value.split(','),is_favorite:favorite.value});tagsText.value=response.data.tags.join(', ');await refresh();notify('Đã lưu ý tưởng, ghi chú, nhãn và yêu thích trên máy.');});}
function createDialog(copy=false){if(parameterBusy.value)return;failure.value=false;sourceName.value=copy?selected.value:'';newName.value=copy?selected.value+'Research':'';newOpen.value=true;}
async function create(){await guard(async()=>{const response=await api.value!.post('/local-strategies',{name:newName.value.trim(),source:sourceName.value||null});newOpen.value=false;await refresh();await select(response.data.name);libraryOpen.value=false;tab.value='code';notify('Đã tạo '+response.data.name+(sourceName.value?'. Đã sao chép mã; cần backtest riêng.':'. Mẫu mới chưa có tín hiệu vào lệnh.'));});}
async function compareVersion(){if(!versionId.value)return;await guard(async()=>{versionPreview.value=(await api.value!.get('/studio/versions/'+selected.value+'/'+versionId.value)).data.content;notify('Đang so sánh bản cũ với mã trong editor. Chưa khôi phục hoặc lưu mã.');});}
async function restorePreview(){if(!versionId.value)return;if(dirty.value&&!window.confirm('Thay mã chưa lưu bằng bản xem trước?'))return;await guard(async()=>{const response=await api.value!.get('/studio/versions/'+selected.value+'/'+versionId.value);code.value=response.data.content;tab.value='code';notify('Đang xem mã cũ. Nhấn Lưu nếu muốn khôi phục; bản hiện tại sẽ được sao lưu.');});}
async function copyPrompt(){const prompt=buildEvidenceCodexPrompt({strategy:selected.value,revision:revision.value,timeframe:interval.value||selectedItem.value?.timeframe,idea:idea.value,notes:notes.value,latestRun:selectedLatestRun.value,latestCheck:checks.value[0]});try{await navigator.clipboard.writeText(prompt);notify('Đã sao chép yêu cầu kèm bằng chứng hiện tại. Dán vào cuộc trò chuyện Codex này để phát triển từ ý tưởng.');}catch{notify('Trình duyệt không cho sao chép. Hãy dùng nội dung ý tưởng trong cuộc trò chuyện Codex.',true);}}
async function run(){if(!selectedItem.value||dirty.value||running.value||checking.value||parameterBusy.value||optimizationRunning.value||optimizationBusy.value)return;await guard(async()=>{
  if(preset.value&&(preset.value.revision!==revision.value||preset.value.valid===false))throw Error('Bộ tham số không khớp mã hiện tại. Chọn bộ hợp lệ trước khi chạy.');
  if(!start.value||wallet.value<=0||stake.value<=0||maxTrades.value<1)throw Error('Kiểm tra ngày, vốn, số tiền mỗi lệnh và số lệnh tối đa.');
  if(!end.value||end.value<=start.value)throw Error('Chọn ngày kết thúc sau ngày bắt đầu. Khoảng backtest phải đóng để kiểm tra nến, mark price và funding đầy đủ.');
  const settings={timerange:start.value.replaceAll('-','')+'-'+end.value.replaceAll('-',''),timeframe:interval.value||selectedItem.value!.timeframe,timeframe_detail:detail.value,dry_run_wallet:wallet.value,max_open_trades:maxTrades.value,stake_amount:String(stake.value),enable_protections:false};
  const files=data.value?.files??[];for(const pair of data.value?.pairs??[]){if(!files.some(x=>x.pair===pair&&x.timeframe===settings.timeframe&&x.type==='futures'))throw Error('Chưa có nến '+settings.timeframe+' cho '+pair+'. Hãy tải dữ liệu trước.');if(!files.some(x=>x.pair===pair&&x.type==='funding_rate'))throw Error('Thiếu funding cho '+pair+'. Không chạy với funding bằng 0.');}
  const inspected=(await api.value!.get('/studio/data-quality',{params:{timerange:settings.timerange,timeframe:settings.timeframe,detail_timeframe:detail.value,warmup_candles:selectedItem.value?.startup_candle_count??200,verify_funding:false}})).data as {status:string;issues?:{message:string}[]};
  if(['missing','invalid'].includes(inspected.status))throw Error('Dữ liệu chưa đủ để backtest: '+(inspected.issues?.[0]?.message??inspected.status)+'. Mở bước Dữ liệu để xem chi tiết và tải bù.');
  // The adapter freezes inputs and delegates execution and reports to the official API.
  const response=await api.value!.post('/studio/runs',{strategy:selected.value,revision:revision.value,settings,preset_id:preset.value?.id});manifestId.value=response.data.id;
  await loadRuns();active.value!.backtestRunning=true;notify('Đã đóng băng mã và dữ liệu, bắt đầu backtest bằng engine chính thức. Hồ sơ được lưu cả khi rời trang.');
});}
async function loadResult(entry:BacktestHistoryEntry){await guard(async()=>{sourcePreview.value='';artifactValid.value=null;await active.value?.getBacktestHistoryResult(entry);tab.value='results';resultMode.value='summary';});}
async function openFrozenRun(run:FrozenRun){await active.value?.getBacktestHistory();const entry=active.value?.backtestHistoryList.find(x=>x.filename===run.filename&&x.strategy===run.strategy);if(entry)await loadResult(entry);else notify(run.error??'Kết quả chưa được lưu vào lịch sử native.',true);}
async function verifyArtifact(){if(!frozenRun.value)return;await guard(async()=>{const check=(await api.value!.get('/studio/runs/'+frozenRun.value!.id+'/verify')).data;artifactValid.value=check.valid;notify(check.valid?'Gói mã, dữ liệu và kết quả khớp dấu vân tay đã lưu.':'Gói lưu đã thay đổi hoặc thiếu tệp.',!check.valid);});}
async function previewSource(){if(!frozenRun.value)return;await guard(async()=>{sourcePreview.value=(await api.value!.get('/studio/runs/'+frozenRun.value!.id+'/source')).data.content;});}
async function downloadArtifact(){if(!frozenRun.value)return;await guard(async()=>{const id=frozenRun.value!.id;const response=await api.value!.get('/studio/runs/'+id+'/artifact',{responseType:'blob'});const url=URL.createObjectURL(response.data);const link=document.createElement('a');link.href=url;link.download='freqpilot-'+id+'.zip';link.click();setTimeout(()=>URL.revokeObjectURL(url),30000);notify('Đã tải gói hồ sơ; giữ riêng trên máy vì gói chứa mã chiến lược và dữ liệu.');});}
async function replayStarted(id:string){manifestId.value=id;if(researchBot)researchBot.backtestRunning=true;notify('Đang chạy lại từ gói đã lưu. Mã và biểu mẫu hiện tại không được dùng; kết quả mới sẽ có đối chiếu riêng.');try{await loadRuns();}catch{notify('Engine đã nhận bản chạy lại nhưng chưa tải được hồ sơ mới. Tải lại kết quả để kiểm tra; không gửi lại tự động.',true);}}
async function optimizationBacktestStarted(id:string){manifestId.value=id;if(researchBot)researchBot.backtestRunning=true;notify('Engine đã nhận backtest kiểm tra bộ tham số từ hồ sơ tối ưu. Đầu vào lấy từ bản sao đã lưu, chưa đổi paper.');try{await loadRuns();}catch{notify('Engine đã nhận backtest nhưng chưa đọc được hồ sơ. Tải lại kết quả để kiểm tra; không gửi lại tự động.',true);}}
async function loadChecks(){if(api.value&&selected.value)checks.value=(await api.value.get('/studio/checks/'+selected.value)).data.checks;}
async function startCheck(kind:'lookahead'|'recursive'){if(dirty.value||running.value||checking.value||parameterBusy.value||optimizationRunning.value||optimizationBusy.value)return;await guard(async()=>{
  if(preset.value&&(preset.value.revision!==revision.value||preset.value.valid===false))throw Error('Bộ tham số không khớp mã hiện tại. Chọn lại trước khi kiểm định.');
  await api.value!.post('/studio/checks/'+selected.value+'/start',{kind,preset_id:preset.value?.id,revision:revision.value,timeframe:interval.value||selectedItem.value?.timeframe,timerange:start.value.replaceAll('-','')+'-'+end.value.replaceAll('-',''),minimum_trade_amount:minSignals.value,targeted_trade_amount:targetSignals.value});
  await loadChecks();notify('Đã gửi kiểm định cho API Freqtrade chính thức. Kết quả được lưu khi job kết thúc.');
});}
function onImportFileChange(event:Event){
  const input=event.target as HTMLInputElement|null;
  const file=input?.files?.[0];
  if(!file){importFileBase64.value='';importFileName.value='';return;}
  importFileName.value=file.name;
  const reader=new FileReader();
  reader.onload=()=>{importFileBase64.value=typeof reader.result==='string'?reader.result:'';};
  reader.readAsDataURL(file);
}
async function importArtifactBundle(){
  if(!api.value||!importFileBase64.value||working.value)return;
  await guard(async()=>{
    const response=await api.value!.post('/studio/runs/import',{
      archive_base64:importFileBase64.value,
      expected_sha256:importExpectedSha.value.trim()||null,
      install_strategy_if_missing:importInstallMissing.value,
    });
    const imported=response.data as FrozenRun;
    importFileBase64.value='';importFileName.value='';importExpectedSha.value='';
    await refresh();
    if(imported.strategy&&items.value.some(x=>x.name===imported.strategy)){
      await select(imported.strategy);
    }
    await openFrozenRun(imported);
    notify('Đã xác minh SHA256 và nhập gói hồ sơ '+imported.id.slice(0,10)+' của '+imported.strategy+'.');
  });
}
function currentDossierMarkdown(){
  if(!frozenRun.value)return '';
  return buildResearchDossierMarkdown({
    strategy:selected.value,
    revision:frozenRun.value.revision,
    idea:idea.value,
    notes:notes.value,
    tags:tagsText.value.split(',').map(x=>x.trim()).filter(Boolean),
    run:frozenRun.value,
    checks:checks.value,
    exitReasons:tradeAnalytics.value.exitReasons,
  });
}
function downloadDossier(){
  const md=currentDossierMarkdown();
  if(!md||!frozenRun.value)return;
  const blob=new Blob([md],{type:'text/markdown;charset=utf-8'});
  const url=URL.createObjectURL(blob);
  const link=document.createElement('a');
  link.href=url;
  link.download=`dossier-${selected.value}-${frozenRun.value.id.slice(0,10)}.md`;
  link.click();
  setTimeout(()=>URL.revokeObjectURL(url),30000);
  notify('Đã xuất hồ sơ nghiên cứu Dossier (.md) kèm dấu vân tay SHA256 và hướng dẫn tái lập.');
}
async function copyDossier(){
  const md=currentDossierMarkdown();
  if(!md)return;
  try{await navigator.clipboard.writeText(md);notify('Đã sao chép Dossier nghiên cứu (.md) vào bộ nhớ tạm.');}
  catch{notify('Trình duyệt không cho phép sao chép tự động. Hãy dùng nút Xuất Dossier (.md).',true);}
}
async function compareLatest(names?:string[]){await guard(async()=>{
  await active.value?.getBacktestHistory();
  await loadRuns();
  const latest=(names??items.value.map(x=>x.name)).map(latestResearchEntry).filter((x):x is BacktestHistoryEntry=>!!x);
  comparisonIds.value=latest.map(x=>x.run_id);
  for(const entry of latest)await active.value?.getBacktestHistoryResult(entry);
  libraryOpen.value=false;tab.value='compare';notify('Đã mở '+latest.length+' chiến lược để so sánh. Kiểm tra khoảng ngày và cấu hình của từng lần chạy.');
});}
function pct(n:number|undefined){return n==null?'—':(n*100).toFixed(2)+'%';}
function fmtDate(value:string|null){return value?value.slice(0,16).replace('T',' ')+' UTC':'—';}
async function pollBacktest(){if(!active.value||optimizationRunning.value)return;try{const was=active.value.backtestRunning;await active.value.pollBacktest();if(was&&!active.value.backtestRunning){await refresh();tab.value='results';notify('Backtest đã kết thúc. Xem số lệnh, phí và rủi ro trước khi đánh giá.');}}catch{/* Native API can be idle or still initializing. */}}
async function initialize({isCurrent}:{isCurrent:()=>boolean}){
  if(poll){clearInterval(poll);poll=undefined;}
  const server=await discoverResearchConnection(bots.allBotStores,b=>useApi(useLoginInfo(b.botId),b.botId).api,bots.hasBots?bots.activeBot?.botId:undefined,isCurrent);
  if(!isCurrent())return;
  researchBot=server;active.value=server;
  bots.selectBot(server.botId);api.value=useApi(useLoginInfo(server.botId),server.botId).api;
  const response=await api.value.get('/studio/data');if(!isCurrent())return;
  data.value=response.data;wallet.value=data.value?.wallet??1000;stake.value=Number(data.value?.stake??100);maxTrades.value=data.value?.max_open_trades??2;
  await refresh();if(!isCurrent())return;await readOptimizationActivity();if(!isCurrent())return;await pollBacktest();if(!isCurrent())return;
  if(items.value[0])await select(items.value.find(x=>x.name==='StarterFuturesResearch')?.name??items.value[0].name);
  if(!isCurrent())return;
  poll=setInterval(()=>{if(running.value)void pollBacktest();if(++activityTick%4===0||optimizationRunning.value)void readOptimizationActivity();if(checking.value)void loadChecks().catch(e=>notify(errorMessage(e),true));if(pendingArtifact.value)void loadRuns().then(async()=>{if(!pendingArtifact.value)await active.value?.getBacktestHistory();}).catch(e=>notify(errorMessage(e),true));},1500);
}
const connection=useResearchBootstrap(initialize);
const ready=computed(()=>connection.phase.value==='ready');
onMounted(()=>{window.addEventListener('beforeunload',warnBeforeUnload);window.addEventListener('keydown',handleWorkspaceKeydown);void connection.start();});onUnmounted(()=>{workspaceMounted=false;if(poll)clearInterval(poll);window.removeEventListener('beforeunload',warnBeforeUnload);window.removeEventListener('keydown',handleWorkspaceKeydown);});
</script>

<template>
  <div class="pilot">
    <div class="pilot-heading" :class="{'library-mode':libraryOpen}">
      <nav class="area-nav" aria-label="Khu vực nghiên cứu">
        <button :class="{active:route.name==='studio'&&libraryOpen}" @click="openLibrary">{{uiText.areaLibrary}}</button>
        <button v-if="selected" :class="{active:route.name==='studio'&&!libraryOpen}" @click="libraryOpen=false;router.push('/studio')">Workspace: {{selected}}</button>
        <button :class="{active:route.name==='research-data'}" @click="router.push('/data')">{{uiText.areaData}}</button>
        <button :class="{active:route.name==='research-jobs'}" @click="router.push('/jobs')">{{uiText.areaJobs}}</button>
        <button :class="{active:paperView}" @click="router.push('/paper')">{{uiText.areaPaper}}</button>
        <button @click="router.push('/settings')">{{uiText.areaSettings}}</button>
      </nav>
      <div class="row">
        <select v-model="studioLang" class="studio-lang-select" aria-label="Ngôn ngữ Studio">
          <option value="vi">🇻🇳 VI</option>
          <option value="en">🇬🇧 EN</option>
          <option value="zh">🇨🇳 中文</option>
          <option value="ru">🇷🇺 RU</option>
          <option value="ko">🇰🇷 KO</option>
        </select>
        <button v-if="ready&&api&&!paperView" :disabled="working||running" @click="compareLatest()">{{uiText.compareLibrary}}</button>
        <div class="safe">● 1x Isolated</div>
      </div>
    </div>
    <div v-if="message&&(!libraryOpen||failure)" class="feedback" :class="{bad:failure}" role="status">{{message}}</div>
    <div v-if="running&&!libraryOpen&&tab==='results'" class="progress" role="status"><progress :value="active?.backtestProgress??0" max="1"/><span>{{active?.backtestStep}} · {{Math.round((active?.backtestProgress??0)*100)}}%</span></div>
    <ResearchConnectionNotice v-if="!ready" :phase="connection.phase.value" :attempt="connection.attempt.value" :max-attempts="connection.maxAttempts" :error="connection.error.value" :has-bots="bots.hasBots" @retry="connection.start" @settings="router.push('/settings')" />
    <template v-else-if="paperView&&api"><PaperWorkspace :api="api" strategy="" revision="" @open-results="openLibrary" /><PaperReconcileWorkspace :api="api" /></template>
    <StrategyLibrary v-else-if="libraryOpen&&api" :items="items" :runs="runs" :busy="working" @open="openStrategy" @favorite="toggleFavorite" @create="createDialog()" @compare="compareLatest" @refresh="guard(refresh)" />
    <div v-else-if="api" class="workspace" :class="{'sidebar-collapsed':!sidebarOpen}" :style="sidebarOpen ? { gridTemplateColumns: sidebarWidth + 'px minmax(0, 1fr)' } : undefined">
      <OperationsWorkspace v-if="route.name==='research-jobs'" :api="api" class="operations-span" />
      <aside v-show="sidebarOpen">
        <div class="sidebar-resize-handle" title="Kéo để thay đổi độ rộng danh sách chiến lược" @mousedown="startSidebarResize" />
        <div class="row sidebar-top">
          <h2>Chiến lược <small>{{items.length}}</small></h2>
          <button aria-label="Tải lại thư viện" title="Tải lại thư viện" @click="guard(refresh)">↻</button>
          <button aria-label="Thu gọn danh sách" title="Thu gọn danh sách chiến lược" @click="sidebarOpen=false">◧</button>
        </div>
        <button class="primary wide" @click="createDialog()">＋ Tạo chiến lược</button>
        <input v-model="query" aria-label="Tìm chiến lược" placeholder="Tên, mô tả hoặc nhãn…">
        <div class="sidebar-controls">
          <select v-model="sidebarFilter" aria-label="Lọc danh sách chiến lược">
            <option value="all">Tất cả ({{items.length}})</option>
            <option value="archived">Có gói backtest</option>
            <option value="profitable">Có lãi (&gt; 0 USDT)</option>
            <option value="favorite">★ Yêu thích</option>
            <option value="short">Hỗ trợ Short</option>
          </select>
          <select v-model="sidebarSort" aria-label="Sắp xếp danh sách chiến lược">
            <option value="evidence">Có gói trước</option>
            <option value="profit_desc">Lãi USDT ↓</option>
            <option value="drawdown_asc">Drawdown ↑</option>
            <option value="trades_desc">Số lệnh ↓</option>
            <option value="updated">Mới cập nhật</option>
            <option value="name">Tên A–Z</option>
          </select>
        </div>
        <div class="library">
          <button v-for="item in filtered" :key="item.name" class="strategy" :class="{chosen:selected===item.name}" @click="openStrategy(item.name, tab)">
            <div class="strategy-title-row">
              <b>{{item.research?.is_favorite?'★ ':''}}{{item.name}}</b>
              <span v-if="formatLibraryRunSummary(latestRunsMap.get(item.name), 1).hasProfit" class="mini-pnl" :class="pnlClass(latestRunsMap.get(item.name)?.summary?.profit_total_abs)">
                {{formatLibraryRunSummary(latestRunsMap.get(item.name), 1).signedProfitText}}
              </span>
            </div>
            <span>{{item.timeframe??'Kiểm tra mã'}} · {{(item.can_short===null || item.can_short===undefined)?'Chưa rõ chiều':item.can_short?'Hỗ trợ short':'Không khai báo short'}} <span v-if="item.protected">· Paper 🔒</span></span>
            <small>{{item.research?.idea?.slice(0,65)||'Chưa có mô tả nghiên cứu'}}</small>
          </button>
        </div>
        <a href="http://localhost:8092/tools/strategy-dev" target="_blank" rel="noopener">Mở Ultimate để so sánh ↗</a>
        <small class="lineage">Kế thừa FreqUI Ultimate + API chính thức của Freqtrade.</small>
      </aside>
      <section v-if="selected">
        <div class="strategy-head">
          <div>
            <span class="eyebrow">CHIẾN LƯỢC ĐANG NGHIÊN CỨU</span>
            <h2>{{selected}}</h2>
            <small>Mã {{revision.slice(0,10)}} · {{selectedItem?.timeframe}} · Binance USDT-M</small>
          </div>
          <div class="row head-actions">
            <button v-if="!sidebarOpen" @click="sidebarOpen=true">◨ Danh sách chiến lược ({{items.length}})</button>
            <button @click="createDialog(true)">Sao chép để thử</button>
          </div>
        </div>
        <div class="context-strip" role="region" aria-label="Trạng thái nghiên cứu hiện tại">
          <button type="button" class="ctx-card" :class="{active:tab==='code'}" @click="tab='code'">
            <span class="ctx-label">01 · Mã nguồn</span>
            <b :class="{warn:dirty}">{{dirty?'● Chưa lưu nháp':selectedItem?.protected?'🔒 Đang bảo vệ Paper':'✓ Đã lưu · ' + revision.slice(0,8)}}</b>
            <small>{{versions.length}} bản sao dự phòng</small>
          </button>
          <button type="button" class="ctx-card" :class="{active:tab==='run'}" @click="tab='run'">
            <span class="ctx-label">02 · Cấu hình & Tham số</span>
            <b>{{preset?preset.label:'Tham số gốc trong mã'}}</b>
            <small>{{interval||selectedItem?.timeframe||'—'}} · {{start}} → {{end||'Chưa chọn ngày kết thúc'}}</small>
          </button>
          <button type="button" class="ctx-card" :class="{active:tab==='results'}" @click="tab=selectedLatestRun?'results':'run'">
            <span class="ctx-label">03 · Gói Backtest gần nhất</span>
            <template v-if="selectedLatestRun">
              <b :class="pnlClass(selectedLatestRun.summary?.profit_total_abs)">
                {{formatLibraryRunSummary(selectedLatestRun).contextText}}
              </b>
              <small>{{selectedLatestRun.revision===revision?'✓ Khớp mã đang mở':'● Mã hiện tại đã đổi'}}</small>
            </template>
            <template v-else>
              <b>Chưa có gói lưu</b>
              <small>Mở Backtest để tạo hồ sơ đầu tiên</small>
            </template>
          </button>
          <button type="button" class="ctx-card" :class="{active:tab==='checks'}" @click="tab='checks'">
            <span class="ctx-label">04 · Kiểm định & Paper</span>
            <b>{{checks.length?checks.length+' báo cáo kiểm định':'Chưa kiểm định lookahead'}}</b>
            <small>Isolated 1x · {{results.length}} lịch sử kết quả</small>
          </button>
        </div>
        <nav class="steps" aria-label="Quy trình phát triển">
          <button v-for="[id,label] in tabs" :key="id" :class="{active:tab===id, dirty:id==='code'&&dirty}" @click="tab=id!">{{label}}</button>
        </nav>
        <div class="next-step-banner" :class="'tone-' + recommendedAction.tone" role="region" aria-label="Bước tiếp theo đề xuất">
          <div class="next-step-copy">
            <span class="next-step-badge">Bước tiếp theo đề xuất</span>
            <b>{{recommendedAction.label}}</b>
          </div>
          <button type="button" class="primary" @click="triggerRecommendedAction">{{recommendedAction.actionLabel}}</button>
        </div>
        <div v-if="tab==='idea'" class="pane">
          <h3>Viết rõ quy tắc trước khi thử</h3>
          <p>Điều kiện vào/ra, cắt lỗ, chốt lời, khung thời gian và rủi ro mỗi lệnh.</p>
          <label>Ý tưởng chiến lược<textarea v-model="idea" rows="6" placeholder="Ví dụ: short khi giá hồi về vùng Fibo sau một đợt tăng…" /></label>
          <label>Ghi chú và điều cần kiểm chứng<textarea v-model="notes" rows="4" placeholder="Giả định, trường hợp bỏ lệnh, điều đã thử…" /></label>
          <div class="form-grid-2">
            <label>Nhãn (phân cách bằng dấu phẩy)<input v-model="tagsText" placeholder="fibonacci, short, reversal" maxlength="400"></label>
            <label class="favorite-field"><input v-model="favorite" type="checkbox"> Đánh dấu yêu thích trong thư viện</label>
          </div>
          <div class="row">
            <button class="primary" :disabled="working" @click="saveResearch">Lưu nghiên cứu</button>
            <button @click="copyPrompt">Sao chép yêu cầu cho Codex</button>
            <span class="spacer"/>
            <button @click="tab='code'">Tiếp: xem mã →</button>
          </div>
          <p class="muted">Dùng Codex đang kết nối với dự án để phát triển từ ý tưởng. FreqPilot chưa có chatbot AI riêng.</p>
        </div>
        <div v-else-if="tab==='code'" class="pane">
          <div class="row">
            <b>{{selected}}.py <span v-if="dirty" class="unsaved-pill">● Chưa lưu</span></b>
            <span class="spacer"/>
            <button v-if="dirty" :disabled="working" @click="discardDraft">Bỏ nháp, khôi phục mã đã lưu</button>
            <button :disabled="working||!dirty||selectedItem?.protected" class="primary" @click="save">Lưu mã</button>
            <button @click="select(selected)">Tải lại</button>
          </div>
          <p v-if="selectedItem?.protected" class="hint">Mã paper đang chạy được bảo vệ. Hãy sao chép trước khi sửa.</p>
          <div class="editor"><CodeEditor v-model="code" language="python" :readonly="selectedItem?.protected" :filename="selected+'.py'" @save="save" /></div>
          <div class="row">
            <label class="inline-label">Phiên bản trước<select v-model="versionId"><option value="">Chọn bản sao dự phòng</option><option v-for="v in versions" :key="v.id" :value="v.id">{{new Date(v.saved_at*1000).toLocaleString('vi-VN')}}</option></select></label>
            <button :disabled="!versionId||working" @click="compareVersion">So sánh phiên bản</button>
            <button :disabled="!versionId||working" @click="restorePreview">Nạp bản cũ vào editor</button>
            <span class="spacer"/>
            <button @click="tab='data'">Tiếp: kiểm tra dữ liệu →</button>
            <button :disabled="dirty" class="primary" @click="tab='run'">Tiếp: backtest →</button>
          </div>
          <div v-if="versionPreview" class="version-diff">
            <div class="row"><h3>So sánh mã · chỉ đọc</h3><button @click="versionPreview=''">Đóng so sánh</button></div>
            <p>So sánh theo dòng bằng bộ xem có sẵn của Ultimate. Chưa khôi phục hoặc lưu mã.</p>
            <DiffViewer :saved="versionPreview" :current="code" :has-changes="versionPreview!==code" :saved-label="'Bản sao ' + versionId" current-label="Mã trong editor" />
          </div>
        </div>
        <div v-else-if="tab==='data'" class="pane">
          <div class="row date-presets">
            <span>Chọn nhanh khoảng ngày từ dữ liệu local:</span>
            <button type="button" @click="applyDatePreset()">Toàn bộ dữ liệu</button>
            <button type="button" @click="applyDatePreset(30)">30 ngày cuối</button>
            <button type="button" @click="applyDatePreset(14)">14 ngày cuối</button>
            <button type="button" @click="applyDatePreset(7)">7 ngày cuối</button>
          </div>
          <div class="form-grid">
            <label>Từ ngày UTC<input v-model="start" type="date"></label>
            <label>Đến ngày UTC, không gồm ngày này<input v-model="end" type="date"></label>
            <label>Khung nến chính<select v-model="interval"><option v-for="tf in [...new Set(data?.files.filter(x=>x.type==='futures').map(x=>x.timeframe))]" :key="tf">{{tf}}</option></select></label>
          </div>
          <DataQualityWorkspace v-if="api" :api="api" :timerange="timerange" :timeframe="interval||selectedItem?.timeframe||'15m'" :detail-timeframe="detail" :warmup-candles="selectedItem?.startup_candle_count??200" @updated="api.get('/studio/data').then(response=>data=response.data)" />
          <div class="row"><span class="spacer"/><button class="primary" @click="tab='run'">Tiếp: backtest →</button></div>
        </div>
        <div v-else-if="tab==='run'" class="pane">
          <div class="row">
            <h3>Backtest với dữ liệu đang có</h3>
            <button type="button" @click="runSplitEditor=!runSplitEditor">{{runSplitEditor ? 'Đóng khung mã cạnh cấu hình' : '◫ Mở mã chiến lược cạnh cấu hình'}}</button>
          </div>
          <div :class="{'run-split-layout': runSplitEditor}">
            <div class="run-config-col">
              <ParameterPresets v-if="api" :key="selected" :api="api" :strategy="selected" :revision="revision" :busy="working||running||checking||optimizationRunning||optimizationBusy" :selected="preset" @selected="preset=$event" @busy="parameterBusy=$event" />
              <p>Mô phỏng nến với chi tiết 1m; chưa phải khớp lệnh tick/L2. Phí hiện tại: {{pct(data?.fee)}} mỗi chiều.</p>
              <div class="row date-presets">
                <span>Khoảng thời gian chạy thử:</span>
                <button type="button" :disabled="running" @click="applyDatePreset()">Đặt theo dữ liệu sẵn có</button>
                <button type="button" :disabled="running" @click="applyDatePreset(30)">30 ngày cuối</button>
                <button type="button" :disabled="running" @click="applyDatePreset(14)">14 ngày cuối</button>
                <button type="button" :disabled="running" @click="applyDatePreset(7)">7 ngày cuối</button>
              </div>
              <div class="form-grid">
                <label>Từ ngày<input v-model="start" type="date"></label>
                <label>Đến ngày (không gồm ngày này)<input v-model="end" type="date"></label>
                <label>Khung tín hiệu<select v-model="interval"><option v-for="tf in [...new Set(data?.files.filter(x=>x.type==='futures').map(x=>x.timeframe))]" :key="tf">{{tf}}</option></select></label>
                <label>Khung chi tiết<select v-model="detail"><option>1m</option></select></label>
                <label>Vốn mô phỏng (USDT)<input v-model.number="wallet" type="number" min="1"></label>
                <label>Số tiền mỗi lệnh<input v-model.number="stake" type="number" min="1"></label>
                <label>Lệnh mở tối đa<input v-model.number="maxTrades" type="number" min="1" max="10"></label>
              </div>
              <div class="hint">BTC / ETH · isolated · chiến lược mẫu 1x · cache tắt · có mark price và funding.</div>
              <div class="row">
                <button class="primary" :disabled="working||dirty||running||checking||parameterBusy||optimizationRunning||optimizationBusy" @click="run">{{running?'Đang backtest…':'Chạy backtest'}}</button>
                <span v-if="dirty" class="warn-text">Lưu mã trước khi chạy.</span>
                <span v-if="manifestId">Hồ sơ chạy: {{manifestId.slice(0,10)}}</span>
                <span class="spacer"/>
                <button v-if="results.length" @click="tab='results'">Xem kết quả đã có ({{results.length}}) →</button>
              </div>
            </div>
            <div v-if="runSplitEditor" class="run-editor-col">
              <div class="row">
                <b>{{selected}}.py <span v-if="dirty" class="unsaved-pill">● Chưa lưu</span></b>
                <span class="spacer"/>
                <button v-if="dirty" :disabled="working" @click="discardDraft">Bỏ nháp</button>
                <button :disabled="working||!dirty||selectedItem?.protected" class="primary" @click="save">Lưu mã</button>
              </div>
              <div class="editor split-editor-box"><CodeEditor v-model="code" language="python" :readonly="selectedItem?.protected" :filename="selected+'.py'" @save="save" /></div>
            </div>
          </div>
          <div v-if="running" class="progress"><progress :value="active?.backtestProgress??0" max="1"/><span>{{active?.backtestStep}} · {{Math.round((active?.backtestProgress??0)*100)}}%</span></div>
          <div v-if="recentRuns.length" class="artifact-panel">
            <h3>Hồ sơ gần đây</h3>
            <div class="recent-runs-grid">
              <article v-for="item in recentRuns" :key="item.id" class="check-card">
                <div class="row">
                  <b>{{runStatus[item.status]??item.status}}</b>
                  <small>{{new Date(item.created_at).toLocaleString('vi-VN')}} · mã {{item.revision.slice(0,10)}}</small>
                  <span class="spacer"/>
                  <button v-if="item.status==='success'" @click="openFrozenRun(item)">Mở kết quả & hồ sơ</button>
                </div>
                <p v-if="item.optimization">Kiểm tra {{item.optimization.mode==='oos'?'ngoài mẫu':'tập học'}} · lượt {{item.optimization.epoch}} của phiên {{item.optimization.id.slice(0,10)}}.</p>
                <p v-if="item.preset">Bộ tham số: {{item.preset.label}} · {{item.preset.native_sha256.slice(0,10)}}</p>
                <p>{{item.settings.timeframe}} · {{item.settings.timerange}} · {{item.input_files}} tệp đầu vào</p>
                <p v-if="item.error" class="feedback bad">{{item.error}}</p>
              </article>
            </div>
          </div>
          <div class="artifact-panel import-bundle-panel">
            <h3>Nhập gói hồ sơ đóng băng (.zip)</h3>
            <p>Nạp gói <code>freqpilot-&lt;id&gt;.zip</code> để kiểm tra dấu vân tay SHA256, xem báo cáo gốc và chạy Archive Replay mà không ghi đè chiến lược đang có.</p>
            <div class="form-grid">
              <label>Tệp gói (.zip)<input type="file" accept=".zip,application/zip" @change="onImportFileChange"></label>
              <label>SHA256 kỳ vọng (64 ký tự hex, tùy chọn)<input v-model="importExpectedSha" placeholder="Để trống hoặc dán SHA256 để đối chiếu cứng" maxlength="64"></label>
              <label class="favorite-field"><input v-model="importInstallMissing" type="checkbox"> Thêm mã vào thư viện nếu chưa có tên chiến lược này</label>
            </div>
            <div class="row">
              <button type="button" class="primary" :disabled="working||!importFileBase64" @click="importArtifactBundle">Xác minh & Nhập gói hồ sơ</button>
              <small v-if="importFileName">Đã chọn: {{importFileName}}</small>
            </div>
          </div>
          <details>
            <summary>Phạm vi dữ liệu trên máy</summary>
            <div class="table-wrap">
              <table><thead><tr><th>Cặp</th><th>Dữ liệu</th><th>Khung</th><th>Bản ghi</th><th>Từ UTC</th><th>Đến UTC</th></tr></thead><tbody><tr v-for="f in data?.files" :key="f.pair+f.type+f.timeframe"><td>{{f.pair}}</td><td>{{f.type}}</td><td>{{f.timeframe}}</td><td>{{f.rows}}</td><td>{{fmtDate(f.start)}}</td><td>{{fmtDate(f.end)}}</td></tr></tbody></table>
            </div>
            <small>Đây là kiểm tra dữ liệu local, không phải một lần đối chiếu mới với Binance.</small>
          </details>
        </div>
        <div v-else-if="tab==='results'" class="pane">
          <div class="row">
            <h3>Lịch sử của {{selected}}</h3>
            <button @click="guard(refresh)">Tải lại kết quả</button>
            <span class="spacer"/>
            <button v-if="frozenRun?.status==='success'" @click="tab='checks'">Tiếp: Kiểm định bias →</button>
            <button v-if="frozenRun?.status==='success'" class="primary" @click="tab='paper'">Chuẩn bị Paper từ gói này →</button>
          </div>
          <div v-if="!results.length" class="empty">Chưa có kết quả. Chạy backtest trước khi đánh giá.</div>
          <div v-else class="history">
            <button
              v-for="entry in results"
              :key="entry.run_id+entry.filename"
              :class="{chosen:entry.filename===active?.selectedBacktestMetadata?.filename}"
              @click="loadResult(entry)"
            >
              <div class="history-top">
                <b>{{new Date(entry.backtest_start_time*1000).toLocaleString('vi-VN')}}</b>
                <span v-if="formatLibraryRunSummary(runForHistory(entry)).hasProfit" class="mini-pnl" :class="pnlClass(runForHistory(entry)?.summary?.profit_total_abs)">
                  {{formatLibraryRunSummary(runForHistory(entry)).profitText}}
                </span>
              </div>
              <small>{{entry.timeframe}} · {{runForHistory(entry)?.preset?.label || entry.filename}}</small>
            </button>
          </div>
          <template v-if="result">
            <p v-if="frozenRun?.optimization" class="hint">Backtest {{frozenRun.optimization.mode==='oos'?'ngoài mẫu':'lại tập học'}} · ứng viên lượt {{frozenRun.optimization.epoch}} · phiên tối ưu {{frozenRun.optimization.id.slice(0,10)}}. Đọc cùng số lệnh và khoảng ngày; đây chưa phải chứng nhận chất lượng.</p>
            <div class="core-metrics">
              <div>
                <small>Lãi / lỗ ròng</small>
                <b :class="pnlClass(result.profit_total_abs)">{{result.profit_total_abs.toFixed(2)}} USDT</b>
                <span :class="pnlClass(result.profit_total)">{{pct(result.profit_total)}}</span>
              </div>
              <div>
                <small>Drawdown tối đa</small>
                <b>{{pct(result.max_drawdown_account)}}</b>
                <small>Theo vốn tài khoản</small>
              </div>
              <div>
                <small>Số lệnh</small>
                <b>{{result.total_trades}}</b>
                <small>{{result.total_trades<30?'Mẫu nhỏ (<30)':'Đủ mẫu cơ bản'}}</small>
              </div>
              <div>
                <small>Profit factor</small>
                <b>{{formatBacktestProfitFactor(result)}}</b>
                <small>Khung {{result.timeframe}}</small>
              </div>
            </div>
            <BacktestSummaryCards :summary="result as unknown as Record<string,unknown>"/>
            <div v-if="result.total_trades<30" class="hint">Chỉ có {{result.total_trades}} lệnh: mẫu nhỏ, chưa đủ để kết luận chất lượng.</div>
            <div class="row modes">
              <button v-for="[mode,label] in [['summary','Tổng quan'],['analysis','Chỉ số & giao dịch'],['chart','Biểu đồ lệnh'],['graphs','Phân phối'],['compare','So sánh đã mở']]" :key="mode" :class="{active:resultMode===mode}" @click="resultMode=mode!">{{label}}</button>
            </div>
            <div v-if="resultMode==='summary'" class="equity-summary">
              <h3>Vốn theo các lệnh đã đóng</h3>
              <EquityCurveChart :equity="realizedEquity" :starting-balance="result.starting_balance"/>
              <small>Đã cộng lãi/lỗ ròng của lệnh đóng; không phải đường vốn gồm vị thế đang mở. Mã hiện tại có thể khác bản đã dùng trong báo cáo cũ.</small>
              <div v-if="tradeAnalytics.underwater.length" class="analytics-subgrid">
                <div class="analytics-card">
                  <h4>Sụt giảm vốn thực nhận (Underwater %)</h4>
                  <UnderwaterChart :series="tradeAnalytics.underwater" />
                </div>
                <div v-if="tradeAnalytics.monthly.length" class="analytics-card">
                  <h4>Lợi nhuận ròng theo tháng (USDT)</h4>
                  <MonthlyReturnsHeatmap :data="tradeAnalytics.monthly" />
                </div>
              </div>
            </div>
            <div class="legacy-report">
              <BacktestResultAnalysis v-if="resultMode==='analysis'" :backtest-result="result"/>
              <BacktestResultChart v-else-if="resultMode==='chart'" :timeframe="result.timeframe" :strategy="selected" :timerange="result.timerange" :backtest-result="result"/>
              <template v-else-if="resultMode==='graphs'">
                <div v-if="tradeAnalytics.exitReasons.length" class="analytics-subgrid">
                  <div class="analytics-card">
                    <h4>Phân bố lý do thoát lệnh (Exit Reason)</h4>
                    <ExitReasonChart :reasons="tradeAnalytics.exitReasons" />
                  </div>
                  <div class="analytics-card">
                    <h4>Hiệu suất theo thứ trong tuần (UTC)</h4>
                    <WeekdayPatternChart :pattern="tradeAnalytics.weekday" />
                  </div>
                  <div class="analytics-card analytics-span-2">
                    <h4>Hiệu suất theo giờ mở lệnh (UTC)</h4>
                    <HourlyPatternChart :data="tradeAnalytics.hourly" />
                  </div>
                </div>
                <BacktestGraphs :trades="result.trades"/>
              </template>
              <BacktestResultComparison v-else-if="resultMode==='compare'&&active" :backtest-results="active.backtestHistory"/>
            </div>
            <div v-if="frozenRun" class="artifact-panel">
              <div class="row">
                <b>Hồ sơ chạy {{frozenRun.id.slice(0,10)}}</b>
                <span class="safe">{{frozenRun.status==='success'?'Đã lưu gói đầu vào & kết quả':frozenRun.status}}</span>
                <span class="spacer"/>
                <button :disabled="working||frozenRun.status!=='success'" @click="verifyArtifact">Kiểm tra tính toàn vẹn</button>
                <button :disabled="working" @click="previewSource">Xem mã đã chạy</button>
                <button :disabled="working||frozenRun.status!=='success'" @click="copyDossier">Sao chép Dossier (.md)</button>
                <button :disabled="working||frozenRun.status!=='success'" @click="downloadDossier">Xuất Dossier (.md)</button>
                <button :disabled="working||frozenRun.status!=='success'" class="primary" @click="downloadArtifact">Tải gói mã + dữ liệu + kết quả</button>
              </div>
              <details v-if="frozenRun.preset"><summary>Giá trị tham số của lần chạy</summary><pre class="source-preview">{{JSON.stringify(frozenRun.preset.values,null,2)}}</pre></details>
              <p v-if="frozenRun.preset">Bộ tham số đã chạy: <b>{{frozenRun.preset.label}}</b> · dấu vân tay {{frozenRun.preset.native_sha256.slice(0,10)}}. Hồ sơ paper dùng bản này.</p>
              <p>Mã {{frozenRun.revision.slice(0,10)}} · {{frozenRun.input_files}} tệp đầu vào · {{(frozenRun.input_bytes/1048576).toFixed(2)}} MB. Engine đã chạy trên bản sao riêng của mã và dữ liệu.</p>
              <p v-if="frozenRun.revision!==revision" class="hint">Mã hiện tại khác phiên bản trong kết quả này. Mở mã đã chạy để đối chiếu.</p>
              <p v-if="artifactValid!==null" :class="{bad:!artifactValid}" class="feedback">{{artifactValid?'Dấu vân tay gói lưu khớp. Đây không phải chứng nhận chất lượng chiến lược.':'Gói lưu không khớp dấu vân tay.'}}</p>
              <details v-if="sourcePreview" open><summary>Mã gốc của lần chạy · chỉ đọc</summary><pre class="source-preview">{{sourcePreview}}</pre></details>
              <small>Gói lưu gồm mã local, nến/mark/funding, cấu hình nghiên cứu và ZIP gốc. Thư viện bên ngoài được cố định qua image engine; dữ liệu thị trường lấy qua mạng không nằm trong gói này.</small>
              <div class="artifact-subgrid">
                <ReplayBacktest v-if="api" :api="api" :run="frozenRun" :busy="working||running||checking||parameterBusy||optimizationRunning||optimizationBusy" :on-accepted="replayStarted" />
                <RunNotesPanel v-if="api" :key="frozenRun.id" :api="api" :run-id="frozenRun.id" :alternatives="runs" :strategy="selected" />
              </div>
            </div>
            <div v-else class="hint">Báo cáo cũ chưa có gói mã và dữ liệu đầy đủ. Mã đang mở có thể khác mã của báo cáo; hãy chạy lại để tạo hồ sơ có thể kiểm tra.</div>
          </template>
        </div>
        <div v-else-if="tab==='checks'" class="pane">
          <h3>Kiểm định trước khi chuyển sang paper</h3>
          <ParameterPresets v-if="api" :key="selected" :api="api" :strategy="selected" :revision="revision" :busy="working||running||checking||optimizationRunning||optimizationBusy" :selected="preset" @selected="preset=$event" @busy="parameterBusy=$event" />
          <p>Dùng API lookahead / recursive có sẵn của Freqtrade 2026.9. Khoảng ngày và khung tín hiệu lấy từ tab Backtest. Không tối ưu tham số.</p>
          <div class="row">
            <button class="primary" :disabled="working||dirty||running||checking||parameterBusy||optimizationRunning||optimizationBusy" @click="startCheck('lookahead')">Kiểm tra lookahead</button>
            <button :disabled="working||dirty||running||checking||parameterBusy||optimizationRunning||optimizationBusy" @click="startCheck('recursive')">Kiểm tra warmup / recursive</button>
            <button @click="guard(loadChecks)">Tải lại kiểm định</button>
            <span class="spacer"/>
            <button @click="tab='optimize'">Tiếp: Tối ưu tham số →</button>
          </div>
          <details><summary>Tham số chẩn đoán</summary><div class="form-grid"><label>Số tín hiệu tối thiểu<input v-model.number="minSignals" type="number" min="1" max="500"></label><label>Số tín hiệu muốn kiểm tra<input v-model.number="targetSignals" type="number" min="1" max="200"></label></div></details>
          <div class="hint">Không phát hiện bias trên một mẫu nhỏ không chứng minh chiến lược an toàn hay có lợi nhuận. Recursive chỉ kiểm tra cặp đầu tiên theo cơ chế gốc của Freqtrade.</div>
          <div v-if="!checks.length" class="empty">Chưa có kiểm định cho chiến lược này.</div>
          <ResearchCheckReport
            v-for="check in checks"
            :key="check.id"
            :check="check"
            :context="{
              strategy: selected,
              revision,
              parameterRevision: preset?.native_sha256 ?? selectedItem?.parameter_revision,
              timeframe: interval,
              timerange: start.replaceAll('-', '') + '-' + end.replaceAll('-', ''),
            }"
          />
        </div>
        <div v-else-if="tab==='optimize'" class="pane">
          <h3>Tối ưu rồi kiểm tra lại trên dữ liệu chưa dùng</h3>
          <p>Ngày, khung nến, vốn và phí lấy từ biểu mẫu Backtest. Chọn khoảng kết thúc rõ ràng trước khi tối ưu.</p>
          <div v-if="!end" class="row date-presets">
            <span>Chưa chọn ngày kết thúc ở Backtest. Chọn nhanh từ dữ liệu sẵn có:</span>
            <button type="button" @click="applyDatePreset()">Toàn bộ dữ liệu</button>
            <button type="button" @click="applyDatePreset(30)">30 ngày cuối</button>
          </div>
          <OptimizationWorkspace v-if="api" :key="selected" :api="api" :strategy="selected" :revision="revision" :settings="optimizationSettings" :preset="preset" :busy="working||dirty||running||checking||parameterBusy" :on-accepted="optimizationBacktestStarted" @busy="optimizationBusy=$event" @selected="preset=$event" @running="readOptimizationActivity" />
          <SeedExperimentsWorkspace v-if="api" :key="selected" :api="api" :strategy="selected" :revision="revision" :settings="optimizationSettings" :preset-id="preset?.id" :busy="working||dirty||running||checking||parameterBusy||optimizationRunning" />
        </div>
        <div v-else-if="tab==='walk'" class="pane"><WalkForwardWorkspace v-if="api" :key="selected" :api="api" :strategy="selected" :revision="revision" :settings="optimizationSettings" :preset-id="preset?.id" :warmup-candles="selectedItem?.startup_candle_count??200" :busy="working||dirty||running||checking||parameterBusy||optimizationRunning" /></div>
        <div v-else-if="tab==='sensitivity'" class="pane"><SensitivityWorkspace v-if="api" :key="selected" :api="api" :strategy="selected" :revision="revision" :settings="optimizationSettings" :preset-id="preset?.id" :base-fee="data?.fee" :busy="working||dirty||running||checking||parameterBusy||optimizationRunning" /></div>
        <div v-else-if="tab==='matrix'" class="pane"><MatrixWorkspace v-if="api" :key="selected" :api="api" :strategy="selected" :revision="revision" :settings="optimizationSettings" :preset-id="preset?.id" :busy="working||dirty||running||checking||parameterBusy||optimizationRunning" /></div>
        <div v-else-if="tab==='compare'" class="pane"><h3>So sánh chiến lược đã chạy</h3><p>Mỗi cột là một lần chạy đã lưu. Các chiến lược có thể dùng khung thời gian khác nhau; hãy đọc cấu hình trước khi xếp hạng.</p><div class="hint">Lợi nhuận cao với ít lệnh chưa chứng minh chất lượng. Xem drawdown, profit factor, số lệnh và kiểm định lookahead / recursive.</div><div class="legacy-report"><BacktestResultComparison :backtest-results="comparison"/></div></div>
        <div v-else class="pane"><PaperWorkspace v-if="api" :api="api" :strategy="selected" :revision="revision" :run="frozenRun?.strategy===selected?frozenRun:undefined" @open-results="tab='results'" /><PaperReconcileWorkspace v-if="api" :api="api" :run-id="frozenRun?.strategy===selected?frozenRun.id:undefined" /></div>
      </section>
      <div v-else class="empty">Tạo hoặc chọn một chiến lược để bắt đầu.</div>
    </div>
    <div v-if="newOpen" class="modal" role="dialog" aria-modal="true" aria-label="Tạo chiến lược FreqPilot"><form @submit.prevent="create"><h2>{{sourceName?'Sao chép chiến lược':'Tạo chiến lược mới'}}</h2><p v-if="failure" class="feedback bad">{{message}}</p><p>Đặt tên tệp và class, ví dụ MyBreakoutFutures.</p><label>Tên chiến lược<input v-model="newName" required pattern="[A-Za-z][A-Za-z0-9_]{0,79}" maxlength="80" autofocus></label><label>Bắt đầu từ<select v-model="sourceName"><option value="">Mẫu trống · chưa có tín hiệu</option><option v-for="item in items" :key="item.name">{{item.name}}</option></select></label><div class="row"><button type="button" @click="newOpen=false">Hủy</button><button class="primary" :disabled="working">Tạo và mở mã</button></div></form></div>
  </div>
</template>

<style scoped>
.pilot,
.pilot * {
  text-align: left;
}
.pilot {
  padding: 22px 26px;
  max-width: 1840px;
  margin: auto;
  color: var(--fg);
  font-family: var(--font-ui);
}
.pilot-heading,
.strategy-head,
.row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.pilot-heading {
  justify-content: space-between;
  margin-bottom: 14px;
  padding: 6px 10px;
  background: var(--bg-1);
  border: 1px solid var(--line);
  border-radius: 10px;
}
.eyebrow {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.14em;
  color: var(--accent);
}
h1 {
  font-size: 26px;
  font-weight: 650;
  line-height: 1.25;
  margin: 6px 0 4px;
}
h2 {
  font-size: 18px;
  font-weight: 650;
  margin: 0;
}
h3 {
  font-size: 18px;
  font-weight: 650;
  margin: 0 0 10px;
}
p {
  line-height: 1.55;
  color: var(--fg-2);
  margin: 8px 0 14px;
  font-size: 13px;
}
.studio-lang-select {
  width: auto;
  padding: 6px 10px;
  font-size: 12px;
  font-weight: 600;
  background: var(--bg-2);
}
small,
.muted {
  color: var(--fg-3);
  font-size: 12px;
}
.safe {
  background: #143b32;
  border: 1px solid #20604e;
  color: #79dfb3;
  border-radius: 30px;
  padding: 6px 13px;
  font-size: 12px;
  font-weight: 600;
}
.area-nav {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin: 0;
  padding: 0;
}
.area-nav button {
  background: transparent;
  border-color: transparent;
  color: var(--fg-2);
  padding: 7px 13px;
  border-radius: 7px;
  font-weight: 500;
}
.area-nav button.active {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 14%, var(--bg-2));
  color: var(--accent);
}
.operations-span {
  grid-column: 1/-1;
}
.workspace {
  display: grid;
  grid-template-columns: 275px minmax(0, 1fr);
  gap: 20px;
}
.workspace.sidebar-collapsed {
  grid-template-columns: minmax(0, 1fr);
}
.workspace > aside {
  background: var(--bg-1);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 15px;
  align-self: start;
  position: sticky;
  top: calc(var(--hdr, 52px) + 12px);
}
.sidebar-resize-handle {
  position: absolute;
  top: 8px;
  right: -6px;
  bottom: 8px;
  width: 8px;
  cursor: col-resize;
  z-index: 10;
}
.sidebar-resize-handle:hover {
  background: color-mix(in srgb, var(--accent) 35%, transparent);
  border-radius: 4px;
}
.sidebar-controls {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  margin-top: 6px;
}
.sidebar-controls select {
  padding: 6px 8px;
  font-size: 11.5px;
}
.run-split-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.1fr);
  gap: 18px;
  align-items: start;
}
.split-editor-box {
  height: 460px;
}
.analytics-subgrid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin: 16px 0;
}
.analytics-card {
  border: 1px solid var(--line);
  background: var(--bg);
  border-radius: 10px;
  padding: 14px;
}
.analytics-card h4 {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
}
.analytics-span-2 {
  grid-column: 1 / -1;
}
.row {
  margin-bottom: 12px;
}
.row h2,
.row h3 {
  margin-right: auto;
  margin-bottom: 0;
}
.spacer {
  flex: 1;
}
button,
.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--line-2);
  background: var(--bg-2);
  color: var(--fg);
  font: inherit;
  font-size: 12.5px;
  font-weight: 500;
  padding: 8px 13px;
  border-radius: 7px;
  cursor: pointer;
  text-decoration: none;
  transition: border-color 0.15s, background-color 0.15s, color 0.15s;
}
button:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}
button:disabled {
  opacity: 0.42;
  cursor: default;
}
.primary {
  background: #1b6a5c;
  color: #f2fff9;
  border-color: #268b77;
}
.primary:hover:not(:disabled) {
  background: #217d6d;
  color: #fff;
}
.wide {
  width: 100%;
  margin-bottom: 10px;
}
input,
select,
textarea {
  font: inherit;
  font-size: 13px;
  background: var(--bg);
  border: 1px solid var(--line-2);
  border-radius: 7px;
  padding: 9px 11px;
  color: var(--fg);
  width: 100%;
}
input:focus,
select:focus,
textarea:focus {
  outline: none;
  border-color: var(--accent);
}
textarea {
  resize: vertical;
}
.library {
  margin: 10px 0;
  max-height: 64vh;
  overflow: auto;
  padding-right: 2px;
}
.strategy {
  width: 100%;
  display: flex;
  align-items: stretch;
  flex-direction: column;
  gap: 5px;
  text-align: left;
  margin: 6px 0;
  padding: 11px 12px;
  background: var(--bg);
}
.strategy-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}
.strategy b {
  overflow-wrap: anywhere;
  font-size: 13px;
}
.strategy > span {
  font-size: 11px;
  color: var(--fg-2);
}
.mini-pnl {
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--bg-2);
  white-space: nowrap;
}
.pos {
  color: #79dfb3 !important;
}
.neg {
  color: #f29b9b !important;
}
.chosen {
  border-color: var(--accent);
  background: #17342f;
}
.lineage {
  display: block;
  margin-top: 12px;
  line-height: 1.5;
}
a {
  color: var(--accent);
  font-size: 12.5px;
}
section {
  min-width: 0;
}
.strategy-head {
  justify-content: space-between;
  margin-bottom: 14px;
}
.strategy-head h2 {
  font-size: 22px;
  margin: 4px 0;
}
.context-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}
.ctx-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: flex-start;
  gap: 4px;
  padding: 11px 14px;
  border-radius: 9px;
  background: var(--bg-1);
  border: 1px solid var(--line);
  text-align: left;
}
.ctx-card.active {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 10%, var(--bg-1));
}
.ctx-label {
  font-size: 10.5px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--fg-3);
}
.ctx-card b {
  font-size: 13px;
  color: var(--fg);
  font-variant-numeric: tabular-nums;
}
.ctx-card b.warn {
  color: #e7bb72;
}
.steps {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 6px;
  margin-bottom: 16px;
  background: var(--bg-1);
  border: 1px solid var(--line);
  border-radius: 10px;
}
.steps button {
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  padding: 6px 9px;
  font-size: 11.5px;
  font-weight: 500;
  color: var(--fg-2);
  white-space: nowrap;
}
.steps button:hover {
  background: var(--bg-2);
  color: var(--fg);
}
.steps button.active {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 16%, var(--bg-2));
  color: var(--accent);
  font-weight: 600;
}
.steps button.dirty::after {
  content: ' ●';
  color: #e7bb72;
}
.next-step-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 14px;
  margin-bottom: 16px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: var(--bg-1);
}
.next-step-banner.tone-warn {
  border-color: #8c6a2b;
  background: color-mix(in srgb, #e7bb72 10%, var(--bg-1));
}
.next-step-banner.tone-ok {
  border-color: #20604e;
  background: color-mix(in srgb, #268b77 12%, var(--bg-1));
}
.next-step-copy {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.next-step-badge {
  font-size: 10.5px;
  font-weight: 650;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--bg-2);
  color: var(--accent);
}
.next-step-banner.tone-warn .next-step-badge {
  color: #e7bb72;
}
.next-step-copy b {
  font-size: 13px;
}
.pane {
  border: 1px solid var(--line);
  background: var(--bg-1);
  border-radius: 12px;
  padding: 22px;
}
.pane label {
  display: block;
  color: var(--fg-2);
  font-size: 12px;
  font-weight: 500;
  margin: 10px 0;
}
.pane label.inline-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}
.pane label.inline-label select {
  margin-top: 0;
  width: auto;
  min-width: 220px;
}
.pane label textarea,
.pane label input,
.pane label select {
  display: block;
  margin-top: 6px;
}
.favorite-field {
  display: flex !important;
  align-items: center;
  gap: 8px;
  padding-top: 22px;
  cursor: pointer;
}
.favorite-field input {
  width: auto !important;
  margin: 0 !important;
  accent-color: var(--accent);
}
.unsaved-pill {
  color: #e7bb72;
  font-size: 12px;
  margin-left: 6px;
}
.warn-text {
  color: #e7bb72;
  font-size: 12.5px;
}
.date-presets {
  padding: 9px 12px;
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 8px;
  font-size: 12px;
  color: var(--fg-2);
}
.date-presets button {
  padding: 5px 10px;
  font-size: 12px;
}
.version-diff {
  margin-top: 22px;
  padding-top: 18px;
  border-top: 1px solid var(--line);
}
.hint,
.feedback {
  padding: 11px 15px;
  background: #132b2a;
  border-left: 3px solid var(--accent);
  border-radius: 6px;
  font-size: 12.5px;
  margin: 14px 0;
  line-height: 1.55;
}
.feedback {
  margin: 0 0 16px;
}
.bad {
  background: #3c2024;
  border-color: #ee8989;
  color: #ffb4b4;
}
.editor {
  position: relative;
  height: 570px;
  border: 1px solid var(--line);
  border-radius: 8px;
  margin: 12px 0;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px 16px;
}
.form-grid-2 {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
  align-items: center;
}
.history {
  display: flex;
  gap: 8px;
  overflow: auto;
  padding: 6px 0 16px;
}
.history button {
  flex-direction: column;
  align-items: stretch;
  gap: 5px;
  min-width: 245px;
  background: var(--bg);
  padding: 10px 13px;
}
.history-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.history small {
  font-size: 10.5px;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.modes {
  margin: 16px 0 12px;
  padding: 5px;
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 9px;
  width: fit-content;
}
.modes button {
  border-color: transparent;
  background: transparent;
}
.modes .active {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 15%, var(--bg-2));
  color: var(--accent);
}
.core-metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin: 14px 0;
}
.core-metrics > div {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px;
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 10px;
}
.core-metrics b {
  font-size: 22px;
  font-variant-numeric: tabular-nums;
}
.core-metrics span {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--accent);
  font-variant-numeric: tabular-nums;
}
.equity-summary {
  margin-top: 14px;
  padding: 16px;
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 10px;
}
.legacy-report {
  margin-top: 18px;
  overflow: auto;
}
.empty {
  padding: 40px;
  text-align: center !important;
  color: var(--fg-3);
}
.modal {
  position: fixed;
  inset: 0;
  z-index: 150;
  background: #000a;
  display: grid;
  place-items: center;
}
.modal form {
  width: min(520px, 95vw);
  background: var(--bg-1);
  border: 1px solid var(--line-2);
  padding: 26px;
  border-radius: 14px;
}
.modal label {
  display: block;
  margin: 14px 0;
}
.modal input,
.modal select {
  margin-top: 8px;
}
.modal .row {
  margin: 20px 0 0;
  justify-content: end;
}
.progress {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 16px 0;
}
progress {
  flex: 1;
}
details {
  margin: 18px 0 0;
}
summary {
  cursor: pointer;
  color: var(--accent);
  font-size: 13px;
  font-weight: 500;
}
.table-wrap {
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--bg);
  margin-top: 10px;
}
table {
  width: 100%;
  font-size: 11.5px;
  border-collapse: collapse;
  font-variant-numeric: tabular-nums;
}
th,
td {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid var(--line);
}
th {
  background: var(--bg-2);
  color: var(--fg-3);
  font-weight: 600;
}
.artifact-panel {
  border: 1px solid var(--line);
  background: var(--bg-1);
  border-radius: 10px;
  padding: 18px;
  margin: 18px 0 0;
}
.artifact-subgrid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  align-items: start;
  margin-top: 12px;
}
.source-preview {
  font-size: 12px;
  max-height: 400px;
  overflow: auto;
  background: var(--bg);
  padding: 14px;
  border-radius: 8px;
  white-space: pre;
}
.recent-runs-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}
.check-card {
  border: 1px solid var(--line);
  background: var(--bg);
  border-radius: 8px;
  padding: 14px;
}
.check-card pre {
  overflow: auto;
  font-size: 12px;
  max-height: 450px;
  padding: 14px;
  background: var(--bg);
}
@media (max-width: 1200px) {
  .context-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .artifact-subgrid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 1000px) {
  .workspace {
    grid-template-columns: 220px minmax(0, 1fr);
  }
  .pilot {
    padding: 16px;
  }
  .form-grid,
  .core-metrics {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 720px) {
  .workspace {
    grid-template-columns: 1fr;
  }
  .workspace > aside {
    position: static;
  }
  .library {
    max-height: 240px;
  }
  .form-grid,
  .form-grid-2,
  .context-strip,
  .core-metrics {
    grid-template-columns: 1fr;
  }
  .pilot-heading h1 {
    font-size: 22px;
  }
  .pane {
    padding: 14px;
  }
}
</style>
