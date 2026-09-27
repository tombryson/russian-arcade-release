import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, bindUserSession, endOnLeave, upload } from './learning-api';

afterEach(()=>{
  bindUserSession(undefined,'');
  vi.unstubAllGlobals();
});

describe('Page identity binding',()=>{
  it('keeps every request bound to its original profile after a late response refreshes CSRF',async()=>{
    bindUserSession('profile-a','old-token','hosted:original-account');
    const fetch=vi.fn((_url:string,_options?:RequestInit)=>Promise.resolve({ok:true,json:async()=>({
      profile_id:'profile-b',profile:{id:'profile-b',display_name:'Other'},csrf_token:'new-token',session_scope:'hosted:other-account',
    })}));
    vi.stubGlobal('fetch',fetch);

    await api('/api/v1/progression');
    await api('/api/v1/progression/preferences',{level:'A2'});
    await upload('/api/v1/conversations/one/turns',new FormData());
    endOnLeave('/api/v1/live-conversations/one/end');

    expect(fetch).toHaveBeenCalledTimes(4);
    for (const [, options] of fetch.mock.calls) {
      expect(options?.headers).toMatchObject({'X-Profile-ID':'profile-a','X-Account-Scope':'hosted:original-account'});
    }
    for (const [, options] of fetch.mock.calls.slice(1)) {
      expect(options?.headers).toMatchObject({'X-CSRF-Token':'new-token'});
    }
    expect(fetch.mock.calls[3][1]).toMatchObject({keepalive:true,method:'POST'});
  });
});

it('does not reload the progression summary for each autosaved answer draft',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>({})})));
  const changed=vi.fn();window.addEventListener('lingo:progression',changed);
  try {
    await api('/api/v1/course/checkpoints/letter/draft',{answers:{q:'a'},revision:0});
    expect(changed).not.toHaveBeenCalled();
    await api('/api/v1/course/checkpoints/letter/answer',{answers:{q:'a'},submission_id:'checked'});
    expect(changed).toHaveBeenCalledOnce();
  } finally {window.removeEventListener('lingo:progression',changed);}
});
