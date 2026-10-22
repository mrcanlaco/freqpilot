import { describe, expect, it, vi } from 'vitest';
import { discoverResearchConnection, temporaryResearchFailure } from '@/utils/researchConnection';

const library={product:'FreqPilot',engine:'2026.9',dry_run:true,strategies:[]};
const bot=(id:string,webserver=true)=>({botId:id,isWebserverMode:webserver,getState:vi.fn(async()=>({runmode:webserver?'webserver':'dry_run'}))});
describe('Research backend discovery',()=>{
  it('skips the Ultimate comparison service and selects only a compatible dry-run FreqPilot workspace',async()=>{
    const ultimate=bot('ultimate'),main=bot('main'),paper=bot('paper',false);
    const get=vi.fn(async(path:string)=>({data:library}));
    const legacy=vi.fn(async()=>{throw {response:{status:404}};});
    const selected=await discoverResearchConnection([ultimate,paper,main], b=>({get:b.botId==='ultimate'?legacy:get}), 'ultimate');
    expect(selected).toBe(main);expect(legacy).toHaveBeenCalledWith('/studio/library');
    expect(get).toHaveBeenCalledTimes(1);
  });
  it('does not treat an unregistered connection as a network problem or probe a trading bot for research',async()=>{
    await expect(discoverResearchConnection([],()=>({get:vi.fn()}))).rejects.toMatchObject({retryable:false});
    const api=vi.fn();await expect(discoverResearchConnection([bot('paper',false)],()=>({get:api}))).rejects.toMatchObject({retryable:false});
    expect(api).not.toHaveBeenCalled();
  });
  it('rejects wrong branding, unsupported engine versions and live-mode responses',async()=>{
    for(const data of [{...library,product:'Other'},{...library,engine:'2026.10'},{...library,dry_run:false},{...library,strategies:null}]){
      await expect(discoverResearchConnection([bot('candidate')],()=>({get:vi.fn(async()=>({data}))}))).rejects.toMatchObject({retryable:false});
    }
  });
  it('keeps authentication failures distinct from transient startup failures',async()=>{
    const auth=bot('auth');auth.getState.mockRejectedValueOnce({response:{status:401}});
    const authApi=vi.fn();await expect(discoverResearchConnection([auth],()=>({get:authApi}))).rejects.toMatchObject({retryable:false});
    expect(authApi).not.toHaveBeenCalled();
    const cold=bot('cold');cold.getState.mockRejectedValueOnce({response:{status:503}});
    await expect(discoverResearchConnection([cold],()=>({get:vi.fn(async()=>{throw {response:{status:503}};})}))).rejects.toMatchObject({retryable:true});
    expect(temporaryResearchFailure({response:{status:403},message:'timeout'})).toBe(false);
  });
  it('can find a good research service even if another configured service needs a login',async()=>{
    const auth=bot('old'),main=bot('main');auth.getState.mockRejectedValueOnce({response:{status:401}});
    expect(await discoverResearchConnection([auth,main],()=>({get:vi.fn(async()=>({data:library}))}))).toBe(main);
  });
  it('stops probing after the view has gone away',async()=>{
    let current=true,finish!:(value:{runmode:string})=>void;
    const source=bot('main');source.getState.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
    const get=vi.fn();const pending=discoverResearchConnection([source],()=>({get}),undefined,()=>current);
    current=false;finish({runmode:'webserver'});
    await expect(pending).rejects.toMatchObject({retryable:false});expect(get).not.toHaveBeenCalled();
  });
});
