import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import ResearchConnectionNotice from '@/components/strategyDev/ResearchConnectionNotice.vue';
describe('Research connection recovery panel',()=>{
  it('allows explicit retry after failure without telling the user to add a duplicate bot',async()=>{
    const wrapper=mount(ResearchConnectionNotice,{props:{phase:'failed',attempt:3,maxAttempts:3,error:'Dịch vụ đang khởi động lại.',hasBots:true}});
    expect(wrapper.text()).not.toContain('Thêm Backtest');
    await wrapper.findAll('button').find(b=>b.text()==='Thử kết nối lại')!.trigger('click');
    expect(wrapper.emitted('retry')).toHaveLength(1);
  });
  it('prevents overlapping requests while loading and shows the bounded retry count',()=>{
    const wrapper=mount(ResearchConnectionNotice,{props:{phase:'loading',attempt:2,maxAttempts:3,error:'',hasBots:true}});
    expect(wrapper.text()).toContain('lần 2/3');
    expect(wrapper.findAll('button').find(b=>b.text()==='Thử kết nối lại')!.attributes('disabled')).toBeDefined();
  });
  it('offers initial setup only when the registry really has no connections',async()=>{
    const wrapper=mount(ResearchConnectionNotice,{props:{phase:'failed',attempt:1,maxAttempts:3,error:'',hasBots:false}});
    expect(wrapper.text()).toContain('Thêm Backtest');expect(wrapper.text()).not.toContain('Thử kết nối lại');
    await wrapper.get('button').trigger('click');expect(wrapper.emitted('settings')).toHaveLength(1);
  });
});
