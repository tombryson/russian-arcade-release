import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {waitFor} from '@testing-library/preact';
const script=readFileSync('../static/js/progression.js','utf8');
const template=readFileSync('../templates/_skill_progress.html','utf8');
let dom;
afterEach(()=>dom?.window.close());
const course=(patch={})=>({version:'a1-v1',profile_id:'personal',current_chapter_id:'first',completed:false,chapters:[{id:'first',number:1,title:'A small message',title_ru:'Короткое сообщение',progress:.2},...Array.from({length:3},(_,i)=>({id:`chapter-${i+2}`,number:i+2,title:'Next',title_ru:'Дальше',progress:0}))],...patch});
const data=(patch={})=>({profile_id:'personal',balance:42,skill:{active_skill:'reading',skills:[{rating:1040,observations:3,progress:.9}]},course:course(),...patch});
const rated=(patch={},extra={})=>data({course:course({chapters:[{...course().chapters[0],...patch},...course().chapters.slice(1)]}),...extra});
async function setup(initial=data(),{household=false,language='en',layout='top',width=1200,coins=true}={}) {
  const markup=template.replace(/\{%[\s\S]*?%\}/g,'').replace(/\{\{[\s\S]*?\}\}/g,expression=>expression.includes('household_enabled') ? '/#journey' : language);
  const badge=coins ? `<a data-progression-badge data-language="${language}"><strong data-progression-balance>—</strong></a>` : '';
  const navigation=layout==='sidebar' ? `<nav id="sidebar"><div class="sidebar-brand-row"></div><button class="navbar-toggler"></button><div id="sidebarNav"><div class="sidebar-footer">${badge}${markup}</div></div></nav>` : `<header class="arcade-header">${badge}${markup}</header>`;
  dom=new JSDOM(`${navigation}<textarea aria-label="Draft">Я читаю.</textarea>`,{url:'http://localhost/writing',runScripts:'outside-only'});
  dom.window.innerWidth=width;
  const heights={'.arcade-header':120,'.sidebar-brand-row':64,'.navbar-toggler':40,'#sidebar':600};
  for (const [selector,height] of Object.entries(heights)) {
    const element=dom.window.document.querySelector(selector);
    if (element) element.getBoundingClientRect=()=>({height});
  }
  const state={data:initial,fail:false,status:503};
  const savedResponse={ok:true,json:async()=>({saved:true})};
  const fetch=vi.fn(async(url)=>url==='/api/v1/progression' ? {ok:!state.fail,status:state.fail ? state.status : 200,json:async()=>state.data} : savedResponse);
  dom.window.fetch=fetch;dom.window.Request=class Request {};
  dom.window.setInterval=()=>0;
  dom.window.eval(script);
  const document=dom.window.document;
  const rail=document.querySelector('[data-skill-rail]');
  await waitFor(()=>expect(rail.style.getPropertyValue('--skill-progress')).not.toBe(''));
  async function refresh() {
    const requests=fetch.mock.calls.filter(([url])=>url==='/api/v1/progression').length;
    const returned=await dom.window.fetch('/save-answer',{method:'POST',body:'original'});
    await waitFor(()=>expect(fetch.mock.calls.filter(([url])=>url==='/api/v1/progression')).toHaveLength(requests+1));
    return returned;
  }
  return {state,fetch,savedResponse,document,rail,link:rail.querySelector('.skill-rail-link'),refresh};
}

