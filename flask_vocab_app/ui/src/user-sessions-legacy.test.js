import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {describe,expect,it,vi} from 'vitest';
import {waitFor} from '@testing-library/preact';
const script=readFileSync('../static/js/user_sessions.js','utf8');
function setup(path='/') {
  const handlers={};
  const location={pathname:path,reload:vi.fn(),assign:vi.fn()};
  const replaceState=vi.fn();
  const state={profile:{id:'a'}};
  runInNewContext(script,{
    document:{visibilityState:'visible',querySelector:()=>({dataset:{profileId:'a'}}),addEventListener:vi.fn()},
    window:{location,history:{replaceState},addEventListener:(name,fn)=>{handlers[name]=fn;}},
    fetch:async()=>({ok:true,json:async()=>({mode:'personal',profile:state.profile})}),
    localStorage:{setItem:vi.fn()},setInterval:vi.fn(),setTimeout:vi.fn()
  });
  return {handlers,location,replaceState,state};
}
describe('Profile changes across browser tabs',()=>{
  it('forces a real reload when the app is already at /',async()=>{
    const {handlers,state,location,replaceState}=setup();
    state.profile={id:'b'};handlers.storage({key:'russian-arcade-session'});
    await waitFor(()=>expect(location.reload).toHaveBeenCalledOnce());
    expect(replaceState).toHaveBeenCalledWith(null,'','/#home');
    expect(location.assign).not.toHaveBeenCalled();
  });
  it('leaves matching profiles alone and returns a legacy activity home after logout',async()=>{
    const {handlers,state,location}=setup('/writing');
    handlers.storage({key:'russian-arcade-session'});
    await new Promise(resolve=>setTimeout(resolve,0));
    expect(location.assign).not.toHaveBeenCalled();
    state.profile=null;handlers.storage({key:'russian-arcade-session'});
    await waitFor(()=>expect(location.assign).toHaveBeenCalledWith('/#home'));
  });
});
