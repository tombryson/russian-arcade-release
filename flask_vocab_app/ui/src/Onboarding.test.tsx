import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/preact';
import { bindUserSession } from './learning-api';
import { useOnboarding, type OnboardingState } from './Onboarding';

const initial:OnboardingState={profile_id:'tom',coins_introduced:false,progress_introduced:false};
const coins={...initial,coins_introduced:true};
const complete={...coins,progress_introduced:true};
const response=(value:unknown,ok=true)=>({ok,json:async()=>value});
type PendingResponse=ReturnType<typeof response>;
function deferred() {
  let resolve!:(value:PendingResponse)=>void;
  const promise=new Promise<PendingResponse>(done=>{resolve=done;});
  return {promise,resolve};
}
function Introduction({saved=initial}:{saved?:OnboardingState}) {
  const {state,introduce,error,retry}=useOnboarding(saved);
  return <>
    <output aria-label="Introductions">{JSON.stringify(state)}</output>
    {state.coins_introduced && <span>Coin balance visible</span>}
    {state.progress_introduced && <span>Barsik’s progress visible</span>}
    <button onClick={()=>introduce('coins')}>Introduce coins</button>
    <button onClick={()=>introduce('progress')}>Introduce progress</button>
    {error && <p role="alert">{error}</p>}
    <button onClick={()=>void retry()}>Retry save</button>
  </>;
}
function visibleState() {
  return JSON.parse(screen.getByRole('status',{name:'Introductions'}).textContent ?? '{}');
}

beforeEach(()=>bindUserSession('tom','page-csrf'));
afterEach(()=>{vi.unstubAllGlobals();bindUserSession(undefined,'');});

describe('Stepwise introduction persistence',()=>{
  it('reveals each introduction immediately but serializes fast coin and progress saves',async()=>{
    const first=deferred();const second=deferred();
    const fetch=vi.fn((_url:string,_init?:RequestInit)=>first.promise)
      .mockImplementationOnce(()=>first.promise).mockImplementationOnce(()=>second.promise);
    vi.stubGlobal('fetch',fetch);
    render(<Introduction />);
    expect(visibleState()).toEqual(initial);
    expect(fetch).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button',{name:'Introduce coins'}));
    fireEvent.click(screen.getByRole('button',{name:'Introduce progress'}));
    expect(visibleState()).toEqual(complete);
    expect(screen.getByText('Coin balance visible')).toBeTruthy();
    expect(screen.getByText('Barsik’s progress visible')).toBeTruthy();
    expect(fetch.mock.calls).toHaveLength(1);
    expect(JSON.parse(fetch.mock.calls[0][1]?.body as string)).toEqual({milestone:'coins'});

    await act(async()=>{first.resolve(response(coins));});
    await waitFor(()=>expect(fetch.mock.calls).toHaveLength(2));
    expect(JSON.parse(fetch.mock.calls[1][1]?.body as string)).toEqual({milestone:'progress'});
    // Saving the earlier coin step must not hide the progress step already shown.
    expect(visibleState()).toEqual(complete);
    await act(async()=>{second.resolve(response(complete));});
    fireEvent.click(screen.getByRole('button',{name:'Retry save'}));
    expect(fetch.mock.calls).toHaveLength(2);
    for (const [url,request] of fetch.mock.calls) {
      expect(url).toBe('/api/v1/onboarding');
      expect(request).toMatchObject({method:'POST',headers:{'X-Profile-ID':'tom','X-CSRF-Token':'page-csrf'}});
    }
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('keeps both introductions visible after failure and retries coins before progress',async()=>{
    const first=deferred();
    const fetch=vi.fn((_url:string,_init?:RequestInit)=>Promise.resolve(response(complete)))
      .mockImplementationOnce(()=>first.promise)
      .mockResolvedValueOnce(response(coins))
      .mockResolvedValueOnce(response(complete));
    vi.stubGlobal('fetch',fetch);
    render(<Introduction />);
    fireEvent.click(screen.getByRole('button',{name:'Introduce coins'}));
    fireEvent.click(screen.getByRole('button',{name:'Introduce progress'}));
    await act(async()=>{first.resolve(response({error:{code:'unavailable',message:'Please try saving again.'}},false));});
    expect(await screen.findByRole('alert')).toHaveProperty('textContent','Please try saving again.');
    expect(visibleState()).toEqual(complete);
    expect(fetch.mock.calls).toHaveLength(1);

    fireEvent.click(screen.getByRole('button',{name:'Retry save'}));
    await waitFor(()=>expect(fetch.mock.calls).toHaveLength(3));
    await waitFor(()=>expect(screen.queryByRole('alert')).toBeNull());
    expect(visibleState()).toEqual(complete);
    expect(fetch.mock.calls.map(([url,request])=>[url,JSON.parse(request?.body as string)])).toEqual([
      ['/api/v1/onboarding',{milestone:'coins'}],
      ['/api/v1/onboarding',{milestone:'coins'}],
      ['/api/v1/onboarding',{milestone:'progress'}],
    ]);
  });

  it('rejects another profile’s response without saving the queued progress step',async()=>{
    const first=deferred();
    const fetch=vi.fn((_url:string,_init?:RequestInit)=>first.promise);
    vi.stubGlobal('fetch',fetch);
    render(<Introduction />);
    fireEvent.click(screen.getByRole('button',{name:'Introduce coins'}));
    fireEvent.click(screen.getByRole('button',{name:'Introduce progress'}));
    await act(async()=>{first.resolve(response({...complete,profile_id:'anna'}));});
    expect(await screen.findByRole('alert')).toHaveProperty('textContent','Your profile changed. Reload before continuing.');
    expect(visibleState()).toEqual(complete);
    expect(fetch.mock.calls).toHaveLength(1);
    expect(JSON.parse(fetch.mock.calls[0][1]?.body as string)).toEqual({milestone:'coins'});
  });

  it('preserves saved introductions during replay without requesting rewards or another save',()=>{
    const fetch=vi.fn();vi.stubGlobal('fetch',fetch);
    render(<Introduction saved={complete} />);
    fireEvent.click(screen.getByRole('button',{name:'Introduce coins'}));
    fireEvent.click(screen.getByRole('button',{name:'Introduce progress'}));
    fireEvent.click(screen.getByRole('button',{name:'Retry save'}));
    expect(visibleState()).toEqual(complete);
    expect(fetch).not.toHaveBeenCalled();
  });
});
