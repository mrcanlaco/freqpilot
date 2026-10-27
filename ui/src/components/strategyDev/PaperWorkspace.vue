<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import type { AxiosInstance } from 'axios';
import { registerPaperLogin } from '@/composables/loginInfo';
import { useBotStore } from '@/stores/ftbotwrapper';
import { botKeyFromApiUrl } from '@/datasource/protocol/identity';
import type { StrategyPreset } from '@/utils/strategyLibrary';
import { useDataSource } from '@/composables/useDataSource';
import PaperHistory from '@/components/strategyDev/PaperHistory.vue';

type Profile = { id:string; label:string; strategy:string; revision:string; run_id:string; warnings:string[];preset?:StrategyPreset;optimization?:{id:string;epoch:number;mode:'train'|'oos'};valid?:boolean;error?:string;archived?:boolean;archived_at?:string|null;
  settings:{pairs:string[];timeframe:string;wallet:number;stake:number|string;max_open_trades:number;fee:number};
  summary:{total_trades?:number;profit_total_abs?:number} };
type PaperState = {online:boolean;state:string;error?:string;history_error?:string;active_profile?:string|null;open_trades:number|null;profiles:Profile[]};
const props=defineProps<{api:AxiosInstance;strategy:string;revision:string;run?:{id:string;strategy:string;revision:string;status:string}}>();
defineEmits<{openResults:[]}>();
const router=useRouter(),bots=useBotStore();
const dataSource=useDataSource();
const state=ref<PaperState>(), working=ref(false),message=ref(''),bad=ref(false),label=ref('');
const showArchived=ref(false);
const historyRefresh=ref(0);
let poll:ReturnType<typeof setInterval>|undefined;
let refreshFailed=false;
const scopedProfiles=computed(()=>state.value?.profiles.filter(p=>!props.strategy||p.strategy===props.strategy)??[]);
const archivedCount=computed(()=>scopedProfiles.value.filter(p=>p.archived&&p.id!==state.value?.active_profile).length);
const profiles=computed(()=>scopedProfiles.value.filter(p=>!p.archived||showArchived.value||p.id===state.value?.active_profile));
const active=computed(()=>state.value?.profiles.find(p=>p.id===state.value?.active_profile));
const statusNames:Record<string,string>={running:'Đang chạy paper',paused:'Tạm ngừng vào lệnh · vẫn quản lý thoát lệnh',stopped:'Đã dừng',reload_config:'Đang nạp cấu hình · chờ xác nhận',unavailable:'Chưa kết nối'};
function errorText(e:unknown){const err=e as {response?:{data?:{detail?:unknown}};message?:string};return String(err.response?.data?.detail??err.message??e);}
async function refresh(){try{state.value=(await props.api.get('/studio/paper')).data;historyRefresh.value++;if(refreshFailed){message.value='';bad.value=false;refreshFailed=false;}}catch(e){refreshFailed=true;if(state.value)state.value={...state.value,online:false,state:'unavailable'};message.value=errorText(e);bad.value=true;}}
async function action(fn:()=>Promise<void>){working.value=true;bad.value=false;try{await fn();await refresh();}catch(e){message.value=errorText(e);bad.value=true;}finally{working.value=false;}}
async function prepare(){if(!props.run)return;await action(async()=>{await props.api.post('/studio/paper/profiles',{run_id:props.run!.id,label:label.value});message.value='Đã chuẩn bị mã và database paper riêng. Bot chưa được bật.';});}
async function setArchived(profile:Profile, archived:boolean){await action(async()=>{await props.api.post('/studio/paper/profiles/'+profile.id+'/'+(archived?'archive':'restore'));message.value=archived?'Đã lưu trữ hồ sơ khỏi danh sách thường dùng. Mã, database và lịch sử vẫn được giữ.':'Đã hiện lại hồ sơ paper.';});}
async function start(profile:Profile){await action(async()=>{message.value='Đang nạp worker paper; bước này có thể mất khoảng một phút…';const response=await props.api.post('/studio/paper/profiles/'+profile.id+'/start',{}, {timeout:150000});message.value=response.data.action_result?.outcome==='observed'?'Đã quan sát worker chạy paper cho '+profile.label+'.':'Đã gửi yêu cầu bật paper; chưa xác nhận trạng thái đích. Theo dõi trạng thái và lịch sử, không gửi lại tự động.';if(response.data.history_error)message.value+=' Trạng thái worker và lỗi lưu lịch sử được xử lý riêng: '+response.data.history_error;});}
async function control(kind:'pause'|'stop'){await action(async()=>{message.value=kind==='pause'?'Đang tạm ngừng vào lệnh…':'Đang dừng worker sau khi kiểm tra vị thế…';const response=await props.api.post('/studio/paper/'+kind,{}, {timeout:90000});message.value=response.data.action_result?.outcome==='observed'?(kind==='pause'?'Đã quan sát worker tạm ngừng vào lệnh, tiếp tục quản lý thoát lệnh.':'Đã quan sát worker dừng khi không còn vị thế mở.'):'Đã gửi yêu cầu; chưa xác nhận trạng thái đích. Theo dõi trạng thái và lịch sử, không gửi lại tự động.';if(response.data.history_error)message.value+=' Trạng thái worker và lỗi lưu lịch sử được xử lý riêng: '+response.data.history_error;});}
async function monitor(){await action(async()=>{
  message.value='Đang kết nối màn hình giám sát paper…';
  const source=dataSource.requireSource();
  if(source.kind!=='direct')throw Error('Giám sát worker local hiện dùng nguồn Direct. Chọn Direct trong Settings trước khi mở.');
  const {data}=await props.api.post('/studio/paper/connection');
  const url='http://'+window.location.hostname+':'+data.apiPort;
  const id='freqpilot.research-paper';
  registerPaperLogin(id,{botName:data.botName,apiUrl:url,accessToken:data.accessToken,refreshToken:data.refreshToken,autoRefresh:true});
  const descriptor={botId:id,botName:data.botName,botUrl:url,sortId:99,createdAt:Date.now()};
  if(!bots.availableBots[id])bots.addBot(descriptor);else bots.updateBot(id,descriptor);
  const bot=bots.botStores[id];
  await bot?.getState();
  await bot?.getWhitelist();
  await source.registry.list();
  await router.push({name:'bot',params:{botKey:botKeyFromApiUrl(url,[window.location.hostname])!},
    query:{...(bot?.whitelist[0]?{pair:bot.whitelist[0]}:{}),...(bot?.timeframe?{tf:bot.timeframe}:{})}});
});}
onMounted(()=>{void refresh();poll=setInterval(()=>{if(!working.value)void refresh();},5000);});
onUnmounted(()=>{if(poll)clearInterval(poll);});
</script>

