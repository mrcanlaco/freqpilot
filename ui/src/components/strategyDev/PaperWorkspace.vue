<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import type { AxiosInstance } from 'axios';
import { registerPaperLogin } from '@/composables/loginInfo';
import { useBotStore } from '@/stores/ftbotwrapper';
import { botKeyFromApiUrl } from '@/datasource/protocol/identity';
import type { StrategyPreset } from '@/utils/strategyLibrary';
import { useDataSource } from '@/composables/useDataSource';

type Profile = { id:string; label:string; strategy:string; revision:string; run_id:string; warnings:string[];preset?:StrategyPreset;valid?:boolean;error?:string;
  settings:{pairs:string[];timeframe:string;wallet:number;stake:number|string;max_open_trades:number;fee:number};
  summary:{total_trades?:number;profit_total_abs?:number} };
type PaperState = {online:boolean;state:string;error?:string;active_profile?:string|null;open_trades:number|null;profiles:Profile[]};
const props=defineProps<{api:AxiosInstance;strategy:string;revision:string;run?:{id:string;strategy:string;revision:string;status:string}}>();
defineEmits<{openResults:[]}>();
const router=useRouter(),bots=useBotStore();
const dataSource=useDataSource();
const state=ref<PaperState>(), working=ref(false),message=ref(''),bad=ref(false),label=ref('');
let poll:ReturnType<typeof setInterval>|undefined;
let refreshFailed=false;
const profiles=computed(()=>state.value?.profiles.filter(p=>p.strategy===props.strategy)??[]);
const active=computed(()=>state.value?.profiles.find(p=>p.id===state.value?.active_profile));
const statusNames:Record<string,string>={running:'Đang chạy paper',paused:'Tạm ngừng vào lệnh · vẫn quản lý thoát lệnh',stopped:'Đã dừng',unavailable:'Chưa kết nối'};
function errorText(e:unknown){const err=e as {response?:{data?:{detail?:unknown}};message?:string};return String(err.response?.data?.detail??err.message??e);}
async function refresh(){try{state.value=(await props.api.get('/studio/paper')).data;if(refreshFailed){message.value='';bad.value=false;refreshFailed=false;}}catch(e){refreshFailed=true;message.value=errorText(e);bad.value=true;}}
async function action(fn:()=>Promise<void>){working.value=true;bad.value=false;try{await fn();await refresh();}catch(e){message.value=errorText(e);bad.value=true;}finally{working.value=false;}}
async function prepare(){if(!props.run)return;await action(async()=>{await props.api.post('/studio/paper/profiles',{run_id:props.run!.id,label:label.value});message.value='Đã chuẩn bị mã và database paper riêng. Bot chưa được bật.';});}
async function start(profile:Profile){await action(async()=>{message.value='Đang nạp worker paper; bước này có thể mất khoảng một phút…';await props.api.post('/studio/paper/profiles/'+profile.id+'/start',{}, {timeout:150000});message.value='Đã bật paper cho '+profile.label+'.';});}
async function control(kind:'pause'|'stop'){await action(async()=>{message.value=kind==='pause'?'Đang tạm ngừng vào lệnh…':'Đang dừng worker sau khi kiểm tra vị thế…';await props.api.post('/studio/paper/'+kind,{}, {timeout:90000});message.value=kind==='pause'?'Đã ngừng vào lệnh mới, tiếp tục quản lý thoát lệnh.':'Đã dừng worker paper khi không còn vị thế mở.';});}
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
      <div class="row"><b>{{statusNames[state?.state??'unavailable']??state?.state}}</b><span v-if="state?.online" class="badge">Kết nối 8095</span></div>
      <p v-if="active">Hồ sơ đang chọn: <strong>{{active.label}}</strong> · {{active.strategy}} · mã {{active.revision.slice(0,10)}}.</p>
      <p v-else-if="state?.online">Worker đã sẵn sàng, chưa chọn hồ sơ nghiên cứu.</p>
      <p v-if="state?.error" class="notice bad">{{state.error}}</p>
      <p v-if="state?.online">Vị thế mô phỏng đang mở: <b>{{state.open_trades}}</b>.</p>
      <div class="row"><button :disabled="working||!state?.online||!active" @click="control('pause')">Tạm ngừng vào lệnh</button><button :disabled="working||!state?.online||!!state.open_trades" @click="control('stop')">Dừng khi đã hết vị thế</button><button class="primary" :disabled="working||!state?.online||!active" @click="monitor">Mở giám sát paper</button></div>
      <small>Đổi hồ sơ cần hết vị thế mở. Tạm ngừng vẫn cho engine quản lý thoát lệnh; bật lại cùng hồ sơ sẽ dùng tiếp database cũ. Sau khi dịch vụ khởi động lại, worker không tự vào lệnh mới. Nếu còn vị thế, worker tiếp tục quản lý thoát lệnh ở chế độ tạm ngừng; nếu không còn vị thế thì dừng.</small><p class="notice">Chế độ tạm ngừng chặn vào lệnh mới và tăng vị thế. Giảm vị thế hoặc chốt lời từng phần vẫn được xử lý theo chiến lược, cùng stoploss, ROI và tín hiệu thoát.</p>
    </article>
    <article class="box">
      <h3>1 · Chuẩn bị từ bản đã backtest</h3>
      <template v-if="run?.strategy===strategy&&run.status==='success'">
        <p>Hồ sơ {{run.id.slice(0,10)}} · {{strategy}} · mã {{run.revision.slice(0,10)}}. Sao chép mã từ gói lưu, giữ nguyên quy tắc tín hiệu, dùng lớp paper giới hạn leverage 1x.</p>
        <p v-if="run.revision!==revision" class="notice">Mã hiện tại khác mã của báo cáo này. Paper sẽ dùng phiên bản trong gói backtest.</p>
        <label>Tên hồ sơ paper<input v-model="label" maxlength="70" :placeholder="strategy+' paper'" /></label>
        <button class="primary" :disabled="working" @click="prepare">Chuẩn bị hồ sơ paper</button>
      </template>
      <template v-else><p>Chọn một kết quả có gói mã và dữ liệu đã lưu trước khi chuẩn bị paper.</p><button @click="$emit('openResults')">Mở kết quả backtest</button></template>
    </article>
    <article class="box"><h3>2 · Xem cấu hình rồi bật paper</h3>
      <p v-if="!profiles.length">Chưa có hồ sơ paper cho {{strategy}}.</p>
      <div v-for="profile in profiles" :key="profile.id" class="profile">
        <div class="row"><b>{{profile.label}}</b><span v-if="profile.id===state?.active_profile" class="badge">Hồ sơ đang chọn</span></div>
        <p>{{profile.settings.pairs.join(' · ')}} · {{profile.settings.timeframe}} · isolated 1x</p>
        <dl><div><dt>Vốn mô phỏng</dt><dd>{{profile.settings.wallet}} USDT</dd></div><div><dt>Stake đề xuất</dt><dd>{{profile.settings.stake}} USDT</dd></div><div><dt>Lệnh mở tối đa</dt><dd>{{profile.settings.max_open_trades}}</dd></div><div><dt>Phí mỗi chiều</dt><dd>{{(profile.settings.fee*100).toFixed(3)}}%</dd></div></dl>
        <p v-if="profile.preset">Bộ tham số từ backtest: <b>{{profile.preset.label}}</b> · {{profile.preset.native_sha256.slice(0,10)}}. Không lấy giá trị mới trong thư viện.</p><p>Backtest nguồn: {{profile.summary.total_trades??0}} lệnh · {{profile.summary.profit_total_abs?.toFixed(3)??'—'}} USDT · mã {{profile.revision.slice(0,10)}}.</p>
        <p v-if="profile.valid===false" class="notice bad">{{profile.error}} Hãy chuẩn bị một hồ sơ mới.</p><div class="notice"><p v-for="warning in profile.warnings" :key="warning">{{warning}}</p></div>
        <div class="row"><button class="primary" :disabled="working||profile.valid===false||!state?.online||(!!state.open_trades&&state.active_profile!==profile.id)" @click="start(profile)">{{profile.id===state?.active_profile?'Bật / tiếp tục paper':'Bật paper hồ sơ này'}}</button><small>Database riêng cho hồ sơ này; không thay bot paper chính.</small></div>
      </div>
    </article>
  </div>
