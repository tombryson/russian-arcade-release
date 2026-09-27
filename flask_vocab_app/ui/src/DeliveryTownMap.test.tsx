import {afterEach,expect,it,vi} from 'vitest';
import {act,fireEvent,render,screen} from '@testing-library/preact';
import {DeliveryMap,Person,point} from './DeliveryMap';
import type {DeliveryState} from './delivery-types';

function fixture():DeliveryState {
  const speaker={name:'Нина',name_en:'Nina',role:'На почте',role_en:'Postal worker',portrait:'postmaster'};
  return {revision:0,phase:'planning',leg:0,title_ru:'Письмо',envelope:'Анне',position:'post',heading:'east',draft:['post'],last_path:[],
    map:{scene:'town',width:17,height:13,tile_size:100,name_en:'Riverside town',name_ru:'Город у реки',
      nodes:[{id:'post',x:2,y:2,kind:'post',label:'Почта',label_en:'Post office',building_id:'postal-building',entrance:'front'},
        {id:'corner',x:3,y:2,kind:'street',label:'Перекрёсток',label_en:'Crossroads'},
        {id:'bridge',x:8,y:3,kind:'bridge',label:'Мост',label_en:'Bridge'},
        {id:'library',x:13,y:9,kind:'library',label:'Библиотека',label_en:'Library'}],
      edges:[['post','corner'],['corner','bridge'],['bridge','library']],
      tiles:[{x:2,y:1,kind:'building',building_kind:'post',building_id:'postal-building',label:'Почта',label_en:'Post office'},
        {x:2,y:2,kind:'road',exits:['e']},{x:3,y:2,kind:'road',exits:['w','s']},{x:8,y:2,kind:'river'},{x:8,y:3,kind:'bridge',exits:['w','e']}],
      districts:[{id:'centre',name:'Old town',name_ru:'Старый город',x:0,y:0,width:8,height:7},{id:'river',name:'Riverside',name_ru:'Заречье',x:9,y:0,width:8,height:13}]},
    objective:'Read the directions',objective_ru:'Прочитай указания',speaker,arrival_speaker:speaker,lines:[],support:{},feedback:null,notebook:[],glossary:[],first_checks:[]};
}
afterEach(()=>vi.unstubAllGlobals());
const props=(state=fixture())=>({state,path:state.draft,position:state.position,onNode:vi.fn(),disabled:false,ru:false});

it('renders a tile town, river, crossing and one separate post office building',()=>{
  const {container}=render(<DeliveryMap {...props()}/>);
  expect(container.querySelector('[data-tile-kind="river"]')).toBeTruthy();
  expect(container.querySelectorAll('.delivery-town-bridge')).toHaveLength(1);
  expect(container.querySelectorAll('.delivery-town-building.building-post')).toHaveLength(1);
  expect(screen.getByText('Old town')).toBeTruthy();
  expect(screen.getByText('Почта')).toBeTruthy();
  expect(screen.queryByText('Your destination')).toBeNull();
});

it('lets connected street clicks and keyboard selection plan the next step, but not distant buildings',()=>{
  const p=props();render(<DeliveryMap {...p}/>);
  fireEvent.click(screen.getByRole('button',{name:'Walk to: Crossroads'}));
  expect(p.onNode).toHaveBeenLastCalledWith('corner');
  fireEvent.click(screen.getByRole('button',{name:'Walk to: Library'}));
  expect(p.onNode).toHaveBeenCalledTimes(1);
  fireEvent.keyDown(screen.getByRole('button',{name:'Walk to: Crossroads'}),{key:'Enter'});
  expect(p.onNode).toHaveBeenCalledTimes(2);
});