<template>
  <div class="paper-workspace">
    <div class="row"><span class="badge">PAPER · 1X · ISOLATED</span><button :disabled="working" @click="refresh">Tải lại trạng thái</button></div>
    <h3>Từ kết quả nghiên cứu sang quan sát thị trường thật</h3>
    <p>Worker nghiên cứu dùng engine chính thức 2026.9 và tiền mô phỏng. Bot StarterFutures hiện có dùng dịch vụ riêng trên cổng 8090.</p>
    <div v-if="message" class="notice" :class="{bad}" role="status">{{message}}</div>
    <article class="box worker">
      <div class="row"><b>{{!state&&!bad?'Đang đọc trạng thái worker…':statusNames[state?.state??'unavailable']??state?.state}}</b><span v-if="state?.online" class="badge">Kết nối 8095</span></div>
      <p v-if="active">Hồ sơ đang chọn: <strong>{{active.label}}</strong> · {{active.strategy}} · mã {{active.revision.slice(0,10)}}.</p>
      <p v-else-if="state?.online">Worker đã sẵn sàng, chưa chọn hồ sơ nghiên cứu.</p>
      <p v-if="state?.error" class="notice bad">{{state.error}}</p>
      <p v-if="state?.history_error" class="notice bad">{{state.history_error}} Kết nối worker hiển thị riêng; lỗi lịch sử không đồng nghĩa bot đã dừng.</p>
      <p v-if="state?.online">Vị thế mô phỏng đang mở: <b>{{state.open_trades}}</b>.</p>
      <div class="row"><button :disabled="working||!state?.online||!active||!(state.state==='running'||(state.state==='stopped'&&Number(state.open_trades)>0))" @click="control('pause')">{{state?.state==='stopped'&&Number(state.open_trades)>0?'Tiếp tục quản lý thoát lệnh':'Tạm ngừng vào lệnh'}}</button><button :disabled="working||!state?.online||!['running','paused'].includes(state.state)||state.open_trades!==0" @click="control('stop')">Dừng khi đã hết vị thế</button><button class="primary" :disabled="working||!state?.online||!active" @click="monitor">Mở giám sát paper</button></div>
      <small>Đổi hồ sơ cần hết vị thế mở. Tạm ngừng vẫn cho engine quản lý thoát lệnh; bật lại cùng hồ sơ sẽ dùng tiếp database cũ. Sau khi dịch vụ khởi động lại, worker không tự vào lệnh mới. Nếu còn vị thế, worker tiếp tục quản lý thoát lệnh ở chế độ tạm ngừng; nếu không còn vị thế thì dừng.</small><p class="notice">Chế độ tạm ngừng chặn vào lệnh mới và tăng vị thế. Giảm vị thế hoặc chốt lời từng phần vẫn được xử lý theo chiến lược, cùng stoploss, ROI và tín hiệu thoát.</p>
    </article>
    <PaperHistory :api="api" :strategy="strategy" :profiles="profiles" :refresh-key="historyRefresh" />
    <article v-if="strategy" class="box">
      <h3>1 · Chuẩn bị từ bản đã backtest</h3>
      <template v-if="run?.strategy===strategy&&run.status==='success'">
        <p>Hồ sơ {{run.id.slice(0,10)}} · {{strategy}} · mã {{run.revision.slice(0,10)}}. Sao chép mã từ gói lưu, giữ nguyên quy tắc tín hiệu, dùng lớp paper giới hạn leverage 1x.</p>
        <p v-if="run.revision!==revision" class="notice">Mã hiện tại khác mã của báo cáo này. Paper sẽ dùng phiên bản trong gói backtest.</p>
        <label>Tên hồ sơ paper<input v-model="label" maxlength="70" :placeholder="strategy+' paper'" /></label>
        <button class="primary" :disabled="working" @click="prepare">Chuẩn bị hồ sơ paper</button>
      </template>
      <template v-else><p>Chọn một kết quả có gói mã và dữ liệu đã lưu trước khi chuẩn bị paper.</p><button @click="$emit('openResults')">Mở kết quả backtest</button></template>
    </article>
    <article class="box"><div class="row"><h3>{{strategy?'2 · Xem cấu hình rồi bật paper':'Hồ sơ paper đã chuẩn bị'}}</h3><button v-if="!strategy" @click="$emit('openResults')">＋ Chuẩn bị từ kết quả backtest</button></div>
      <div v-if="archivedCount" class="row"><button :disabled="working" @click="showArchived=!showArchived">{{showArchived?'Ẩn hồ sơ đã lưu trữ':'Xem '+archivedCount+' hồ sơ đã lưu trữ'}}</button><small>Lưu trữ chỉ ẩn khỏi danh sách thường dùng; mã, database và lịch sử không bị xóa.</small></div>
      <p v-if="!state">{{bad?'Chưa tải được hồ sơ paper. Hãy tải lại trạng thái.':'Đang tải hồ sơ paper…'}}</p><p v-else-if="!profiles.length">{{archivedCount?'Các hồ sơ trong phạm vi này đã được lưu trữ. Chọn xem hồ sơ đã lưu trữ để hiện lại.':strategy?'Chưa có hồ sơ paper cho '+strategy+'.':'Chưa có hồ sơ paper. Mở một chiến lược và chọn kết quả backtest đã lưu để chuẩn bị.'}}</p>
      <div v-for="profile in profiles" :key="profile.id" class="profile">
        <div class="row"><b>{{profile.label}}</b><span v-if="profile.id===state?.active_profile" class="badge">Hồ sơ đang chọn</span><span v-if="profile.archived" class="badge">Đã lưu trữ</span></div>
        <p>{{profile.strategy}} · {{profile.settings.pairs.join(' · ')}} · {{profile.settings.timeframe}} · isolated 1x</p>
        <dl><div><dt>Vốn mô phỏng</dt><dd>{{profile.settings.wallet}} USDT</dd></div><div><dt>Stake đề xuất</dt><dd>{{profile.settings.stake}} USDT</dd></div><div><dt>Lệnh mở tối đa</dt><dd>{{profile.settings.max_open_trades}}</dd></div><div><dt>Phí mỗi chiều</dt><dd>{{(profile.settings.fee*100).toFixed(3)}}%</dd></div></dl>
        <p v-if="profile.optimization">Nguồn tối ưu {{profile.optimization.id.slice(0,10)}} · lượt {{profile.optimization.epoch}} · backtest {{profile.optimization.mode==='oos'?'ngoài mẫu':'lại tập học'}}. Bộ số lấy từ gói đã kiểm tra, không tự chọn kết quả tối ưu mới.</p><p v-if="profile.preset">Bộ tham số từ backtest: <b>{{profile.preset.label}}</b> · {{profile.preset.native_sha256.slice(0,10)}}. Không lấy giá trị mới trong thư viện.</p><p>Backtest nguồn: {{profile.summary.total_trades??0}} lệnh · {{profile.summary.profit_total_abs?.toFixed(3)??'—'}} USDT · mã {{profile.revision.slice(0,10)}}.</p>
        <p v-if="profile.valid===false" class="notice bad">{{profile.error}} Hãy chuẩn bị một hồ sơ mới.</p><div class="notice"><p v-for="warning in profile.warnings" :key="warning">{{warning}}</p></div>
        <div class="row"><button class="primary" :disabled="working||profile.archived||profile.valid===false||!state?.online||!['running','paused','stopped'].includes(state.state)||(state.active_profile===profile.id&&state.state==='running')||(state.open_trades!==0&&state.active_profile!==profile.id)" @click="start(profile)">{{profile.id===state?.active_profile&&state?.state==='running'?'Đang chạy paper':profile.id===state?.active_profile&&state?.state==='paused'?'Tiếp tục paper':'Bật paper hồ sơ này'}}</button><button v-if="profile.archived" :disabled="working" @click="setArchived(profile,false)">Hiện lại hồ sơ</button><button v-else :disabled="working||!state?.online||profile.valid===false||profile.id===state?.active_profile" @click="setArchived(profile,true)">Lưu trữ hồ sơ</button><small>Database riêng cho hồ sơ này; không thay bot paper chính.</small></div>
        <small v-if="!profile.archived&&profile.id===state?.active_profile">Worker đang chọn hồ sơ này nên chưa thể lưu trữ.</small><small v-else-if="!profile.archived&&!state?.online">Cần kết nối worker để xác nhận hồ sơ không đang được chọn trước khi lưu trữ.</small>
      </div>
    </article>
  </div>
