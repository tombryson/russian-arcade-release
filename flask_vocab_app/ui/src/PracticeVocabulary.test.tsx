import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/preact';
import {Practice} from './Practice';

const passage = 'Она стоит перед аптекой.\n\nПотом она снова стоит перед аптекой.';
const initial = {id:'s1', profile_id:'p1', title:'Reading', revision:0, status:'active', completed_items:0, total_items:3, attempts:[],
  item:{id:'q1', type:'choice', prompt:'Where is she?', passage, word_lookup:true, has_hint:true, choices:[{id:'a',text:'Перед аптекой.'}]}};
const entry = {word:'аптекой', lemma:'аптека', pos:'NOUN', context:'Потом она снова стоит перед аптекой.', meaning:'pharmacy',
  in_vocabulary:false, can_add:true, choices:[], dictionary_url:'https://en.openrussian.org/ru/аптека'};
const response = (value:unknown, ok=true) => Promise.resolve({ok,json:async()=>value});
beforeEach(()=>vi.spyOn(HTMLMediaElement.prototype,'pause').mockImplementation(()=>{}));
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});

it('selects the exact repeated occurrence, waits for support, and saves only on request',async()=>{
  const fetch = vi.fn((url:string, _options?:RequestInit) => {
    if(url.endsWith('/words/lookup')) return response({...initial,revision:1,word:entry});
    if(url.endsWith('/words')) return response({...initial,revision:2,word:{...entry,in_vocabulary:true,can_add:false,added:true,mnemonic:'A memory association'}});
    if(url.endsWith('/attempts')) return response({...initial,status:'completed',revision:3,item:null,attempts:[{id:'a1',feedback:{outcome:'correct',answer:'Перед аптекой.',assisted:true}}]});
    return response(initial);
  });
  vi.stubGlobal('fetch',fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={()=>{}}/>);
  const words = await screen.findAllByRole('button',{name:'аптекой'});
  expect(fetch).toHaveBeenCalledOnce();
  fireEvent.click(words[1]);
  await screen.findByText('pharmacy');
  expect(screen.getByRole('complementary',{name:'Word help'}).textContent).toContain(entry.context);
  expect(screen.getByText('аптекой → аптека')).toBeTruthy();
  const lookup = fetch.mock.calls.find(([url])=>url.endsWith('/words/lookup'))!;
  expect(JSON.parse(String(lookup[1]?.body))).toMatchObject({word:'аптекой',offset:passage.lastIndexOf('аптекой'),expected_revision:0});
  expect(fetch.mock.calls.some(([url])=>url.endsWith('/words'))).toBe(false);
  fireEvent.click(screen.getByRole('button',{name:'Add to my words'}));
  await screen.findByText('Added to your vocabulary.');
  expect(screen.getByText('A memory association')).toBeTruthy();
  expect(JSON.parse(String(fetch.mock.calls.find(([url])=>url.endsWith('/words'))![1]?.body))).toMatchObject({lemma:'аптека',pos:'NOUN',expected_revision:1});
  fireEvent.click(screen.getByRole('button',{name:'Перед аптекой.'}));
  await screen.findByText('You used a hint for this question.');
  expect(JSON.parse(String(fetch.mock.calls.find(([url])=>url.endsWith('/attempts'))![1]?.body)).expected_revision).toBe(2);
});