it('follows the draft tail and switches between overview and local camera without modifying a route',()=>{
  const p=props(),{rerender}=render(<DeliveryMap {...p}/>);
  fireEvent.click(screen.getByRole('button',{name:'Explore streets'}));
  const map=screen.getByRole('group',{name:/Town map/}),initial=map.getAttribute('viewBox');
  expect(map.getAttribute('data-camera')).toBe('local');
  rerender(<DeliveryMap {...p} path={['post','corner','bridge']}/>);
  expect(map.getAttribute('viewBox')).not.toBe(initial);
  fireEvent.click(screen.getByRole('button',{name:'Whole town'}));
  expect(map.getAttribute('viewBox')).toBe('0 0 1700 1300');
  expect(map.getAttribute('data-camera')).toBe('overview');
  fireEvent.click(screen.getByRole('button',{name:'Centre on Barsik'}));
  expect(map.getAttribute('data-camera')).toBe('local');
  expect(map.getAttribute('viewBox')).toBe(initial);
  expect(p.onNode).not.toHaveBeenCalled();
});

it('supports map panning, zoom and recentring independent of route planning',()=>{
  const p=props();render(<DeliveryMap {...p}/>);
  fireEvent.click(screen.getByRole('button',{name:'Explore streets'}));
  const map=screen.getByRole('group',{name:/Town map/}),initial=map.getAttribute('viewBox');
  fireEvent.click(screen.getByRole('button',{name:'Move map right'}));
  expect(map.getAttribute('viewBox')).not.toBe(initial);
  fireEvent.click(screen.getByRole('button',{name:'Zoom in'}));
  const zoomedWidth=Number(map.getAttribute('viewBox')!.split(' ')[2]);
  expect(zoomedWidth).toBeLessThan(Number(initial!.split(' ')[2]));
  fireEvent.click(screen.getByRole('button',{name:'Zoom out'}));
  fireEvent.click(screen.getByRole('button',{name:'Centre on Barsik'}));
  expect(map.getAttribute('viewBox')).toBe(initial);
  expect(p.onNode).not.toHaveBeenCalled();
});

it('shows the visitor in guide mode and prevents disabled walking',()=>{
  const state=fixture();state.interaction='guide';const p={...props(state),disabled:true};
  const {container}=render(<DeliveryMap {...p}/>);
  expect(container.querySelector('.delivery-town-traveller .delivery-person')).toBeTruthy();
  expect(container.querySelector('.delivery-town-traveller image')).toBeNull();
  expect(screen.getByRole('button',{name:'Centre on your visitor'})).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Walk to: Crossroads'}));
  expect(p.onNode).not.toHaveBeenCalled();
});

it('keeps legacy geometry and renderer intact while town points use cell centres',()=>{
  const state=fixture();state.map.scene='riverside';const node=state.map.nodes[0];
  expect(point(node)).toEqual({x:400,y:390});
  expect(point(node,{scene:'town',tile_size:100})).toEqual({x:250,y:250});
  const {container}=render(<DeliveryMap {...props(state)}/>);
  expect(container.querySelector('svg.delivery-map')?.getAttribute('viewBox')).toBe('0 0 870 670');
  expect(container.querySelector('.delivery-town')).toBeNull();
});

it('localises map controls and place names to Russian',()=>{
  render(<DeliveryMap {...props()} ru/>);
  expect(screen.getByRole('button',{name:'Посмотреть улицы'})).toBeTruthy();
  expect(screen.getByRole('button',{name:'Идти: Перекрёсток'})).toBeTruthy();
  expect(screen.getByText('Старый город')).toBeTruthy();
  expect(screen.getByText('Почта')).toBeTruthy();
  expect(screen.queryByText('Old town')).toBeNull();
});

it('distinguishes a named bus stop from its building and shows a closed crossing',()=>{
  const state=fixture();
  state.map.nodes.push({id:'bus-library',x:12,y:9,kind:'bus-stop',label:'Библиотека',label_en:'Library'});
  state.map.edges.push(['library','bus-library']);
  (state.map as typeof state.map&{closures:unknown[]}).closures=[{node_id:'bridge',reason:'Bridge closed for repairs',reason_ru:'Мост закрыт на ремонт'}];
  const {container}=render(<DeliveryMap {...props(state)}/>);
  expect(screen.getByText('«Библиотека»')).toBeTruthy();
  expect(screen.getByText('Ост.')).toBeTruthy();
  expect(screen.getByText('Библиотека',{exact:true})).toBeTruthy();
  expect(screen.getByRole('button',{name:'Walk to: Bus stop — Library'})).toBeTruthy();
  expect(container.querySelector('.delivery-town-bus-stop')).toBeTruthy();
  expect(container.querySelector('.delivery-town-closure title')?.textContent).toBe('Bridge closed for repairs');
});