</template>

<style scoped>
.paper-workspace,.paper-workspace *{text-align:left}.paper-workspace{color:var(--fg)}h3{font-size:19px;font-weight:650;margin:0 0 10px}p{color:var(--fg-2);line-height:1.55;margin:8px 0 14px;font-size:13px}.row{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:12px}.badge{padding:5px 12px;border:1px solid #20604e;background:#143b32;border-radius:20px;color:#79dfb3;font-size:11.5px;font-weight:600}.box{padding:20px;border:1px solid var(--line);background:var(--bg);border-radius:11px;margin:16px 0}.box.worker{background:linear-gradient(180deg,rgba(27,106,92,.12),var(--bg));border-color:rgba(38,139,119,.45)}.profile{padding:18px;border:1px solid var(--line);background:var(--bg-1);border-radius:10px;margin-top:16px;transition:border-color .15s}.profile:hover{border-color:var(--line-2)}.notice{background:#132b2a;border-left:3px solid var(--accent);border-radius:6px;padding:12px 15px;margin:14px 0;line-height:1.55;font-size:12.5px}.notice:empty{display:none}.notice p{margin:4px 0}.bad{background:#3c2024;border-color:#ee8989;color:#ffb4b4}button{font:inherit;font-size:12.5px;font-weight:500;padding:8px 13px;border:1px solid var(--line-2);background:var(--bg-2);color:var(--fg);border-radius:7px;cursor:pointer;transition:border-color .15s}button:hover:not(:disabled){border-color:var(--accent);color:var(--accent)}button:disabled{opacity:.4;cursor:default}.primary{background:#1b6a5c;color:#f2fff9;border-color:#268b77}.primary:hover:not(:disabled){background:#217d6d;color:#fff}small{display:block;color:var(--fg-3);line-height:1.55;font-size:12px;margin-top:6px}label{display:block;color:var(--fg-2);font-size:12px;font-weight:500;margin:12px 0}input{display:block;width:100%;font:inherit;font-size:13px;padding:9px 11px;background:var(--bg-1);color:var(--fg);border:1px solid var(--line-2);border-radius:7px;margin-top:6px}dl{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:12px 0;padding:12px;background:var(--bg);border:1px solid var(--line);border-radius:8px}dt{font-size:11px;color:var(--fg-3)}dd{margin:4px 0 0;font-weight:650;font-size:13.5px;font-variant-numeric:tabular-nums}@media(max-width:850px){dl{grid-template-columns:repeat(2,1fr)}}
</style>
