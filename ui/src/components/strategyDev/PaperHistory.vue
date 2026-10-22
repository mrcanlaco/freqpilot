<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue';
import type { AxiosInstance } from 'axios';
type Event = {id:number;created_at:string;kind:string;profile_id?:string;strategy?:string;label?:string;
  body:{action?:string;outcome?:string;state?:string;previous_state?:string;request_id?:string;
    open_trades?:number;http_status?:number;configuration_changed?:boolean;observation_restored?:boolean}};
type Page = {events:Event[];next_before:number|null;started_at:string|null;note:string};
const props=defineProps<{api:AxiosInstance;strategy:string;profiles:{id:string;label:string;strategy:string}[];refreshKey:number}>();
const opened=ref(false),profile=ref(''),rows=ref<Event[]>([]),page=ref<Page>(),loading=ref(false),error=ref(''),olderPages=ref(false);
let generation=0;
const stateNames:Record<string,string>={running:'Đang chạy paper',paused:'Tạm ngừng vào lệnh',stopped:'Đã dừng',reload_config:'Đang nạp cấu hình',unavailable:'Chưa quan sát được'};
const actions:Record<string,string>={start:'Bật / tiếp tục',pause:'Tạm ngừng vào lệnh',stop:'Dừng khi đã hết vị thế'};
function title(event:Event){
  if(event.kind==='baseline')return 'Trạng thái đầu tiên được ghi nhận';
  if(event.kind==='observation_gap')return 'Không đọc được trạng thái worker';
  if(event.kind==='observation')return event.body.observation_restored?'Đã đọc lại được trạng thái':event.body.configuration_changed?'Đã quan sát cấu hình worker khác':'Trạng thái native đã thay đổi';
  if(event.kind==='action_request')return 'Yêu cầu: '+(actions[event.body.action??'']??event.body.action);
  if(event.body.outcome==='observed')return 'Đã quan sát trạng thái được yêu cầu';
  if(event.body.outcome==='error')return 'Yêu cầu kết thúc có lỗi · cần kiểm tra worker';
  return 'Đã gửi yêu cầu · chưa xác nhận trạng thái đích';
}
async function load(older=false){
  if(loading.value)return;
  const current=++generation;
  loading.value=true;error.value='';
  try{
    const {data}=await props.api.get<Page>('/studio/paper/history',{params:{limit:30,strategy:props.strategy||undefined,profile_id:profile.value||undefined,before:older?page.value?.next_before:undefined}});
    if(current!==generation)return;
    rows.value=older?[...rows.value,...data.events.filter(e=>!rows.value.some(r=>r.id===e.id))]:data.events;
    page.value=data;olderPages.value=older;
  }catch(e){if(current===generation){const failure=e as {response?:{data?:{detail?:unknown}};message?:string};error.value=String(failure.response?.data?.detail??failure.message??e);}}
  finally{if(current===generation)loading.value=false;}
}
async function toggle(){opened.value=!opened.value;if(opened.value)await load();}
watch([()=>props.strategy,profile],()=>{generation++;loading.value=false;rows.value=[];page.value=undefined;olderPages.value=false;if(opened.value)void load();});
watch(()=>props.refreshKey,()=>{if(opened.value&&!loading.value&&!olderPages.value)void load();});
onUnmounted(()=>{generation++;});
</script>

<template>
  <section class="paper-history" aria-label="Lịch sử paper">
    <div class="row"><h3>Lịch sử thao tác & trạng thái</h3><button @click="toggle">{{opened?'Thu gọn lịch sử':'Xem lịch sử paper'}}</button></div>
    <p>Ghi bền vững theo hồ sơ từ khi có tính năng này. Yêu cầu đã gửi không đồng nghĩa worker đã đổi trạng thái; không dựng lại các phiên cũ chưa quan sát.</p>
    <template v-if="opened">
      <div class="row"><label>Hồ sơ<select v-model="profile"><option value="">Tất cả hồ sơ{{strategy?' của '+strategy:''}}</option><option v-for="item in profiles" :key="item.id" :value="item.id">{{item.label}} · {{item.strategy}}</option></select></label><button :disabled="loading" @click="load()">Tải lại lịch sử</button></div>
      <p v-if="error" class="error" role="alert">{{error}} Các thao tác paper không được gửi lại tự động.</p>
      <p v-if="!rows.length&&!loading&&!error">Chưa có sự kiện được ghi cho lựa chọn này.</p>
      <ol aria-label="Sự kiện paper"><li v-for="event in rows" :key="event.id">
        <div class="row"><b>{{title(event)}}</b><time :datetime="event.created_at">{{new Date(event.created_at).toLocaleString('vi-VN')}}</time></div>
        <p>{{event.label??'Worker nghiên cứu'}}<template v-if="event.strategy"> · {{event.strategy}}</template><small v-if="event.profile_id"> · {{event.profile_id.slice(0,10)}}</small></p>
        <p v-if="event.body.state">{{stateNames[event.body.state]??event.body.state}}<template v-if="typeof event.body.open_trades==='number'"> · {{event.body.open_trades}} vị thế mở tại lần đọc</template></p>
        <small v-if="event.body.request_id">Yêu cầu {{event.body.request_id.slice(0,10)}}<template v-if="event.body.http_status"> · HTTP {{event.body.http_status}}</template></small>
        <small v-if="event.kind==='observation_gap'">Đây là khoảng thiếu quan sát, không xác nhận worker đã dừng.</small>
      </li></ol>
      <p v-if="loading" role="status">Đang tải lịch sử…</p>
      <button v-if="page?.next_before" :disabled="loading" @click="load(true)">Xem sự kiện cũ hơn</button>
      <small v-if="page" class="note">{{page.note}} Thời gian hiển thị theo trình duyệt.</small>
    </template>
  </section>
</template>

<style scoped>
.paper-history{padding:20px;border:1px solid var(--line);border-radius:10px;margin:20px 0;text-align:left}h3{font-size:20px;margin:0}p{line-height:1.6;color:var(--fg-2);margin:10px 0}.row{display:flex;align-items:center;flex-wrap:wrap;gap:12px}.row time{margin-left:auto;color:var(--fg-3);font-size:12px}button,select{font:inherit;font-size:13px;padding:9px 13px;border:1px solid var(--line-2);background:var(--bg-2);color:var(--fg);border-radius:7px}button{cursor:pointer}button:disabled{opacity:.4;cursor:default}label{display:grid;gap:6px;margin:12px 0;font-size:12px}ol{list-style:none;padding:0;margin:18px 0}li{border-left:2px solid var(--accent);padding:14px 16px;margin:12px 0;background:var(--bg-2);border-radius:6px}small{color:var(--fg-3);font-size:12px;line-height:1.6}.note{display:block;margin-top:18px}.error{color:#ffb4b4;background:#3c2024;padding:12px;border-radius:6px}
</style>