it('offers the end of an uninterrupted street alongside a single step, stopping at the junction',()=>{
  const state=fixture();
  state.map.nodes=[
    {id:'start',x:1,y:3,kind:'street',label:'Старт',label_en:'Start'},
    {id:'first',x:2,y:3,kind:'street',label:'Первый участок',label_en:'First block'},
    {id:'middle',x:3,y:3,kind:'street',label:'Второй участок',label_en:'Second block'},
    {id:'junction',x:4,y:3,kind:'street',label:'Перекрёсток',label_en:'Junction'},
    {id:'east',x:5,y:3,kind:'street',label:'Дальше',label_en:'Beyond the junction'},
    {id:'north',x:4,y:2,kind:'street',label:'Север',label_en:'North'},
  ];
  state.map.edges=[['start','first'],['first','middle'],['middle','junction'],['junction','east'],['junction','north']];
  state.position='start';state.draft=['start'];
  const p=props(state);render(<DeliveryMap {...p}/>);
  fireEvent.click(screen.getByRole('button',{name:'Walk to: First block'}));
  expect(p.onNode).toHaveBeenLastCalledWith('first');
  fireEvent.click(screen.getByRole('button',{name:'Walk to: Junction'}));
  expect(p.onNode).toHaveBeenLastCalledWith('junction');
  fireEvent.click(screen.getByRole('button',{name:'Walk to: Beyond the junction'}));
  expect(p.onNode).toHaveBeenCalledTimes(2);
});

it('keeps the town overview when planning begins until the learner chooses a closer view',()=>{
  const state=fixture();state.phase='dialogue';const p=props(state);
  const {rerender,container}=render(<DeliveryMap {...p}/>);
  const map=screen.getByRole('group',{name:/Town map/});
  expect(map.getAttribute('data-camera')).toBe('overview');
  expect(screen.getByRole('button',{name:'Explore streets'})).toBeTruthy();
  rerender(<DeliveryMap {...p} state={{...state,phase:'planning'}}/>);
  expect(map.getAttribute('data-camera')).toBe('overview');
  fireEvent.click(screen.getByRole('button',{name:'Explore streets'}));
  expect(map.getAttribute('data-camera')).toBe('local');
  expect(Number(map.getAttribute('viewBox')!.split(' ')[2])/state.map.tile_size!).toBeGreaterThanOrEqual(10);
  expect(container.querySelector('.delivery-town-minimap')).toBeTruthy();
});

it('preserves an explicitly chosen overview when a route changes',()=>{
  const state=fixture();const p=props(state);
  const {rerender}=render(<DeliveryMap {...p}/>);
  fireEvent.click(screen.getByRole('button',{name:'Explore streets'}));
  fireEvent.click(screen.getByRole('button',{name:'Whole town'}));
  rerender(<DeliveryMap {...p} path={['post','corner','bridge']}/>);
  expect(screen.getByRole('group',{name:/Town map/}).getAttribute('data-camera')).toBe('overview');
});


it('shows a bus while aboard and restores Barsik when the learner gets off',()=>{
  const state=fixture();state.transport={id:'bus-5',label:'Bus 5',label_ru:'Автобус № 5',board:'post',status:'aboard',stops:[]};
  const p=props(state),{container,rerender}=render(<DeliveryMap {...p}/>);
  expect(container.querySelector('.delivery-town-bus title')?.textContent).toBe('Bus 5');
  expect(container.querySelector('.delivery-town-traveller')?.getAttribute('aria-label')).toBe('Barsik on the bus');
  expect(container.querySelector('.delivery-town-traveller image')).toBeNull();
  rerender(<DeliveryMap {...p} state={{...state,transport:{...state.transport,status:'arrived'}}}/>);
  expect(container.querySelector('.delivery-town-bus')).toBeNull();
  expect(container.querySelector('.delivery-town-traveller image')).toBeTruthy();
});

