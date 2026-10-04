import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/preact';
import {Practice} from './Practice';

const entries = [{kind:'word',text:'аптекой',meaning_en:'pharmacy',sentence:'Анна стоит перед аптекой.'},
  {kind:'phrase',text:'перед аптекой',meaning_en:'in front of the pharmacy'}];
const initial = {id:'s1',profile_id:'p1',title:'Reading',revision:0,status:'active',completed_items:0,total_items:3,attempts:[],
  item:{id:'i1',type:'choice',prompt:'Where is Anna?',passage:'Анна стоит перед аптекой.',has_hint:true,
    has_passage_support:true,choices:[{id:'a',text:'Перед аптекой.'}]}};
const revealed = {...initial,revision:1,item:{...initial.item,passage_support:entries}};
const response = (value:unknown,ok=true) => Promise.resolve({ok,json:async()=>value});
beforeEach(()=>vi.spyOn(HTMLMediaElement.prototype,'pause').mockImplementation(()=>{}));
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});

it('opens compact word support only after its receipt, collapses without another request, and preserves revision',async()=>{
  const fetch=vi.fn((url:string,_options?:RequestInit)=>response(url.endsWith('/passage-help') ? revealed : initial));
  vi.stubGlobal('fetch',fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={()=>{}}/>);
  const toggle=await screen.findByRole('button',{name:'Words and phrases'});
  expect(toggle.getAttribute('aria-expanded')).toBe('false');
  expect(screen.queryByText('pharmacy')).toBeNull();
  fireEvent.click(toggle);
  await screen.findByText('pharmacy');
  expect(JSON.parse(String(fetch.mock.calls[1][1]?.body))).toMatchObject({expected_revision:0,item_id:'i1'});
  expect(toggle.getAttribute('aria-expanded')).toBe('true');
  fireEvent.click(toggle);
  expect(screen.queryByText('pharmacy')).toBeNull();
  fireEvent.click(toggle);
  expect(screen.getByText('pharmacy')).toBeTruthy();
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(screen.queryByText('The answer is')).toBeNull();
});

it('restores explicitly disclosed support on reload and does not add it to old sessions',async()=>{
  const fetch=vi.fn((url:string)=>response(url.endsWith('/old') ? {...initial,id:'old',item:{...initial.item,has_passage_support:undefined}} : revealed));
  vi.stubGlobal('fetch',fetch);
  const view=render(<Practice sessionId="s1" profileId="p1" onFinish={()=>{}}/>);
  await screen.findByText('pharmacy');
  view.rerender(<Practice sessionId="old" profileId="p1" onFinish={()=>{}}/>);
  await waitFor(()=>expect(screen.queryByRole('button',{name:'Words and phrases'})).toBeNull());
  expect(screen.queryByText('pharmacy')).toBeNull();
});

it('keeps listening word support behind explicit transcript disclosure',async()=>{
  const listening={...initial,item:{...initial.item,passage:undefined,type:'listening_choice',has_transcript:true,transcript:null,listened:false}};
  const transcript={...listening,revision:1,item:{...listening.item,transcript:initial.item.passage}};
  const fetch=vi.fn((url:string)=>response(url.endsWith('/transcript') ? transcript : url.endsWith('/passage-help') ? {...transcript,revision:2,item:{...transcript.item,passage_support:entries}} : listening));
  vi.stubGlobal('fetch',fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={()=>{}}/>);
  const button=await screen.findByRole('button',{name:'Show transcript'});
  expect(screen.queryByRole('button',{name:'Words and phrases'})).toBeNull();
  expect(screen.queryByText('pharmacy')).toBeNull();
  fireEvent.click(button);
  fireEvent.click(await screen.findByRole('button',{name:'Words and phrases'}));
  await screen.findByText('pharmacy');
  expect(fetch.mock.calls.map(([url])=>url)).toEqual(['/api/v1/learning-sessions/s1','/api/v1/learning-sessions/s1/transcript','/api/v1/learning-sessions/s1/passage-help']);
});

it('retries an uncertain disclosure with the identical command and keeps answers blocked until saved',async()=>{
  let count=0;
  const fetch=vi.fn((url:string,_options?:RequestInit)=>url.endsWith('/passage-help') && ++count===1 ? Promise.reject(new TypeError('network')) : response(url.endsWith('/passage-help') ? revealed : initial));
  vi.stubGlobal('fetch',fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={()=>{}}/>);
  fireEvent.click(await screen.findByRole('button',{name:'Words and phrases'}));
  await screen.findByText('Word support could not open. Try again.');
  expect((screen.getByRole('button',{name:'Перед аптекой.'}) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.queryByText('pharmacy')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Try saving again'}));
  await screen.findByText('pharmacy');
  expect(fetch.mock.calls[1][1]?.body).toBe(fetch.mock.calls[2][1]?.body);
});

it('does not erase a typed draft when optional support is requested',async()=>{
  const form={...initial,draft_enabled:true,draft:{response:{text:''},revision:0},item:{...initial.item,type:'controlled_text',choices:undefined}};
  const fetch=vi.fn((url:string,_options?:RequestInit)=>response(url.endsWith('/draft') ? {draft:{response:{text:'аптека'},revision:1}}
    : url.endsWith('/passage-help') ? {...form,revision:1,draft:{response:{text:'аптека'},revision:1},item:{...form.item,passage_support:entries}} : form));
  vi.stubGlobal('fetch',fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={()=>{}}/>);
  const input=await screen.findByRole('textbox');
  fireEvent.input(input,{target:{value:'аптека'}});
  fireEvent.click(screen.getByRole('button',{name:'Words and phrases'}));
  await screen.findByText('pharmacy');
  expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('аптека');
  expect(fetch.mock.calls.filter(([,options])=>options?.method==='POST').map(([url])=>url)).toEqual(['/api/v1/learning-sessions/s1/draft','/api/v1/learning-sessions/s1/passage-help']);
});