</template>

<style scoped>
.paper-workspace{color:var(--fg)}h3{font-size:20px;margin:0 0 12px}p{color:var(--fg-2);line-height:1.6;margin:10px 0 16px}.row{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:14px}.badge{padding:6px 12px;border:1px solid #20604e;background:#143b32;border-radius:20px;color:#79dfb3;font-size:12px}.box{padding:20px;border:1px solid var(--line);border-radius:10px;margin:20px 0}.profile{padding:18px;border:1px solid var(--line);border-radius:8px;margin-top:20px}.notice{background:#132b2a;border-left:3px solid var(--accent);padding:12px 16px;margin:18px 0;line-height:1.6;font-size:13px}.notice p{margin:4px 0}.bad{background:#3c2024;border-color:#ee8989;color:#ffb4b4}button{font:inherit;font-size:13px;padding:9px 13px;border:1px solid var(--line-2);background:var(--bg-2);color:var(--fg);border-radius:7px;cursor:pointer}button:disabled{opacity:.4;cursor:default}.primary{background:#1b6a5c;color:#f2fff9;border-color:#268b77}small{color:var(--fg-3);line-height:1.6;font-size:12px}label{display:block;color:var(--fg-2);font-size:12px;margin:12px 0}input{display:block;width:100%;font:inherit;padding:10px;background:var(--bg);color:var(--fg);border:1px solid var(--line-2);border-radius:6px;margin-top:7px}dl{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}dt{font-size:11px;color:var(--fg-3)}dd{margin:6px 0;font-weight:600}@media(max-width:850px){dl{grid-template-columns:repeat(2,1fr)}}
</style>
