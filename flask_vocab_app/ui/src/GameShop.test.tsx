import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {act, fireEvent, render, screen} from '@testing-library/preact';
import {GameShop} from './GameShop';
import {GameLanguage} from './GameLocale';
import type {GameCatalogueState, JourneyGameId} from './journey-games-api';

const catalogue = (balance=100):GameCatalogueState => ({profile_id:'tom',shop:{balance,first_purchase:true,price:25,enabled:true},games:[
  {id:'pack-bag',title:'Pack the bag',description:'Match Russian messages to pictures.',lesson_id:'bag',lesson_title:'Bag',lesson_href:'#first-steps/bag',unlocked:false,new:false,active_session_id:null,purchase:{price:25,owned:false,can_purchase:balance>=25}},
  {id:'directions',title:'Follow the directions',description:'Find your way through a Russian town.',lesson_id:'directions',lesson_title:'Directions',lesson_href:'#first-steps/directions',unlocked:false,new:false,active_session_id:null,purchase:{price:25,owned:false,can_purchase:balance>=25}}
]});
const response = (value:unknown,ok=true) => ({ok,json:async()=>structuredClone(value)});
function server(initial=catalogue()) {
  const state={catalogue:structuredClone(initial),hold:false,release:undefined as undefined|(()=>void),fail:'',priceChanged:false,refreshFails:false,purchases:0};
  const fetch=vi.fn(async(url:string,request?:RequestInit)=>{
    if(request?.method!=='POST') {
      if(state.refreshFails && state.purchases)throw new Error('Shop refresh unavailable.');
      return response(state.catalogue);
    }
    if(state.hold){state.hold=false;await new Promise<void>(resolve=>{state.release=resolve;});}
    const id=url.split('/').at(-2) as JourneyGameId;
    const game=state.catalogue.games.find(item=>item.id===id)!;
    if(state.fail){const code=state.fail;state.fail='';if(code==='network')throw new Error('Connection interrupted.');return response({error:{code,message:code==='profile_changed'?'Your profile changed.':'Your balance changed.'}},false);}
    if(state.priceChanged){state.priceChanged=false;state.catalogue.shop!.first_purchase=false;state.catalogue.shop!.price=50;for(const item of state.catalogue.games)item.purchase!.price=50;return response({error:{code:'price_changed',message:'The price changed. Please review it before buying.'}},false);}
    state.purchases++;
    const charged=game.purchase!.owned?0:game.purchase!.price;
    game.unlocked=true;game.purchase!.owned=true;
    state.catalogue.shop!.balance!-=charged;
    state.catalogue.shop!.price=50;state.catalogue.shop!.first_purchase=false;
    for(const item of state.catalogue.games){item.purchase!.price=50;item.purchase!.can_purchase=!item.purchase!.owned && state.catalogue.shop!.balance!>=50;}
    return response({game_id:id,charged,balance:state.catalogue.shop!.balance,owned:true,already_owned:charged===0});
  });
  vi.stubGlobal('fetch',fetch);
  return {state,fetch,posts:()=>fetch.mock.calls.filter(([,request])=>request?.method==='POST')};
}
async function unlock(name='Pack the bag',price=25) {
  fireEvent.click(await screen.findByRole('button',{name:`Unlock ${name} for ${price} Lingocoins`}));
}
beforeEach(()=>{window.location.hash='shop';});
afterEach(()=>vi.unstubAllGlobals());