it('keeps short-hair portraits for named male visitors and existing male portrait aliases',()=>{
  const {container,rerender}=render(<Person kind="sergei"/>);
  for(const kind of ['sergei','ivan','pavel','viktor','igor','boris','dima','nikolai']){
    rerender(<Person kind={kind}/>);
    expect(container.querySelector('.delivery-person-long-hair')).toBeNull();
  }
  rerender(<Person kind="postmaster"/>);
  expect(container.querySelector('.delivery-person-long-hair')).toBeTruthy();
});

it('joins old saved town streets by painting the whole road surface after every kerb',()=>{
  const {container}=render(<DeliveryMap {...props()}/>);
  const roads=container.querySelector('.delivery-town-roads')!;
  const layers=Array.from(roads.children);
  expect(layers.map(layer=>layer.getAttribute('class'))).toEqual([
    'delivery-town-road-sidewalk','delivery-town-road-kerb','delivery-town-road-surface',
  ]);
  for(const layer of layers)expect(layer.querySelectorAll('path')).toHaveLength(fixture().map.edges.length);
  expect(roads.getAttribute('stroke-linecap')).toBe('square');
});

it('renders street hierarchy and neighbourhood plots without inventing walking routes',()=>{
  const state=fixture();
  state.map.street_segments=[{from:'post',to:'corner',kind:'path'},{from:'corner',to:'bridge',kind:'main'},{from:'bridge',to:'library',kind:'residential'}];
  state.map.blocks=[{id:'park',x:5,y:5,width:3,height:2,kind:'park'},{id:'square',x:10,y:5,width:2,height:2,kind:'market'}];
  state.map.plots=[{id:'post-garden',building_id:'postal-building',x:1.8,y:.8,width:1.4,height:1.4,kind:'garden',frontage:'s'}];
  state.map.tiles!.push({x:6,y:7,kind:'building',building_kind:'house',building_id:'decorative-home',colour:'coral',decorative:true});
  const p=props(state),{container}=render(<DeliveryMap {...p}/>);
  expect(container.querySelectorAll('.delivery-town-block')).toHaveLength(2);
  expect(container.querySelector('.delivery-town-plot.plot-garden')).toBeTruthy();
  expect(container.querySelector('.delivery-town-building.is-decorative')).toBeTruthy();
  expect(container.querySelectorAll('.delivery-town-node')).toHaveLength(state.map.nodes.length);
  const width=(kind:string)=>Number(container.querySelector(`.delivery-town-road-surface [data-street-kind="${kind}"]`)?.getAttribute('stroke-width'));
  expect(width('path')).toBeLessThan(width('residential'));
  expect(width('residential')).toBeLessThan(width('main'));
  expect(container.querySelectorAll('.block-park>path')).toHaveLength(0);
  fireEvent.click(screen.getByRole('button',{name:'Walk to: Crossroads'}));
  expect(p.onNode).toHaveBeenCalledWith('corner');
});

it('wraps house names and staggers adjacent landmark labels without shrinking them',()=>{
  const state=fixture();
  state.map.tiles!.push({x:3,y:1,kind:'building',building_kind:'house',building_id:'yellow-house',label:'Жёлтый дом',label_en:'Yellow house'});
  state.map.nodes.push({id:'yellow-door',x:3,y:0,kind:'house',building_id:'yellow-house',label:'Жёлтый дом',label_en:'Yellow house'});
  const {container}=render(<DeliveryMap {...props(state)}/>);
  const houseLabel=screen.getByText('Жёлтый').parentElement!;
  expect(houseLabel.querySelectorAll('tspan')).toHaveLength(2);
  expect(houseLabel.textContent).toContain('дом');
  expect(houseLabel.getAttribute('y')).not.toBe(screen.getByText('Почта').parentElement!.getAttribute('y'));
  expect(container.querySelectorAll('.delivery-town-label-leader')).toHaveLength(2);
});

