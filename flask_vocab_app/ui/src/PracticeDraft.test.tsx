import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/preact';
import {Practice} from './Practice';

const initial = {id:'s1',profile_id:'p1',title:'Places',revision:0,status:'active',completed_items:0,total_items:2,attempts:[],draft_enabled:true,draft:{response:{text:'шко'},revision:2},origin:{title:'Where shall we meet?',href:'/curriculum/units/location-destination-v2'},sequence:{run_id:'r1',step_id:'forms',lesson_url:'/curriculum/units/location-destination-v2?run=r1'},item:{id:'i1',type:'controlled_text',prompt:'Иду в ___. (школа)',has_hint:false}};
const response = (body: unknown, ok=true) => Promise.resolve({ok,json:async () => body});
beforeEach(() => {vi.spyOn(HTMLMediaElement.prototype,'pause').mockImplementation(() => {});});
afterEach(() => {cleanup();vi.unstubAllGlobals();vi.restoreAllMocks();});

it('restores the saved draft and saves edits without checking an answer', async () => {
  const fetch = vi.fn((_url:string, options?:RequestInit) => response(options?.method === 'POST' ? {draft:{response:{text:'школу'},revision:3}} : initial));
  vi.stubGlobal('fetch',fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}}/>);
  const field = await screen.findByRole('textbox');
  await waitFor(() => expect((field as HTMLInputElement).value).toBe('шко'));
  await screen.findByText('Saved');
  expect(fetch.mock.calls.some(([,options]) => options?.method === 'POST')).toBe(false);
  fireEvent.input(field,{target:{value:'школу'}});
  await screen.findByText('Saved',{}, {timeout:2000});
  const request = fetch.mock.calls.find(([url]) => url.endsWith('/draft'))!;
  expect(request).toBeTruthy();
  expect(JSON.parse(String(request[1]?.body))).toMatchObject({item_id:'i1',expected_revision:0,expected_draft_revision:2,response:{text:'школу'}});
  expect(fetch.mock.calls.some(([url]) => url.endsWith('/attempts'))).toBe(false);
  expect(screen.getByRole('link',{name:'Where shall we meet?'}).getAttribute('href')).toContain('?run=r1');
});

it('retries an uncertain draft using the same command and preserves the text', async () => {
  let saves=0;
  const fetch=vi.fn((_url:string,options?:RequestInit) => options?.method === 'POST' ? ++saves===1 ? Promise.reject(new TypeError('offline')) : response({draft:{response:{text:'школу'},revision:3}}) : response(initial));
  vi.stubGlobal('fetch',fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}}/>);
  const field=await screen.findByRole('textbox');
  fireEvent.input(field,{target:{value:'школу'}});
  fireEvent.click(await screen.findByRole('button',{name:'Retry save'},{timeout:2000}));
  await screen.findByText('Saved');
  const posts=fetch.mock.calls.filter(([,options])=>options?.method==='POST');
  expect(posts[0][1]?.body).toBe(posts[1][1]?.body);
  expect((field as HTMLInputElement).value).toBe('школу');
});

it('retains conflicting local text and stops automatic writes until the saved version is loaded', async () => {
  const fetch=vi.fn((_url:string,options?:RequestInit) => options?.method==='POST' ? response({error:{code:'stale_draft_revision'}},false) : response(initial));
  vi.stubGlobal('fetch',fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}}/>);
  const field=await screen.findByRole('textbox');fireEvent.input(field,{target:{value:'в школу'}});
  await screen.findByText(/This draft changed in another tab/,{}, {timeout:2000});
  expect((field as HTMLInputElement).value).toBe('в школу');
  fireEvent.click(screen.getByRole('button',{name:'Check answer'}));
  expect(fetch.mock.calls.filter(([,options])=>options?.method==='POST')).toHaveLength(1);
  fireEvent.click(screen.getByRole('button',{name:'Load saved version'}));
  expect(await screen.findByRole('textbox',{name:'Copy your unsaved text'})).toBeTruthy();
});

it('flushes a typed draft before submitting and scopes draft requests to the demo', async () => {
  document.head.insertAdjacentHTML('beforeend','<meta name="app-base-path" content="/demo">');
  const completed={...initial,status:'completed',item:null,completed_items:2,attempts:[{id:'a1',feedback:{outcome:'correct',answer:'школу',assisted:false}}]};
  const fetch=vi.fn((url:string,_options?:RequestInit) => response(url.endsWith('/draft') ? {draft:{response:{text:'школу'},revision:3}} : url.endsWith('/attempts') ? completed : initial));
  vi.stubGlobal('fetch',fetch);
  try {
    render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}}/>);
    fireEvent.input(await screen.findByRole('textbox'),{target:{value:'школу'}});
    fireEvent.click(screen.getByRole('button',{name:'Check answer'}));
    await screen.findByRole('heading',{name:'That’s right.'});
    expect(fetch.mock.calls.filter(([,options])=>options?.method==='POST').map(([url])=>url)).toEqual(['/demo/api/v1/learning-sessions/s1/draft','/demo/api/v1/learning-sessions/s1/attempts']);
  } finally {document.querySelector('meta[name="app-base-path"]')?.remove();}
});
