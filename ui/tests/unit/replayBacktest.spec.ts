import { describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import type { AxiosInstance } from 'axios';
import ReplayBacktest from '@/components/strategyDev/ReplayBacktest.vue';

const run = {id:'original-id',strategy:'Sample',status:'success'};
const preview = {id:run.id,strategy:run.strategy,revision:'source-a',artifact_sha256:'a'.repeat(64),
  settings:{timerange:'20260918-20261022',timeframe:'1h',timeframe_detail:'1m',dry_run_wallet:1000,stake_amount:'100',max_open_trades:2},
  pairs:['BTC/USDT:USDT','ETH/USDT:USDT'],fee:0.0005,input_files:33,input_bytes:4000,engine:'2026.9',
  note:'Metadata thị trường Binance vẫn được engine lấy qua mạng; không bảo đảm kết quả khớp.'};
function setup(){
  const api={get:vi.fn(async()=>({data:preview})),post:vi.fn(async()=>({data:{id:'new-id'}}))};
  const onAccepted=vi.fn();
  const wrapper=mount(ReplayBacktest,{props:{api:api as unknown as AxiosInstance,run,busy:false,onAccepted}});
  return {api,wrapper,onAccepted};
}
describe('Archived backtest replay',()=>{
  it('only reviews on first click and starts explicitly with the reviewed archive fingerprint',async()=>{
    const {api,wrapper,onAccepted}=setup();
    expect(api.get).not.toHaveBeenCalled();expect(api.post).not.toHaveBeenCalled();
    await wrapper.get('button').trigger('click');await flushPromises();
    expect(api.get).toHaveBeenCalledWith('/studio/runs/original-id/replay');
    expect(wrapper.text()).toContain('Backtest chưa bắt đầu');
    expect(wrapper.text()).toContain('không bảo đảm kết quả khớp');
    expect(wrapper.text()).toContain('0,05%');
    expect(api.post).not.toHaveBeenCalled();
    await wrapper.findAll('button').find(b=>b.text()==='Chạy bản sao & đối chiếu')!.trigger('click');await flushPromises();
    expect(api.post).toHaveBeenCalledWith('/studio/runs/original-id/replay',{artifact_sha256:'a'.repeat(64)});
    expect(onAccepted).toHaveBeenCalledWith('new-id');
  });
  it('discards a late preview after another report is selected',async()=>{
    const {api,wrapper}=setup();let complete!:(value:{data:typeof preview})=>void;
    api.get.mockImplementationOnce(()=>new Promise(resolve=>{complete=resolve;}));
    await wrapper.get('button').trigger('click');
    await wrapper.setProps({run:{...run,id:'other-id'}});complete({data:preview});await flushPromises();
    expect(wrapper.text()).not.toContain('Xem lại trước khi chạy');expect(api.post).not.toHaveBeenCalled();
  });
  it('shows a rejected archive and requires another review instead of retrying automatically',async()=>{
    const {api,wrapper,onAccepted}=setup();await wrapper.get('button').trigger('click');await flushPromises();
    api.post.mockRejectedValueOnce({response:{data:{detail:'Gói đã thay đổi'}}});
    await wrapper.findAll('button').find(b=>b.text()==='Chạy bản sao & đối chiếu')!.trigger('click');await flushPromises();
    expect(wrapper.get('[role=alert]').text()).toContain('Gói đã thay đổi');
    expect(wrapper.text()).not.toContain('Xem lại trước khi chạy');expect(api.post).toHaveBeenCalledTimes(1);
    expect(onAccepted).not.toHaveBeenCalled();
  });
  it('blocks a reviewed launch while another native job is running',async()=>{
    const {api,wrapper}=setup();await wrapper.get('button').trigger('click');await flushPromises();
    await wrapper.setProps({busy:true});
    expect(wrapper.findAll('button').find(b=>b.text()==='Chạy bản sao & đối chiếu')!.attributes('disabled')).toBeDefined();
    expect(api.post).not.toHaveBeenCalled();
  });
  it('reports an accepted native job to its owner after the report panel unmounts',async()=>{
    const {api,wrapper,onAccepted}=setup();await wrapper.get('button').trigger('click');await flushPromises();
    let complete!:(value:{data:{id:string}})=>void;
    api.post.mockImplementationOnce(()=>new Promise(resolve=>{complete=resolve;}));
    await wrapper.findAll('button').find(b=>b.text()==='Chạy bản sao & đối chiếu')!.trigger('click');
    wrapper.unmount();complete({data:{id:'accepted-after-leaving'}});await flushPromises();
    expect(onAccepted).toHaveBeenCalledWith('accepted-after-leaving');
  });
  it('qualifies matching empty results and shows exact differing trade counts',async()=>{
    const {wrapper}=setup();
    await wrapper.setProps({run:{...run,replay_of:{id:'parent-id',artifact_sha256:'a'.repeat(64)},replay_comparison:{status:'matched',source_id:'parent-id',source_trades:0,replayed_trades:0}}});
    expect(wrapper.text()).toContain('chưa kiểm tra được hành vi khớp lệnh');
    await wrapper.setProps({run:{...run,replay_of:{id:'parent-id',artifact_sha256:'a'.repeat(64)},replay_comparison:{status:'different',source_id:'parent-id',source_trades:2,replayed_trades:1,different_trades:2,different_metrics:['profit_total_abs']}}});
    expect(wrapper.text()).toContain('2 lệnh khác hoặc thiếu');expect(wrapper.text()).toContain('profit_total_abs');
    expect(wrapper.text()).not.toContain('Khớp toàn bộ');
  });
});