it('marks actual north and courtyard entrances and only draws a south door when that side is accessible',()=>{
  const state=fixture();
  state.map.tiles=[{x:5,y:5,kind:'building',building_kind:'house',building_id:'court',frontage:'n'}];
  state.map.nodes=[{id:'front',x:5,y:4,kind:'house',building_id:'court',entrance:'main',label:'Дом с двором',label_en:'Courtyard house'}];
  state.map.edges=[];state.position='front';state.draft=['front'];
  const p=props(state),{container,rerender}=render(<DeliveryMap {...p}/>);
  expect(container.querySelector('[data-entrance-side="n"]')).toBeTruthy();
  expect(container.querySelector('.delivery-building-door')).toBeNull();
  const withRear={...state,map:{...state.map,nodes:[...state.map.nodes,{id:'rear',x:5,y:6,kind:'courtyard',building_id:'court',entrance:'courtyard',label:'Вход со двора',label_en:'Courtyard entrance'}]}};
  rerender(<DeliveryMap {...props(withRear)}/>);
  expect(container.querySelector('.delivery-building-door')).toBeTruthy();
  expect(container.querySelector('.delivery-town-entrance.is-rear[data-entrance-side="s"]')).toBeTruthy();
  expect(screen.getByText('Главный вход')).toBeTruthy();
  expect(screen.getByText('Со двора')).toBeTruthy();
});


it('does not zoom in when zooming out of the whole-town view',()=>{
  render(<DeliveryMap {...props()}/>);
  const map=screen.getByRole('group',{name:/Town map/}),initial=map.getAttribute('viewBox');
  const out=screen.getByRole('button',{name:'Zoom out'}) as HTMLButtonElement;
  expect(out.disabled).toBe(true);
  fireEvent.click(out);
  expect(map.getAttribute('viewBox')).toBe(initial);
  fireEvent.click(screen.getByRole('button',{name:'Explore streets'}));
  for(let i=0;i<8&&!out.disabled;i++)fireEvent.click(out);
  expect(map.getAttribute('data-camera')).toBe('overview');
  expect(map.getAttribute('viewBox')).toBe(initial);
});

it('keeps landmark names readable at different viewport sizes and zoom levels',()=>{
  let resize:ResizeObserverCallback|undefined;
  class Observer {constructor(callback:ResizeObserverCallback){resize=callback;}observe(){}disconnect(){}}
  vi.stubGlobal('ResizeObserver',Observer);
  render(<DeliveryMap {...props()}/>);
  const map=screen.getByRole('group',{name:/Town map/});
  const setSize=(width:number,height:number)=>act(()=>resize?.([{contentRect:{width,height}} as ResizeObserverEntry],{} as ResizeObserver));
  const renderedFont=(width:number,height:number)=>{
    const box=map.getAttribute('viewBox')!.split(' ').map(Number),text=screen.getByText('Почта').parentElement!;
    return Number(text.getAttribute('font-size'))*Math.min(width/box[2],height/box[3]);
  };
  setSize(1200,800);expect(renderedFont(1200,800)).toBeGreaterThanOrEqual(13.5);
  setSize(420,500);expect(renderedFont(420,500)).toBeGreaterThanOrEqual(13.5);
  fireEvent.click(screen.getByRole('button',{name:'Explore streets'}));
  fireEvent.click(screen.getByRole('button',{name:'Zoom in'}));
  expect(renderedFont(420,500)).toBeGreaterThanOrEqual(13.5);
  expect(renderedFont(420,500)).toBeLessThanOrEqual(15);
});