it('retries an uncertain lookup with the identical receipt before enabling answers',async()=>{
  let attempts=0;
  const fetch=vi.fn((url:string)=>url.endsWith('/words/lookup')
    ? ++attempts===1 ? Promise.reject(new TypeError('Lost receipt')) : response({...initial,revision:1,word:entry})
    : response(initial));
  vi.stubGlobal('fetch',fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={()=>{}}/>);
  fireEvent.click((await screen.findAllByRole('button',{name:'аптекой'}))[1]);
  await screen.findByText('Word help could not be confirmed. Try again.');
  expect((screen.getByRole('button',{name:'Перед аптекой.'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button',{name:'Try saving again'}));
  await screen.findByText('pharmacy');
  const calls=fetch.mock.calls.filter(([url])=>url.endsWith('/words/lookup'));
  expect((calls[0] as unknown as [string,RequestInit])[1].body).toBe((calls[1] as unknown as [string,RequestInit])[1].body);
  expect((screen.getByRole('button',{name:'Перед аптекой.'}) as HTMLButtonElement).disabled).toBe(false);
});

it('keeps the listening transcript and its words hidden until the reveal receipt is saved',async()=>{
  const listening={...initial,item:{...initial.item,passage:undefined,type:'listening_choice',has_transcript:true,transcript:null,listened:false}};
  const revealed={...listening,revision:1,item:{...listening.item,transcript:passage}};
  const fetch=vi.fn((url:string)=>response(url.endsWith('/transcript') ? revealed : url.endsWith('/words/lookup') ? {...revealed,revision:2,word:entry} : listening));
  vi.stubGlobal('fetch',fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={()=>{}}/>);
  const reveal=await screen.findByRole('button',{name:'Show transcript'});
  expect(screen.queryByRole('button',{name:'аптекой'})).toBeNull();
  expect(screen.queryByText(passage)).toBeNull();
  fireEvent.click(reveal);
  const words=await screen.findAllByRole('button',{name:'аптекой'});
  fireEvent.click(words[1]);
  await screen.findByText('pharmacy');
  expect(fetch.mock.calls.map(([url])=>url)).toEqual(['/api/v1/learning-sessions/s1','/api/v1/learning-sessions/s1/transcript','/api/v1/learning-sessions/s1/words/lookup']);
});

it('shows ambiguous readings and lets pending enrichment be retried without blocking practice',async()=>{
  const text='Она видит печь.';
  const saved={...initial,item:{...initial.item,passage:text}};
  const ambiguous={...entry,word:'печь',lemma:null,pos:null,context:text,meaning:undefined,can_add:false,choices:[
    {lemma:'печь',pos:'NOUN',label:'печь · noun',in_vocabulary:false,can_add:true},
    {lemma:'печь',pos:'INFN',label:'печь · verb',in_vocabulary:false,can_add:true}]};
  const pendingWord={...ambiguous,lemma:'печь',pos:'NOUN',choices:[],in_vocabulary:true,can_add:false,enrichment_pending:true};
  const current={...saved,revision:2,word:pendingWord};
  const fetch=vi.fn((url:string)=>url.endsWith('/words') ? response({error:{code:'vocabulary_enrichment_pending',message:'The word is saved. Retry its details.',current_session:current}},false)
    : response(url.endsWith('/words/lookup') ? {...saved,revision:1,word:ambiguous} : saved));
  vi.stubGlobal('fetch',fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={()=>{}}/>);
  fireEvent.click(await screen.findByRole('button',{name:'печь'}));
  const readings=await screen.findByRole('combobox');
  expect(screen.queryByRole('button',{name:'Add to my words'})).toBeNull();
  fireEvent.change(readings,{target:{value:'печь|NOUN'}});
  fireEvent.click(await screen.findByRole('button',{name:'Add to my words'}));
  await screen.findByText('The word is saved. Retry its details.');
  expect(screen.getByRole('button',{name:'Finish word details'})).toBeTruthy();
  expect((screen.getByRole('button',{name:'Перед аптекой.'}) as HTMLButtonElement).disabled).toBe(false);
});

it('drops word help when moving to another learner and ignores the old response',async()=>{
  let resolve!: (value:unknown)=>void;
  const second={...initial,id:'s2',profile_id:'p2',item:{...initial.item,passage:'Дима дома.'}};
  const fetch=vi.fn((url:string)=>url.endsWith('/words/lookup') ? new Promise(done=>{resolve=done;}) : response(url.endsWith('/s2') ? second : initial));
  vi.stubGlobal('fetch',fetch);
  const view=render(<Practice sessionId="s1" profileId="p1" onFinish={()=>{}}/>);
  fireEvent.click((await screen.findAllByRole('button',{name:'аптекой'}))[0]);
  view.rerender(<Practice sessionId="s2" profileId="p2" onFinish={()=>{}}/>);
  await screen.findByRole('button',{name:'Дима'});
  resolve({ok:true,json:async()=>({...initial,revision:1,word:entry})});
  await waitFor(()=>expect(screen.queryByText('pharmacy')).toBeNull());
  expect(screen.queryByRole('complementary',{name:'Word help'})).toBeNull();
});
