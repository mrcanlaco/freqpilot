import { describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import type { AxiosInstance } from 'axios';
import PaperHistory from '@/components/strategyDev/PaperHistory.vue';
const profile={id:'a'.repeat(32),label:'Quan sát BTC',strategy:'Sample'};
const event={id:3,created_at:'2026-10-22T01:00:00Z',kind:'baseline',profile_id:profile.id,strategy:'Sample',label:profile.label,body:{state:'stopped',open_trades:0}};
function setup(){
  const api={get:vi.fn(async()=>({data:{events:[event],next_before:null,started_at:event.created_at,note:'Không dựng lại thời gian chưa quan sát.'}})),post:vi.fn()};
  const wrapper=mount(PaperHistory,{props:{api:api as unknown as AxiosInstance,strategy:'',profiles:[profile],refreshKey:0}});
  return {api,wrapper};
}
describe('Paper lifecycle history',()=>{
  it('only reads on opening and never sends a trading or lifecycle command',async()=>{
    const {api,wrapper}=setup();expect(api.get).not.toHaveBeenCalled();
    await wrapper.get('button').trigger('click');await flushPromises();
    expect(api.get).toHaveBeenCalledWith('/studio/paper/history',{params:expect.objectContaining({limit:30})});
    expect(wrapper.text()).toContain('Trạng thái đầu tiên được ghi nhận');
    expect(wrapper.text()).toContain('0 vị thế mở tại lần đọc');expect(api.post).not.toHaveBeenCalled();
  });
  it('discards a late result for a different profile filter',async()=>{
    const {api,wrapper}=setup();let complete!:(value:{data:{events:typeof event[];next_before:null;started_at:string;note:string}})=>void;
    api.get.mockImplementationOnce(()=>new Promise(resolve=>{complete=resolve;}));
    await wrapper.get('button').trigger('click');
    api.get.mockResolvedValueOnce({data:{events:[],next_before:null,started_at:'today',note:'filtered'}});
    await wrapper.get('select').setValue(profile.id);await flushPromises();
    complete({data:{events:[event],next_before:null,started_at:'earlier',note:'old'}});await flushPromises();
    expect(wrapper.text()).toContain('Chưa có sự kiện');expect(wrapper.text()).not.toContain('Trạng thái đầu tiên được ghi nhận');
  });
  it('uses a stable older cursor and preserves the rows while reading older pages',async()=>{
    const {api,wrapper}=setup();
    api.get.mockResolvedValueOnce({data:{events:[event],next_before:3,started_at:'start',note:'history'}});
    await wrapper.get('button').trigger('click');await flushPromises();
    api.get.mockResolvedValueOnce({data:{events:[{...event,id:2}],next_before:null,started_at:'start',note:'history'}});
    await wrapper.findAll('button').find(b=>b.text()==='Xem sự kiện cũ hơn')!.trigger('click');await flushPromises();
    expect(api.get.mock.lastCall?.[1]).toMatchObject({params:{before:3}});
    expect(wrapper.findAll('li')).toHaveLength(2);
    await wrapper.setProps({refreshKey:1});await flushPromises();
    expect(api.get).toHaveBeenCalledTimes(2);
  });
  it('distinguishes an observation gap from a stopped bot and an unconfirmed request from success',async()=>{
    const {api,wrapper}=setup();
    api.get.mockResolvedValueOnce({data:{events:[{...event,kind:'observation_gap',body:{state:'unavailable'}},{...event,id:2,kind:'action_result',body:{action:'start',outcome:'unconfirmed'}}],next_before:null,started_at:'start',note:'history'}});
    await wrapper.get('button').trigger('click');await flushPromises();
    expect(wrapper.text()).toContain('không xác nhận worker đã dừng');
    expect(wrapper.text()).toContain('chưa xác nhận trạng thái đích');
    expect(wrapper.text()).not.toContain('Đã quan sát trạng thái được yêu cầu');expect(api.post).not.toHaveBeenCalled();
  });
  it('retains the event list on read errors and never retries an action',async()=>{
    const {api,wrapper}=setup();await wrapper.get('button').trigger('click');await flushPromises();
    api.get.mockRejectedValueOnce({response:{data:{detail:'history unavailable'}}});
    await wrapper.findAll('button').find(b=>b.text()==='Tải lại lịch sử')!.trigger('click');await flushPromises();
    expect(wrapper.get('[role=alert]').text()).toContain('history unavailable');
    expect(wrapper.findAll('li')).toHaveLength(1);expect(api.post).not.toHaveBeenCalled();
  });
});