it('separates the two courtyard entrance labels and connects each label to its gate',()=>{
  const state=fixture();
  state.map.tiles=[{x:12,y:5,kind:'building',building_kind:'house',building_id:'court',frontage:'n'},
    {x:13,y:5,kind:'building',building_kind:'house',building_id:'neighbour',label:'Соседний дом'}];
  state.map.nodes=[{id:'front',x:12,y:4,kind:'house',building_id:'court',entrance:'main',label:'Дом с двором',label_en:'Courtyard house'},
    {id:'rear',x:12,y:6,kind:'courtyard',building_id:'court',entrance:'courtyard',label:'Вход со двора',label_en:'Courtyard entrance'},
    {id:'neighbour-door',x:13,y:6,kind:'house',building_id:'neighbour',label:'Соседний дом',label_en:'Neighbouring house'}];
  state.position='front';state.draft=['front'];state.map.edges=[];
  const {container}=render(<DeliveryMap {...props(state)}/>);
  const main=screen.getByText('Главный вход'),rear=screen.getByText('Со двора');
  const separation=Math.abs(Number(main.getAttribute('y'))-Number(rear.getAttribute('y')));
  expect(separation).toBeGreaterThan(Number(main.getAttribute('font-size')));
  expect(container.querySelectorAll('.delivery-town-entrance-leader')).toHaveLength(2);
});

it('uses undistorted building proportions and caps neighbouring houses to their available space',()=>{
  const state=fixture();
  state.map.tiles!.push({x:3,y:1,kind:'building',building_kind:'house',building_id:'next-door'});
  const {container}=render(<DeliveryMap {...props(state)}/>);
  const transforms=Array.from(container.querySelectorAll('.delivery-town-building')).map(node=>node.getAttribute('transform')!);
  for(const transform of transforms){
    expect(transform).toMatch(/scale\([\d.]+\)$/);
    const scale=Number(transform.match(/scale\(([\d.]+)\)/)![1]);
    expect(120*scale).toBeLessThan(state.map.tile_size!);
  }
});

it('keeps narrow-overview label leaders clear of the neighbouring house',()=>{
  let resize:ResizeObserverCallback|undefined;
  class Observer {constructor(callback:ResizeObserverCallback){resize=callback;}observe(){}disconnect(){}}
  vi.stubGlobal('ResizeObserver',Observer);
  const state=fixture();state.map.width=21;state.map.height=21;
  state.map.tiles=[{x:3,y:11,kind:'building',building_kind:'house',building_id:'yellow',colour:'yellow'},
    {x:4,y:11,kind:'building',building_kind:'house',building_id:'blue',colour:'blue'}];
  state.map.nodes=[{id:'yellow-door',x:3,y:10,kind:'house',building_id:'yellow',label:'Жёлтый дом',label_en:'Yellow house'},
    {id:'blue-door',x:4,y:10,kind:'house',building_id:'blue',label:'Синий дом',label_en:'Blue house'}];
  state.map.edges=[];state.position='yellow-door';state.draft=['yellow-door'];
  const {container}=render(<DeliveryMap {...props(state)}/>);
  act(()=>resize?.([{contentRect:{width:390,height:390}} as ResizeObserverEntry],{} as ResizeObserver));
  const glyphs=Array.from(container.querySelectorAll('.delivery-town-building'));
  const bounds=glyphs.map(glyph=>{
    const [cx,cy,scale]=glyph.getAttribute('transform')!.match(/[-\d.]+/g)!.map(Number);
    return {left:cx-60*scale,right:cx+60*scale,top:cy-113*scale,bottom:cy-10*scale};
  });
  for(const [index,name] of ['Жёлтый','Синий'].entries()){
    const line=screen.getByText(name).closest('g')!.querySelector('.delivery-town-label-leader')!;
    const [x1,y1,x2,y2]=line.getAttribute('d')!.match(/[-\d.]+/g)!.map(Number),other=bounds[1-index];
    for(let step=1;step<100;step++){
      const x=x1+(x2-x1)*step/100,y=y1+(y2-y1)*step/100;
      expect(x>other.left+.1&&x<other.right-.1&&y>other.top+.1&&y<other.bottom-.1).toBe(false);
    }
  }
});
