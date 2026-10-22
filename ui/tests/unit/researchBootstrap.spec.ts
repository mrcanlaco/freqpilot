import { afterEach, describe, expect, it, vi } from 'vitest';
import { effectScope } from 'vue';
import { flushPromises } from '@vue/test-utils';
import { useResearchBootstrap } from '@/composables/useResearchBootstrap';
import { ResearchConnectionError } from '@/utils/researchConnection';
const scopes:ReturnType<typeof effectScope>[]=[];
function setup(read:Parameters<typeof useResearchBootstrap>[0]){
  const scope=effectScope();scopes.push(scope);
  const state=scope.run(()=>useResearchBootstrap(read))!;
  return {scope,state};
}
afterEach(()=>{scopes.splice(0).forEach(s=>s.stop());vi.useRealTimers();});
describe('Read-only research startup recovery',()=>{
  it('recovers a transient initial failure with a bounded scheduled read',async()=>{
    vi.useFakeTimers();const read=vi.fn().mockRejectedValueOnce(new ResearchConnectionError('starting',true)).mockResolvedValueOnce(undefined);
    const {state}=setup(read);await state.start();expect(state.phase.value).toBe('waiting');
    await vi.advanceTimersByTimeAsync(1000);expect(state.phase.value).toBe('ready');expect(state.attempt.value).toBe(2);
    await vi.advanceTimersByTimeAsync(60000);expect(read).toHaveBeenCalledTimes(2);
  });
  it('stops after three attempts and permits an explicit new attempt',async()=>{
    vi.useFakeTimers();const read=vi.fn().mockRejectedValue(new ResearchConnectionError('offline',true));
    const {state}=setup(read);await state.start();await vi.advanceTimersByTimeAsync(60000);
    expect(read).toHaveBeenCalledTimes(3);expect(state.phase.value).toBe('failed');expect(vi.getTimerCount()).toBe(0);
    read.mockResolvedValueOnce(undefined);await state.start();expect(state.phase.value).toBe('ready');expect(state.attempt.value).toBe(1);
  });
  it('does not repeat a refused login or reinitialize an already editable workspace',async()=>{
    vi.useFakeTimers();const read=vi.fn().mockRejectedValueOnce(new ResearchConnectionError('login required',false)).mockResolvedValue(undefined);
    const {state}=setup(read);await state.start();await vi.advanceTimersByTimeAsync(60000);
    expect(read).toHaveBeenCalledTimes(1);expect(state.phase.value).toBe('failed');
    await state.start();await state.start();expect(read).toHaveBeenCalledTimes(2);expect(state.phase.value).toBe('ready');
  });
  it('never overlaps two initial reads',async()=>{
    let finish!:()=>void;const read=vi.fn(()=>new Promise<void>(resolve=>{finish=resolve;}));
    const {state}=setup(read);const initial=state.start();await state.start();expect(read).toHaveBeenCalledTimes(1);
    finish();await initial;expect(state.phase.value).toBe('ready');
  });
  it('cancels scheduled retries when leaving the page',async()=>{
    vi.useFakeTimers();const read=vi.fn().mockRejectedValue(new ResearchConnectionError('offline',true));
    const {state,scope}=setup(read);await state.start();scope.stop();await vi.advanceTimersByTimeAsync(60000);
    expect(read).toHaveBeenCalledTimes(1);expect(vi.getTimerCount()).toBe(0);
  });
  it('an explicit attempt replaces a scheduled retry without overlapping it',async()=>{
    vi.useFakeTimers();const read=vi.fn().mockRejectedValueOnce(new ResearchConnectionError('offline',true)).mockResolvedValue(undefined);
    const {state}=setup(read);await state.start();expect(state.phase.value).toBe('waiting');
    await state.start();await vi.advanceTimersByTimeAsync(60000);
    expect(read).toHaveBeenCalledTimes(2);expect(state.phase.value).toBe('ready');expect(vi.getTimerCount()).toBe(0);
  });
  it('invalidates a late in-flight response before its source can be applied',async()=>{
    let finish!:()=>void;let applied=0;
    const {state,scope}=setup(async({isCurrent})=>{await new Promise<void>(resolve=>{finish=resolve;});if(isCurrent())applied++;});
    const initial=state.start();scope.stop();finish();await initial;await flushPromises();
    expect(applied).toBe(0);expect(state.phase.value).not.toBe('ready');
  });
});