describe('Shared progress in existing activities',()=>{
  it('distinguishes a full preparation bar from a saved milestone pass',async()=>{
    const {rail,state,refresh}=await setup(rated({progress:1,status:'ready'}));
    expect(rail.querySelector('[data-skill-bar]').getAttribute('aria-valuetext')).toContain('100% prepared for checkpoint');
    expect(rail.querySelector('[data-skill-bar]').getAttribute('aria-valuetext')).not.toContain('Milestone passed');
    state.data=rated({progress:1,status:'passed'});
    await refresh();
    expect(rail.querySelector('[data-skill-bar]').getAttribute('aria-valuetext')).toContain('Milestone passed');
  });
  it.each([['top',1200,'120px'],['top',500,'120px'],['sidebar',1200,'0px'],['sidebar',500,'104px']])('measures the visible %s bar at width %s',async(layout,width,expected)=>{
    const {document}=await setup(data(),{layout,width});
    expect(document.documentElement.style.getPropertyValue('--arcade-header-height')).toBe(expected);
    expect(document.documentElement.style.getPropertyValue('--skill-header-height')).toBe(expected);
  });

  it('updates sidebar progress and clears the mobile offset when the viewport reaches desktop',async()=>{
    const {document,state,rail,refresh}=await setup(data(),{layout:'sidebar',width:500});
    expect(document.querySelector('.arcade-header')).toBeNull();
    expect(document.querySelector('#sidebar [data-progression-balance]').textContent).toBe('42');
    dom.window.innerWidth=992;
    dom.window.dispatchEvent(new dom.window.Event('resize'));
    expect(document.documentElement.style.getPropertyValue('--arcade-header-height')).toBe('0px');
    state.data=rated({rating:1050,progress:.25},{balance:45});
    await refresh();
    expect(document.querySelector('#sidebar [data-progression-balance]').textContent).toBe('45');
    expect(rail.style.getPropertyValue('--skill-progress')).toBe('0.25');
  });

  it('can refresh an introduced skill rail without a coin badge',async()=>{
    const {document,rail}=await setup(data(),{layout:'sidebar',coins:false});
    expect(document.querySelector('[data-progression-badge]')).toBeNull();
    expect(rail.style.getPropertyValue('--skill-progress')).toBe('0.2');
  });

  it.each([false,true])('links the uncluttered rail to the chapter journey (household=%s)',async household=>{
    const {rail,link}=await setup(data(),{household});
    expect(rail.tagName).toBe('DIV');expect(link.tagName).toBe('A');
    expect(link.getAttribute('href')).toBe('/#journey');
    expect(link.getAttribute('hx-boost')).toBe('false');
    expect(link.getAttribute('aria-label')).toBe('Chapter 1 of 4 · A small message · 20% prepared for checkpoint. Open your journey');
    expect(rail.textContent.trim()).toBe('');
    expect(rail.querySelector('summary,details,.skill-rail-caption,.skill-progress-panel,[data-skill-content]')).toBeNull();
    expect(rail.getAttribute('open')).toBeNull();
    expect(rail.style.getPropertyValue('--skill-progress')).toBe('0.2');
    expect(rail.querySelector('[data-skill-bar]').getAttribute('aria-valuenow')).toBe('20');
  });

  it('updates after a saved answer without changing its response, activity draft or focused field',async()=>{
    const {state,document,rail,link,savedResponse,refresh}=await setup();
    expect(document.querySelector('[data-progression-balance]').textContent).toBe('42');
    const draft=document.querySelector('textarea');draft.focus();draft.setSelectionRange(2,5);
    state.data=rated({rating:1050,progress:.25},{balance:45});
    expect(await refresh()).toBe(savedResponse);
    expect(document.querySelector('[data-progression-balance]').textContent).toBe('45');
    expect(draft.value).toBe('Я читаю.');expect(document.activeElement).toBe(draft);
    expect([draft.selectionStart,draft.selectionEnd]).toEqual([2,5]);
    expect(rail.style.getPropertyValue('--skill-progress')).toBe('0.25');
    expect(rail.querySelector('[data-skill-bar]').getAttribute('aria-valuenow')).toBe('25');
    expect(link.getAttribute('aria-label')).toContain('25% prepared for checkpoint');
    expect(rail.classList.contains('is-moving')).toBe(true);
    document.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Escape'}));
    expect(document.activeElement).toBe(draft);
  });

  it('shows an unmeasured start without empty-state copy or a made-up rating',async()=>{
    const {document,rail,link}=await setup(data({course:undefined}));
    expect(link.getAttribute('aria-label')).toBe('Open your journey');
    expect(link.getAttribute('aria-label')).not.toContain('1,000');
    expect(rail.style.getPropertyValue('--skill-progress')).toBe('0');
    expect(document.querySelector('[data-skill-bar]').hidden).toBe(true);
    expect(document.querySelector('.skill-rail-runner').hidden).toBe(false);
    expect(rail.textContent.trim()).toBe('');
    expect(rail.innerHTML).not.toContain('Getting started');
  });

  it.each([[-.2,'0'],[1.2,'1'],[Number.NaN,'0']])('bounds bar progress %s to %s',async(progress,expected)=>{
    const {rail}=await setup(rated({progress}));
    expect(rail.style.getPropertyValue('--skill-progress')).toBe(expected);
    expect(rail.querySelector('[data-skill-bar]').getAttribute('aria-valuenow')).toBe(String(Number(expected)*100));
  });

  it('keeps saved progress on a temporary failure but clears it when the session expires',async()=>{
    const {state,document,rail,link,refresh}=await setup();
    state.fail=true;
    await refresh();
    expect(link.getAttribute('aria-label')).toContain('20% prepared for checkpoint');
    expect(link.getAttribute('aria-label')).toContain('Showing your last saved progress');
    expect(rail.style.getPropertyValue('--skill-progress')).toBe('0.2');
    expect(rail.querySelector('.skill-rail-runner').hidden).toBe(false);
    state.status=403;
    await refresh();
    expect(link.getAttribute('aria-label')).toContain('Chapter progress unavailable');
    expect(link.getAttribute('aria-label')).not.toContain('1,040');
    expect(rail.style.getPropertyValue('--skill-progress')).toBe('0');
    expect(rail.querySelector('.skill-rail-runner').hidden).toBe(true);
    expect(rail.querySelector('[data-skill-bar]').hasAttribute('aria-valuenow')).toBe(false);
    expect(document.querySelector('[data-progression-balance]').textContent).toBe('—');
    expect(rail.classList.contains('is-moving')).toBe(false);
  });

  it('clears stale progress on an explicit profile-change response',async()=>{
    const {state,rail,link,refresh}=await setup();
    state.fail=true;state.status=409;state.data={error:{code:'profile_changed'}};
    await refresh();
    expect(link.getAttribute('aria-label')).toContain('unavailable');
    expect(rail.style.getPropertyValue('--skill-progress')).toBe('0');
    expect(rail.querySelector('.skill-rail-runner').hidden).toBe(true);
  });

  it.each([
    ['profile',rated({progress:.25},{profile_id:'different'})],
    ['version',data({course:course({version:'a1-v2',chapters:[{...course().chapters[0],progress:.25},...course().chapters.slice(1)]})})],
    ['chapter',data({course:course({current_chapter_id:'chapter-2'})})],
    ['lower progress',rated({progress:.1})],
  ])('does not animate a %s change as earned progress',async(_change,next)=>{
    const {state,rail,refresh}=await setup();state.data=next;await refresh();
    expect(rail.classList.contains('is-moving')).toBe(false);
  });

  it('sets chapter names as accessible text rather than executable markup',async()=>{
    const {link,rail}=await setup(rated({title:'<img src=x onerror=alert(1)>'}));
    expect(link.getAttribute('aria-label')).toContain('<img src=x onerror=alert(1)>');
    expect(rail.querySelectorAll('img')).toHaveLength(1);
    expect(rail.querySelector('img').getAttribute('src')).toBe('/static/images/barsik-progress-run-v1.webp');
  });

  it('provides the chapter and journey destination in Russian',async()=>{
    const {link}=await setup(data(),{language:'ru'});
    expect(link.getAttribute('aria-label')).toContain('Глава 1 из 4');
    expect(link.getAttribute('aria-label')).toContain('20% подготовки к проверке');
    expect(link.getAttribute('aria-label')).toContain('Открыть путешествие');
  });
});