describe('Shop',()=>{
  it('makes ownership permanent only after a confirmed purchase and refreshes every remaining price',async()=>{
    const api=server();const changed=vi.fn();window.addEventListener('lingo:progression',changed);
    render(<GameShop/>);
    expect(await screen.findByRole('heading',{name:'Shop'})).toBeTruthy();
    await screen.findByRole('button',{name:'Unlock Pack the bag for 25 Lingocoins'});
    expect(api.posts()).toHaveLength(0);
    await unlock();
    expect(await screen.findByRole('link',{name:'Play Pack the bag'})).toBeTruthy();
    expect(screen.getByLabelText('75 Lingocoins')).toBeTruthy();
    expect(await screen.findByRole('button',{name:'Unlock Follow the directions for 50 Lingocoins'})).toBeTruthy();
    expect(screen.getByText('Pack the bag is yours. You can play it whenever you like.')).toBeTruthy();
    expect(api.posts()).toHaveLength(1);expect(changed).toHaveBeenCalledTimes(1);
    window.removeEventListener('lingo:progression',changed);
  });
  it('ignores duplicate clicks while a purchase is pending and keeps other games disabled',async()=>{
    const api=server();api.state.hold=true;render(<GameShop/>);
    const button=await screen.findByRole('button',{name:'Unlock Pack the bag for 25 Lingocoins'});
    fireEvent.click(button);fireEvent.click(button);
    expect(screen.queryByRole('link',{name:'Play Pack the bag'})).toBeNull();
    expect((screen.getByRole('button',{name:'Unlock Follow the directions for 25 Lingocoins'}) as HTMLButtonElement).disabled).toBe(true);
    expect(api.posts()).toHaveLength(1);
    await act(async()=>api.state.release?.());
    expect(await screen.findByRole('link',{name:'Play Pack the bag'})).toBeTruthy();
  });
  it('retries an uncertain purchase with the same id and quoted price, never charging a different game first',async()=>{
    const api=server();api.state.fail='network';render(<GameShop/>);await unlock();
    await screen.findByRole('alert');
    expect(screen.queryByRole('link',{name:'Play Pack the bag'})).toBeNull();
    expect((screen.getByRole('button',{name:'Unlock Follow the directions for 25 Lingocoins'}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button',{name:'Try again'}));
    await screen.findByRole('link',{name:'Play Pack the bag'});
    const first=JSON.parse(api.posts()[0][1]!.body as string),second=JSON.parse(api.posts()[1][1]!.body as string);
    expect(first.request_id).toBeTruthy();expect(first.expected_price).toBe(25);expect(second).toEqual(first);
  });
  it('refreshes a stale price and waits for a new explicit purchase at the new price',async()=>{
    const api=server();api.state.priceChanged=true;render(<GameShop/>);await unlock();
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(await screen.findByRole('button',{name:'Unlock Pack the bag for 50 Lingocoins'})).toBeTruthy();
    expect(api.posts()).toHaveLength(1);expect(screen.queryByRole('link',{name:'Play Pack the bag'})).toBeNull();
    await unlock('Pack the bag',50);await screen.findByRole('link',{name:'Play Pack the bag'});
    const first=JSON.parse(api.posts()[0][1]!.body as string),second=JSON.parse(api.posts()[1][1]!.body as string);
    expect(second.expected_price).toBe(50);expect(second.request_id).not.toBe(first.request_id);
  });
  it('refreshes insufficient funds without unlocking or retrying automatically',async()=>{
    const api=server();api.state.fail='insufficient_funds';render(<GameShop/>);
    await screen.findByRole('button',{name:'Unlock Pack the bag for 25 Lingocoins'});
    api.state.catalogue.shop!.balance=3;for(const game of api.state.catalogue.games)game.purchase!.can_purchase=false;
    await unlock();await screen.findByRole('alert');
    expect(screen.getByLabelText('3 Lingocoins')).toBeTruthy();
    expect((screen.getByRole('button',{name:'Unlock Pack the bag for 25 Lingocoins'}) as HTMLButtonElement).disabled).toBe(true);
    expect(api.posts()).toHaveLength(1);
  });
  it('keeps the confirmed game when refresh fails but blocks purchases with stale prices',async()=>{
    const api=server();api.state.refreshFails=true;render(<GameShop/>);await unlock();
    expect(await screen.findByRole('link',{name:'Play Pack the bag'})).toBeTruthy();
    expect(await screen.findByRole('button',{name:'Refresh shop'})).toBeTruthy();
    expect((screen.getByRole('button',{name:'Unlock Follow the directions for 25 Lingocoins'}) as HTMLButtonElement).disabled).toBe(true);
    api.state.refreshFails=false;fireEvent.click(screen.getByRole('button',{name:'Refresh shop'}));
    await screen.findByRole('button',{name:'Unlock Follow the directions for 50 Lingocoins'});
  });
  it('accepts a signed wallet after a reward reversal and shows the true shortfall',async()=>{
    const api=server(catalogue(-1));render(<GameShop/>);
    expect(await screen.findByLabelText('-1 Lingocoins')).toBeTruthy();
    expect(screen.getAllByText('26 more coins needed')).toHaveLength(2);
    expect((screen.getByRole('button',{name:'Unlock Pack the bag for 25 Lingocoins'}) as HTMLButtonElement).disabled).toBe(true);
    expect(api.posts()).toHaveLength(0);
  });
  it('removes purchase controls and asks to reopen the profile if identity changes',async()=>{
    const api=server();api.state.fail='profile_changed';render(<GameShop profileHref="/my-profile"/>);await unlock();
    await screen.findByRole('alert');
    expect(screen.getByRole('link',{name:'Choose your profile'}).getAttribute('href')).toBe('/my-profile');
    expect(screen.queryByRole('button',{name:/Unlock .* for/})).toBeNull();
  });
  it('lets demo visitors play existing samples without purchase controls',async()=>{
    const overview=catalogue();overview.public_demo=true;overview.shop!.enabled=false;
    overview.games[0].availability='sample';overview.games[0].unlocked=true;overview.games[1].availability='local-only';
    const api=server(overview);render(<GameShop/>);
    expect(await screen.findByRole('link',{name:'Play Pack the bag'})).toBeTruthy();
    expect(screen.getByText('Try the sample games here. The shop is available in your own installation.')).toBeTruthy();
    expect(screen.queryByRole('button',{name:/Unlock .* for/})).toBeNull();expect(api.posts()).toHaveLength(0);
  });
  it('lets guests browse and choose a profile without offering an anonymous purchase',async()=>{
    const overview=catalogue();overview.profile_id=null;overview.shop!.balance=null;overview.shop!.enabled=false;
    const api=server(overview);render(<GameShop/>);
    expect(await screen.findByRole('link',{name:'Choose your profile'})).toBeTruthy();
    expect(screen.queryByRole('button',{name:/Unlock .* for/})).toBeNull();expect(api.posts()).toHaveLength(0);
  });
  it('has Russian shop and purchase copy',async()=>{
    server();render(<GameLanguage.Provider value="ru"><GameShop/></GameLanguage.Provider>);
    expect(await screen.findByRole('heading',{name:'Магазин'})).toBeTruthy();
    expect(await screen.findByRole('button',{name:'Открыть «Собери сумку» за 25 лингокоинов'})).toBeTruthy();
  });
});
