import type {DeliveryBlock,DeliveryMapData,DeliveryNode,DeliveryPlot,DeliveryState,DeliveryStreet,DeliveryTile} from './delivery-types';
import {useEffect,useRef,useState} from 'preact/hooks';
import './styles/delivery-town.css';
import {corridorChoices} from './delivery-navigation';

export const point=(node:DeliveryNode,map?:{scene?:string;tile_size?:number})=>map?.scene==='town'
  ?{x:(node.x+.5)*(map.tile_size??100),y:(node.y+.5)*(map.tile_size??100)}
  :{x:100+node.x*150,y:90+node.y*150};

export function Person({kind,small=false}:{kind:string;small?:boolean}) {
  const longHair=!['sasha','nikolai','boris','dima','sergei','ivan','pavel','viktor','igor'].includes(kind), baker=kind==='olya';
  const coat=kind==='lena'?'#567c8d':kind==='boris'?'#ad704a':baker?'#e9b855':kind==='sasha'?'#64866d':kind==='postmaster'?'#42639a':'#b96149';
  return <svg class={small?'delivery-person is-small':'delivery-person'} width={small?46:75} height={small?51:83} viewBox="0 0 100 110" aria-hidden="true">
    <circle cx="50" cy="52" r="45" fill={baker?'#f4e5b3':'#e6e9d6'}/>
    <path d="M14 110V88Q18 71 40 72H61Q83 73 87 94V110" fill={coat}/>
    {longHair&&<path class="delivery-person-long-hair" d="M24 50Q17 13 52 14Q84 12 78 62L86 75H20Z" fill={baker?'#693f2f':'#443a31'}/>}
    <ellipse cx="50" cy="47" rx="24" ry="29" fill="#edbe8f"/>
    <path d="M26 38Q23 10 52 17Q79 16 75 36Q57 34 49 26Q37 39 26 38" fill={baker?'#693f2f':'#443a31'}/>
    <circle cx="41" cy="46" r="2" fill="#27323a"/><circle cx="60" cy="46" r="2" fill="#27323a"/>
    <path d="M43 60Q51 66 59 59" fill="none" stroke="#744536" stroke-width="2.5" stroke-linecap="round"/>
    <path d="M43 72L50 82 58 72" fill="#fff4dd"/>
    {baker&&<><path d="M27 22Q14 7 30 3Q40-5 49 4Q62-4 71 4Q89 10 73 24V30H28Z" fill="#fff8e8"/><path d="M37 78V109H69V78L61 82H43Z" fill="#fff8e8"/></>}
    {kind==='postmaster'&&<><path d="M24 27L27 14H74L79 27Z" fill="#304c7e"/><rect x="42" y="18" width="18" height="8" rx="2" fill="#f2c750"/></>}
    {kind==='lena'&&<g fill="none" stroke="#58616a" stroke-width="2"><circle cx="41" cy="46" r="8"/><circle cx="60" cy="46" r="8"/><path d="M49 45H52"/></g>}
    {kind==='boris'&&<path d="M30 82H70V110H30Z" fill="#e0cd9d"/>}
    {kind==='sasha'&&<path d="M24 26Q27 4 57 10Q79 13 76 30H18" fill="#ad674b"/>}
  </svg>;
}

function Tree({x,y,size=1}:{x:number;y:number;size?:number}) {
  return <g transform={`translate(${x} ${y}) scale(${size})`}><ellipse cy="27" rx="24" ry="8" fill="#8a9c76" opacity=".18"/><path d="M0 25V-3" stroke="#8d7153" stroke-width="7"/><path d="M-26-4Q-35-24-17-30Q-15-55 5-47Q29-48 28-27Q48-7 25 6Q0 21-26-4" fill="#789875"/><path d="M-16-14Q-24-39 3-37Q17-38 18-17" fill="#94ab7d"/></g>;
}

function Building({kind,id,side,colour,showDoor=true}:{kind:string;id:string;side?:string;colour?:string;showDoor?:boolean}) {
  const house=kind==='house',post=kind==='post';
  const roof=colour==='blue'?'#6387a0':colour==='yellow'?'#ba9148':colour==='coral'?'#b76650':id==='house-two'?'#7c8eac':id==='house-one'?'#b97956':'#be6953';
  const wall=colour==='blue'?'#abc4d3':colour==='yellow'?'#f0d178':colour==='coral'?'#e4a68e':'#edd7ac';
  if(kind==='fountain')return <g><ellipse cy="6" rx="52" ry="20" fill="#779799"/><ellipse cy="1" rx="48" ry="16" fill="#a0c9cd"/><path d="M-15-3Q-7-24-7-37H7Q7-22 15-3Z" fill="#c6cdb3"/><ellipse cy="-38" rx="24" ry="8" fill="#7cadb3"/><path d="M0-38V-58M0-52Q-20-72-26-31M0-52Q20-72 26-31" stroke="#a1d2d7" stroke-width="4" fill="none" stroke-linecap="round"/></g>;
  if(kind==='park')return <g><Tree x={-30} y={-17}/><Tree x={24} y={-31} size={1.2}/><path d="M-24 18V-6H24V18M-30-4H30" stroke="#9c7848" fill="none" stroke-width="7"/><path d="M-24 8H24" stroke="#c1a76b" stroke-width="5"/></g>;
  if(kind==='bank')return <g><Tree x={22} y={-22}/><path d="M-30 12H12M-26 12V26M8 12V26M-30 2H12" stroke="#93734e" stroke-width="7"/><path d="M-27-10H10" stroke="#ad8b59" stroke-width="6"/></g>;
  if(kind==='market')return <g transform="translate(0 -55)">
    <path d="M-50 48V-5H50V48M-53-4H53" fill="none" stroke="#987850" stroke-width="6"/>
    <path d="M-58-9L-43-36H43L58-9Z" fill="#e9c25d"/>
    {[-40,-13,14,41].map(x=><path key={x} d={`M${x}-35h12l6 26h-21Z`} fill="#658b78"/>)}
    <path d="M-49 29H49V47H-49Z" fill="#b2915d"/>
    {[-35,-21,-7,7,21,35].map((x,i)=><circle key={x} cx={x} cy="20" r="8" fill={i%2?'#d49e40':'#b65840'}/>)}
  </g>;
  if(kind==='square')return <g><path d="M-34 9L0-10 34 9 0 28Z" fill="#d4c3a0"/><path d="M-18 0L17 18M-1-10L32 9M-17 18L18 0" stroke="#ede1c4" stroke-width="2"/></g>;
  const publicBuilding=['library','school','station','cafe','pharmacy','bank-office'].includes(kind);
  if(!house&&!post&&kind!=='bakery'&&!publicBuilding)return null;
  const bakery=kind==='bakery';
  return <g transform={bakery||side==='south'?'translate(0 47)':'translate(0 -43)'}>
    <ellipse cy="35" rx="61" ry="11" fill="#808770" opacity=".16"/>
    <path d="M-48-40H48V33H-48Z" fill={post?'#dc9b73':house?wall:'#f1dcab'} stroke="#bba784" stroke-width="2"/>
    <path d="M-59-37L-17-70 51-57 60-37Z" fill={roof}/><path d="M-51-38H54" stroke="#854f3d" stroke-width="4"/>
    {showDoor?<><path class="delivery-building-door" d="M-7 33V-6Q7-15 20-6V33" fill={house?'#527b82':'#887457'}/><circle cx="13" cy="14" r="2" fill="#efd686"/></>:<><rect x="-6" y="-20" width="22" height="25" rx="2" fill="#fdf0bf" stroke="#8b9991" stroke-width="2"/><path d="M5-20V5M-6-8H16" stroke="#8b9991" stroke-width="2"/></>}
    <rect x="-35" y="-21" width="21" height="25" rx="2" fill="#fdf0bf" stroke="#8b9991" stroke-width="3"/>
    <path d="M-24-20V4M-35-7H-14" stroke="#8b9991" stroke-width="2"/>
    <rect x="29" y="-21" width="11" height="24" fill="#fdf0bf"/>
    {bakery&&<><path d="M-48-30H48L54-12H-54Z" fill="#f9f0d4"/>{[-40,-15,10,35].map(x=><path key={x} d={`M${x}-30h12l4 18h-16Z`} fill="#b8704d"/>)}<ellipse cx="-24" cy="14" rx="14" ry="7" fill="#d8a752"/><path d="M-31 10l4 6m2-8 4 7" stroke="#f5d483" stroke-width="2"/></>}
    {publicBuilding&&<g transform="translate(0 -44)"><rect x="-31" y="-11" width="62" height="24" rx="3" fill="#f9edcf" stroke="#a99a78"/>
      {kind==='pharmacy'?<path d="M-5-9H5V-3H11V7H5V13H-5V7H-11V-3H-5Z" fill="#547e62"/>:
       kind==='bank-office'?<><path d="M-21-3L0-12 21-3ZM-19 12H19M-13-2V10M0-2V10M13-2V10" fill="#80959d" stroke="#58707c" stroke-width="3"/></>:
       kind==='library'?<path d="M-20-5Q-8-10 0-4Q8-10 20-5V8Q8 3 0 9Q-8 3-20 8ZM0-4V9" fill="#839c9a" stroke="#536d71"/>:
       kind==='cafe'?<><path d="M-12-6H10V4Q0 14-12 4Z" fill="#b77754"/><path d="M10-4Q23-5 20 4Q17 8 10 6" stroke="#b77754" stroke-width="3" fill="none"/></>:
       <><circle r="9" fill="#fff9dd" stroke="#6e8580" stroke-width="2"/><path d="M0-6V0L5 3" fill="none" stroke="#6e8580" stroke-width="2"/></>}
    </g>}
    {post&&<g transform="translate(-27 22)"><rect x="-7" y="-13" width="14" height="24" rx="4" fill="#ba473d"/><path d="M-4-6H4" stroke="#f8d589" stroke-width="2"/></g>}
  </g>;
}

function LegacyDeliveryMap({state,path,position,onNode,disabled,ru}:{state:DeliveryState;path:string[];position:string;onNode:(id:string)=>void;disabled:boolean;ru:boolean}) {
  const byId=Object.fromEntries(state.map.nodes.map(n=>[n.id,n]));
  const tail=path.at(-1)??position;
  const adjacent=new Set(state.map.edges.flatMap(([a,b])=>a===tail?[b]:b===tail?[a]:[]));
  const points=path.map(id=>point(byId[id]));
  const current=point(byId[position]);
  const riverside=state.map.scene==='riverside';
  return <svg class="delivery-map" viewBox="0 0 870 670" role="group" aria-label={ru?'Карта района. Выбирай связанные точки, чтобы построить маршрут.':'Neighbourhood map. Choose connected points to plan a route.'}>
    <defs><pattern id="delivery-paper" width="12" height="12" patternUnits="userSpaceOnUse"><circle cx="1" cy="2" r=".6" fill="#b9ae85" opacity=".17"/></pattern></defs>
    <rect width="870" height="670" rx="28" fill="#e5e7cb"/><rect width="870" height="670" rx="28" fill="url(#delivery-paper)"/>
    {riverside?<><path d="M-30 453Q235 421 455 450T910 456" fill="none" stroke="#accbd0" stroke-width="94"/><path d="M-30 453Q235 421 455 450T910 456" fill="none" stroke="#8ab4bf" stroke-width="2" stroke-dasharray="24 15"/></>:<>
    <path d="M616-20Q582 130 664 211Q719 264 889 240" fill="none" stroke="#accbd0" stroke-width="100"/>
    <path d="M616-20Q582 130 664 211Q719 264 889 240" fill="none" stroke="#8ab4bf" stroke-width="2" stroke-dasharray="24 15" opacity=".55"/></>}
    <text x="38" y="50" class="delivery-map-title">{state.map.name_ru??'ПАРКОВЫЙ КВАРТАЛ'}</text>
    <text x="38" y="75" class="delivery-map-subtitle">{ru?'Маленькие улицы. Новые знакомства.':'Small streets. People to meet.'}</text>
    {(riverside?[[55,380,.6],[805,350,1],[795,570,.7],[285,415,.6],[210,640,.6]]:[[65,200,1.3],[160,135,1],[300,135,.9],[80,590,1.4],[400,620,.7],[590,620,.8],[815,430,1.2],[810,90,.9],[90,350,.8]]).map(([x,y,size],i)=><Tree key={i} x={x} y={y} size={size}/>)}
    {state.map.edges.map(([a,b])=>{const p=point(byId[a]),q=point(byId[b]);return <g key={a+b}><path d={`M${p.x} ${p.y}L${q.x} ${q.y}`} stroke="#c4b798" stroke-width="29" stroke-linecap="round"/><path d={`M${p.x} ${p.y}L${q.x} ${q.y}`} stroke="#f7edd3" stroke-width="23" stroke-linecap="round"/></g>;})}
    <g transform={riverside?"translate(-150 285)":undefined}><path d="M687 106V224M713 106V224" stroke="#957758" stroke-width="6"/>{Array.from({length:10},(_,i)=><path key={i} d={`M687 ${111+i*12}H713`} stroke="#c5a37a" stroke-width="8"/>)}</g>
    {state.map.nodes.map(n=>{const p=point(n);return <g key={n.id} transform={`translate(${p.x} ${p.y})`}><Building kind={n.kind} id={n.id} side={n.building_side}/>{!['street','junction'].includes(n.kind)&&<text y={n.kind==='bakery'||n.building_side==='south'?102:n.kind==='house'||n.kind==='post'?55:44} class="delivery-place-label">{n.label}</text>}</g>;})}
    {state.encounters?.map(encounter=>{const p=point(byId[encounter.position]);return <g key={encounter.position} transform={`translate(${p.x+38} ${p.y-74})`} class="delivery-met-person" aria-label={(ru?'Ты встретил: ':'You met: ')+(ru?encounter.speaker.name:encounter.speaker.name_en)}><Person kind={encounter.speaker.portrait} small/><text x="23" y="64">{ru?encounter.speaker.name:encounter.speaker.name_en}</text></g>;})}
    {points.length>1&&<polyline points={points.map(p=>`${p.x},${p.y}`).join(' ')} fill="none" stroke="#315f8d" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="2 13"/>}
    {state.map.nodes.map(n=>{const p=point(n),active=adjacent.has(n.id)&&!disabled,selected=tail===n.id;return <g key={n.id} transform={`translate(${p.x} ${p.y})`} role="button" tabIndex={active?0:-1} aria-disabled={!active} aria-label={(ru?'Идти: ':'Walk to: ')+(ru?n.label:n.label_en)} onClick={()=>active&&onNode(n.id)} onKeyDown={e=>{if(active&&['Enter',' '].includes(e.key)){e.preventDefault();onNode(n.id);}}} class={`delivery-map-node${active?' is-available':''}${selected?' is-selected':''}`}>
      <circle r="30" fill="transparent"/><circle r={active?12:5} fill={active?'#fcf4da':selected?'#315f8d':'#b3a284'} stroke={active?'#315f8d':'#d6c9ab'} stroke-width={active?3:1}/>{active&&<path d="M-4 0H4M0-4V4" stroke="#315f8d" stroke-width="2"/>}
    </g>;})}
    <g transform={`translate(${current.x} ${current.y})`} class="delivery-barsik" pointer-events="none"><ellipse cy="12" rx="26" ry="9" fill="#6b7665" opacity=".24"/><image href="/static/images/barsik-running-v1.webp" x="-32" y="-45" width="64" height="64" transform={state.heading==='west'?'scale(-1 1)':undefined}/></g>
    <g transform="translate(801 570)" aria-hidden="true"><path d="M0-24L-10 8 0 2 10 8Z" fill="#7b8980"/><text y="-31" text-anchor="middle" font-size="11" fill="#657568">N</text></g>
  </svg>;
}

type MapProps={state:DeliveryState;path:string[];position:string;onNode:(id:string)=>void;disabled:boolean;ru:boolean};
type TownTile=DeliveryTile;
type TownMap=DeliveryMapData;
const clamp=(value:number,min:number,max:number)=>Math.min(Math.max(value,min),Math.max(min,max));
const buildings=new Set(['house','post','bakery','library','school','station','cafe','market','fountain','park','bank','square','pharmacy','bank-office']);

function TownGround({tile,size}:{tile:TownTile;size:number}) {
  const x=tile.x*size,y=tile.y*size,water=['river','water'].includes(tile.kind),garden=['park','garden','trees'].includes(tile.kind),plaza=['plaza','square','paving'].includes(tile.kind);
  return <g transform={`translate(${x} ${y})`} data-tile-kind={tile.kind}>
    <rect width={size+.4} height={size+.4} fill={water||tile.kind==='bridge'?'#91bbc1':garden?'#d2dfb9':plaza?'#e7dec7':tile.kind==='courtyard'?'#e6dfc5':'#e2e6c8'}/>
    {water&&<><path d={`M${size*.13} ${size*.28}q${size*.12} -6 ${size*.24} 0t${size*.24} 0M${size*.4} ${size*.7}q${size*.12} -6 ${size*.24} 0t${size*.24} 0`} fill="none" stroke="#c8e0d7" stroke-width="2" stroke-linecap="round"/><path d={`M${size*.9} 0V${size}`} stroke="#b5d3d1" stroke-width="2" stroke-dasharray="12 17"/></>}
    {plaza&&<path d={`M0 ${size*.5}H${size}M${size*.5} 0V${size}`} stroke="#d1c7ae" stroke-width="1"/>}
    {garden&&<><Tree x={size*.31} y={size*.56} size={size/155}/><Tree x={size*.75} y={size*.79} size={size/190}/></>}
    {tile.kind==='grass'&&(tile.x*3+tile.y)%5===0&&<path d={`M${size*.27} ${size*.46}l-3 -7m3 7 4-9M${size*.71} ${size*.8}l-4-6m4 6 3-8`} stroke="#b4c394" stroke-width="2" stroke-linecap="round"/>}
  </g>;
}

function TownBlock({block,size}:{block:DeliveryBlock;size:number}) {
  const x=block.x*size,y=block.y*size,w=block.width*size,h=block.height*size;
  const green=block.kind==='park',paved=['market','civic','courtyard'].includes(block.kind);
  return <g class={`delivery-town-block block-${block.kind}`} aria-hidden="true">
    <rect x={x} y={y} width={w} height={h} rx={size*.15} fill={green?'#c6d5ae':paved?'#e7dec7':'#d7dfbd'} stroke={green?'#b7c99b':paved?'#d3c8ac':'#ccd5b3'} stroke-width={size*.025}/>
    {paved&&<g stroke="#cbbfa3" stroke-width="1" opacity=".42">{Array.from({length:Math.floor(w/(size*.3))},(_,i)=><path key={`v${i}`} d={`M${x+(i+1)*size*.3} ${y+size*.09}V${y+h-size*.09}`}/>)}{Array.from({length:Math.floor(h/(size*.3))},(_,i)=><path key={`h${i}`} d={`M${x+size*.09} ${y+(i+1)*size*.3}H${x+w-size*.09}`}/>)}</g>}
    {green&&<>{[[.2,.25],[.72,.28],[.2,.72],[.8,.73]].map(([tx,ty],i)=><Tree key={i} x={x+w*tx} y={y+h*ty} size={size/175}/>)}</>}
  </g>;
}

function TownPlot({plot,size}:{plot:DeliveryPlot;size:number}) {
  const x=plot.x*size,y=plot.y*size,w=plot.width*size,h=plot.height*size;
  return <g class={`delivery-town-plot plot-${plot.kind}`} aria-hidden="true">
    <rect x={x} y={y} width={w} height={h} rx={size*.09} fill={plot.kind==='paved'?'#eee4ca':plot.kind==='garden'?'#cbd7b1':'#d9dfbc'} stroke={plot.kind==='paved'?'#d8ccb0':'#bfcda5'} stroke-width={size*.015}/>
    {plot.kind==='garden'&&<>
      <path d={`M${x+size*.09} ${y+size*.1}H${x+w-size*.09}`} fill="none" stroke="#91aa7c" stroke-width={size*.08} stroke-linecap="round"/>
      <Tree x={x+w-size*.22} y={y+size*.32} size={size/290}/>
    </>}
  </g>;
}

const streetStyle={main:{sidewalk:.37,kerb:.27,surface:.235,fill:'#d9d6c5'},residential:{sidewalk:.285,kerb:.205,surface:.175,fill:'#e7dfc9'},path:{sidewalk:.14,kerb:.105,surface:.078,fill:'#ead6b1'}};

function TownStreets({map,size,byId}:{map:TownMap;size:number;byId:Record<string,DeliveryNode>}) {
  const explicit=new Map((map.street_segments??[]).map(edge=>[[edge.from,edge.to].sort().join('|'),edge.kind]));
  const streets=map.edges.flatMap(([a,b])=>{
    if(!byId[a]||!byId[b])return [];
    const from=point(byId[a],map),to=point(byId[b],map);
    const fallback:DeliveryStreet['kind']=byId[a].building_id||byId[b].building_id?'path':'residential';
    const kind=explicit.get([a,b].sort().join('|'))??fallback;
    return [{id:`${a}-${b}`,d:`M${from.x} ${from.y}L${to.x} ${to.y}`,kind}];
  });
  // Paint each layer across the whole network. A later edge can no longer draw
  // its outline over an earlier edge's surface at a corner or intersection.
  return <g class="delivery-town-roads" aria-hidden="true" fill="none" stroke-linecap="square" stroke-linejoin="round">
    {(['sidewalk','kerb','surface'] as const).map(layer=><g key={layer} class={`delivery-town-road-${layer}`}>{streets.map(street=>{
      const style=streetStyle[street.kind];
      return <path key={street.id} d={street.d} data-street-kind={street.kind} stroke={layer==='surface'?style.fill:layer==='kerb'?'#b8b29a':'#f3ead2'} stroke-width={size*style[layer]}/>;
    })}</g>)}
  </g>;
}

function townLabelLines(label:string):string[] {
  const words=label.split(' ');
  if(words.length<2)return [label];
  const middle=Math.ceil(words.length/2);
  return [words.slice(0,middle).join(' '),words.slice(middle).join(' ')];
}

type TownLabel={x:number;y:number;lines:string[];font:number;width:number;height:number;anchor:{x:number;y:number};secondary:boolean;leaderFrom:{x:number;y:number};leaderTo:{x:number;y:number}};
type LabelRect={x:number;y:number;width:number;height:number};
const overlapArea=(a:LabelRect,b:LabelRect)=>Math.max(0,Math.min(a.x+a.width,b.x+b.width)-Math.max(a.x,b.x))*Math.max(0,Math.min(a.y+a.height,b.y+b.height)-Math.max(a.y,b.y));

function townBuildingScales(map:TownMap,size:number,unitsPerPixel:number):Map<string,number> {
  const tiles=(map.tiles??[]).filter(tile=>tile.kind==='building');
  return new Map(tiles.map(tile=>{
    let cap=size/85;
    for(const other of tiles){
      if(other===tile)continue;
      const dx=Math.abs(other.x-tile.x),dy=Math.abs(other.y-tile.y);
      if(dy<1.2&&dx>0)cap=Math.min(cap,dx*size*.91/120);
      if(dx<.9&&dy>0)cap=Math.min(cap,dy*size*.88/120);
    }
    const desired=tile.decorative?size/148:Math.max(size/115,42*unitsPerPixel/120);
    return [tile.building_id??`${tile.x}-${tile.y}`,Math.min(cap,desired)];
  }));
}

function townEntrancePoint(node:DeliveryNode,tile:TownTile,size:number,scale:number) {
  const dx=node.x-tile.x,dy=node.y-tile.y,cx=(tile.x+.5)*size,cy=(tile.y+.5)*size;
  return {x:cx+dx*(60*scale+6),y:dy<0?cy+size*.22-103*scale-8:dy>0?cy+size*.28:cy};
}

function townBuildingBounds(tile:TownTile,size:number,scale:number):LabelRect {
  return {x:(tile.x+.5)*size-60*scale,y:(tile.y+.72)*size-103*scale,width:120*scale,height:103*scale};
}

function rectEdgeToward(rect:LabelRect,toward:{x:number;y:number}) {
  const center={x:rect.x+rect.width/2,y:rect.y+rect.height/2},dx=toward.x-center.x,dy=toward.y-center.y;
  const amount=Math.min(dx?rect.width/2/Math.abs(dx):Infinity,dy?rect.height/2/Math.abs(dy):Infinity);
  return Number.isFinite(amount)?{x:center.x+dx*amount,y:center.y+dy*amount}:center;
}

function crossesRectangle(from:{x:number;y:number},to:{x:number;y:number},rect:LabelRect):boolean {
  let near=0,far=1;
  for(const [start,change,min,max] of [[from.x,to.x-from.x,rect.x,rect.x+rect.width],[from.y,to.y-from.y,rect.y,rect.y+rect.height]]){
    if(Math.abs(change)<.00001){if(start<=min||start>=max)return false;continue;}
    const a=(min-start)/change,b=(max-start)/change;
    near=Math.max(near,Math.min(a,b));far=Math.min(far,Math.max(a,b));
    if(near>=far)return false;
  }
  return near<1&&far>0;
}

function townLabels(map:TownMap,size:number,unitsPerPixel:number,overview:boolean,scales:Map<string,number>):Map<string,TownLabel> {
  const tiles=Object.fromEntries((map.tiles??[]).filter(tile=>tile.kind==='building'&&tile.building_id).map(tile=>[tile.building_id!,tile]));
  const width=(map.width??17)*size,height=(map.height??13)*size;
  const obstacles=(map.tiles??[]).filter(tile=>tile.kind==='building').map(tile=>({id:tile.building_id??`${tile.x}-${tile.y}`,rect:townBuildingBounds(tile,size,scales.get(tile.building_id??`${tile.x}-${tile.y}`)??size/115)}));
  const occupied:LabelRect[]=[],result=new Map<string,TownLabel>();
  const nodes=map.nodes.filter(node=>!['street','junction','road','path','courtyard'].includes(node.kind)&&!(overview&&node.kind==='meeting'))
    .sort((a,b)=>Number(!a.building_id)-Number(!b.building_id)||a.y-b.y||a.x-b.x);
  const items=[...nodes.map(node=>({node,entrance:false})),...map.nodes.filter(node=>node.building_id&&tiles[node.building_id]&&map.nodes.filter(other=>other.building_id===node.building_id).length>1).map(node=>({node,entrance:true}))];
  for(const {node,entrance} of items){
    const building=tiles[node.building_id??''],tile=entrance?undefined:building;
    const scale=scales.get(node.building_id??'')??size/115;
    const anchor=entrance&&building?townEntrancePoint(node,building,size,scale):tile?{x:(tile.x+.5)*size,y:(tile.y+.5)*size}:point(node,map);
    const secondary=entrance||node.kind==='bus-stop'||node.kind==='meeting',font=(secondary?12:14)*unitsPerPixel;
    const title=entrance?(node.entrance==='courtyard'?'Со двора':'Главный вход'):node.kind==='bus-stop'?`Ост. «${node.label}»`:node.label;
    const lines=entrance?[title]:townLabelLines(title);
    const boxWidth=Math.max(...lines.map(line=>line.length))*.58*font+font*.55,boxHeight=lines.length*font*1.12;
    const gap=font*.35,below=tile?anchor.y+size*.38:anchor.y+size*.3,above=tile?anchor.y-size*.98:anchor.y-size*.35;
    const candidates:LabelRect[]=[];
    for(const band of [0,1,2,3,4,5])for(const direction of ['below','above']){
      const top=direction==='below'?below+gap+band*(boxHeight+gap):above-gap-boxHeight-band*(boxHeight+gap);
      candidates.push({x:clamp(anchor.x-boxWidth/2,8,width-boxWidth-8),y:clamp(top,8,height-boxHeight-8),width:boxWidth,height:boxHeight});
    }
    for(const side of [-1,1])for(const distance of [.62,1.05,1.6,2.2])for(const vertical of [0,-.65,.65,-1.3,1.3]){
      candidates.push({x:clamp(anchor.x+side*(size*distance+boxWidth/2)-boxWidth/2,8,width-boxWidth-8),y:clamp(anchor.y-boxHeight/2+vertical*(boxHeight+gap),8,height-boxHeight-8),width:boxWidth,height:boxHeight});
    }
    const leader=(candidate:LabelRect)=>{
      const center={x:candidate.x+candidate.width/2,y:candidate.y+candidate.height/2};
      const from=tile?rectEdgeToward(townBuildingBounds(tile,size,scale),center):anchor;
      return {from,to:rectEdgeToward(candidate,from)};
    };
    // Prefer nearby positions on either side before trying distant label rows.
    // At narrow widths the font occupies more map units, so vertical-first
    // placement otherwise pushes labels several streets from their buildings.
    candidates.sort((a,b)=>Math.hypot(a.x+a.width/2-anchor.x,a.y+a.height/2-anchor.y)-Math.hypot(b.x+b.width/2-anchor.x,b.y+b.height/2-anchor.y));
    const score=(candidate:LabelRect)=>{
      const connector=leader(candidate);
      return occupied.reduce((sum,other)=>sum+overlapArea(candidate,{x:other.x-gap*.35,y:other.y-gap*.35,width:other.width+gap*.7,height:other.height+gap*.7})*4,0)
        +obstacles.reduce((sum,other)=>sum+overlapArea(candidate,other.rect)+(other.id!==node.building_id&&crossesRectangle(connector.from,connector.to,other.rect)?size*size*8:0),0);
    };
    let chosen=candidates[0],best=Infinity;
    for(const candidate of candidates){const value=score(candidate);if(value<best){chosen=candidate;best=value;}if(value===0)break;}
    occupied.push(chosen);
    const connector=leader(chosen);
    result.set(entrance?`entrance:${node.id}`:node.id,{x:chosen.x+boxWidth/2,y:chosen.y+font*.83,lines,font,width:boxWidth,height:boxHeight,anchor,secondary,leaderFrom:connector.from,leaderTo:connector.to});
  }
  return result;
}

function TownEntrance({node,tile,size,scale}:{node:DeliveryNode;tile:TownTile;size:number;scale:number}) {
  const dx=node.x-tile.x,dy=node.y-tile.y;
  const {x,y}=townEntrancePoint(node,tile,size,scale);
  const rotation=dx?90:0,rear=node.entrance==='courtyard';
  return <g class={`delivery-town-entrance${rear?' is-rear':''}`} aria-hidden="true" data-entrance-side={dx<0?'w':dx>0?'e':dy<0?'n':'s'}>
    <title>{rear?'Courtyard entrance':'Building entrance'}</title>
    <g transform={`translate(${x} ${y}) rotate(${rotation})`}>
      <path d="M-14-8H14V10H-14Z" fill="#f3ead2" stroke="#b9b08e" stroke-width="1.5"/>
      <path d="M-11 4V-5M11 4V-5M-11-5H11" fill="none" stroke={rear?'#99784e':'#56786f'} stroke-width="4" stroke-linecap="square"/>
      <path d="M-10 8H10" stroke="#c2b38e" stroke-width="2"/>
    </g>
  </g>;
}

function TownBuilding({tile,size,scale,southEntrance}:{tile:TownTile;size:number;scale:number;southEntrance?:boolean}) {
  const kind=tile.building_kind??'house',id=tile.building_id??`${tile.x}-${tile.y}`;
  if(!buildings.has(kind))return null;
  const low=['market','fountain','park','bank','square'].includes(kind);
  return <g class={`delivery-town-building building-${kind}${tile.decorative?' is-decorative':''}`} transform={`translate(${(tile.x+.5)*size} ${(tile.y+.5)*size+(low?size*.09:kind==='bakery'?size*.22-80*scale:size*.22+10*scale)}) scale(${scale})`} aria-hidden="true">
    <Building kind={kind} id={id} colour={tile.colour} showDoor={southEntrance??(!tile.frontage||tile.frontage==='s')}/>
  </g>;
}

function TownDeliveryMap({state,path,position,onNode,disabled,ru}:MapProps) {
  const map=state.map as TownMap,size=map.tile_size??100,width=(map.width??17)*size,height=(map.height??13)*size;
  const byId=Object.fromEntries(map.nodes.map(n=>[n.id,n]));
  const buildingTiles=Object.fromEntries((map.tiles??[]).filter(tile=>tile.kind==='building'&&tile.building_id).map(tile=>[tile.building_id!,tile]));
  const safePosition=byId[position]?position:map.nodes[0]?.id;
  const tail=byId[path.at(-1)??'']?path.at(-1)!:safePosition;
  const focusId=position!==state.position?safePosition:tail;
  const focus=byId[focusId]?point(byId[focusId],map):{x:width/2,y:height/2};
  const [overview,setOverview]=useState(true),[zoom,setZoom]=useState(1),[offset,setOffset]=useState<{x:number;y:number}|null>(null),[viewportSize,setViewportSize]=useState({width:880,height:660});
  const ratio=viewportSize.width/viewportSize.height;
  const viewport=useRef<SVGSVGElement>(null),drag=useRef<{x:number;y:number;cx:number;cy:number;scaleX:number;scaleY:number;moved:boolean}|null>(null),suppressClick=useRef(false);
  useEffect(()=>setOffset(null),[focusId]);
  useEffect(()=>{
    const node=viewport.current;if(!node||typeof ResizeObserver==='undefined')return;
    const observer=new ResizeObserver(([entry])=>{if(entry.contentRect.width&&entry.contentRect.height)setViewportSize({width:entry.contentRect.width,height:entry.contentRect.height});});
    observer.observe(node);return()=>observer.disconnect();
  },[]);
  const viewWidth=overview?width:Math.min(width,size*11/zoom),viewHeight=overview?height:Math.min(height,viewWidth/ratio);
  const unitsPerPixel=Math.max(viewWidth/viewportSize.width,viewHeight/viewportSize.height);
  const buildingScales=townBuildingScales(map,size,unitsPerPixel);
  const labels=townLabels(map,size,unitsPerPixel,overview,buildingScales);
  const center=offset??focus,x=overview?0:clamp(center.x-viewWidth/2,0,width-viewWidth),y=overview?0:clamp(center.y-viewHeight/2,0,height-viewHeight);
  const current=byId[safePosition]?point(byId[safePosition],map):focus;
  const adjacency=new Set(map.edges.flatMap(([a,b])=>a===tail?[b]:b===tail?[a]:[]));
  const corridorEnds=new Set(corridorChoices(map,tail).map(option=>option.node_id));
  const selectable=new Set([...adjacency,...corridorEnds]);
  const points=path.flatMap(id=>byId[id]?[point(byId[id],map)]:[]);
  const guide=state.interaction==='guide',aboard=state.transport?.status==='aboard';
  const label=(en:string,russian:string)=>ru?russian:en;
  const shift=(dx:number,dy:number)=>{setOverview(false);setOffset({x:clamp(x+viewWidth/2+dx*viewWidth*.42,viewWidth/2,width-viewWidth/2),y:clamp(y+viewHeight/2+dy*viewHeight*.42,viewHeight/2,height-viewHeight/2)});};
  const recenter=()=>{if(overview)setZoom(1);setOverview(false);setOffset({...current});};
  const changeZoom=(amount:number)=>{
    if(overview){if(amount>0){setZoom(1);setOverview(false);}return;}
    const next=clamp(zoom*(amount>0?1.25:1/1.25),.2,2.5);
    if(amount<0&&size*11/next>=width){setOverview(true);setOffset(null);return;}
    setZoom(next);
  };
  const activate=(id:string)=>{if(!suppressClick.current&&!disabled&&selectable.has(id))onNode(id);};
  const seenEncounters=(state.encounters??[]).filter(encounter=>byId[encounter.position]&&encounter.position!==safePosition);
  return <div class={`delivery-town${overview?' is-overview':''}`}>
    <svg ref={viewport} tabIndex={0} class="delivery-town-map" viewBox={`${x} ${y} ${viewWidth} ${viewHeight}`} role="group" aria-label={label('Town map. Select connected streets to plan a route.','Карта города. Выбирай соседние улицы, чтобы построить маршрут.')} data-camera={overview?'overview':'local'}
      onPointerDown={event=>{
        if(overview||event.button!==0)return;
        const bounds=event.currentTarget.getBoundingClientRect();if(!bounds.width||!bounds.height)return;
        suppressClick.current=false;drag.current={x:event.clientX,y:event.clientY,cx:x+viewWidth/2,cy:y+viewHeight/2,scaleX:viewWidth/bounds.width,scaleY:viewHeight/bounds.height,moved:false};
      }}
      onPointerMove={event=>{
        const start=drag.current;if(!start)return;const dx=event.clientX-start.x,dy=event.clientY-start.y;
        if(!start.moved&&Math.hypot(dx,dy)<6)return;
        if(!start.moved)event.currentTarget.setPointerCapture?.(event.pointerId);start.moved=true;suppressClick.current=true;
        setOffset({x:clamp(start.cx-dx*start.scaleX,viewWidth/2,width-viewWidth/2),y:clamp(start.cy-dy*start.scaleY,viewHeight/2,height-viewHeight/2)});
      }}
      onPointerUp={event=>{if(drag.current?.moved)suppressClick.current=true;drag.current=null;if(event.currentTarget.hasPointerCapture?.(event.pointerId))event.currentTarget.releasePointerCapture?.(event.pointerId);}}
      onPointerCancel={()=>{drag.current=null;suppressClick.current=false;}}
      onKeyDown={event=>{if(event.target!==event.currentTarget)return;const movement:Record<string,[number,number]>={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]};if(movement[event.key]){event.preventDefault();shift(...movement[event.key]);}}}>
      <rect width={width} height={height} fill="#e2e6c8"/>
      {(map.tiles??[]).map(tile=><TownGround key={`${tile.x}-${tile.y}`} tile={tile} size={size}/>)}
      {(map.blocks??[]).map(block=><TownBlock key={block.id} block={block} size={size}/>)}
      {(map.plots??[]).map(plot=><TownPlot key={plot.id} plot={plot} size={size}/>)}
      <TownStreets map={map} byId={byId} size={size}/>
      {(map.tiles??[]).filter(tile=>tile.kind==='bridge').map(tile=>{const bx=tile.x*size,by=(tile.y+.5)*size,horizontal=tile.exits?.some(exit=>exit==='e'||exit==='w')??true;return <g key={`bridge-${tile.x}-${tile.y}`} transform={horizontal?undefined:`rotate(90 ${bx+size/2} ${by})`} class="delivery-town-bridge" aria-hidden="true"><rect x={bx-size*.05} y={by-size*.21} width={size*1.1} height={size*.42} fill="#bfa079"/>{Array.from({length:9},(_,i)=><path key={i} d={`M${bx+i*size/8} ${by-size*.2}V${by+size*.2}`} stroke="#e4c99b" stroke-width={size*.025}/>)}<path d={`M${bx-size*.05} ${by-size*.255}H${bx+size*1.05}M${bx-size*.05} ${by+size*.255}H${bx+size*1.05}`} fill="none" stroke="#876e50" stroke-width={size*.045}/></g>;})}
      <g class="delivery-town-frontages" fill="none" stroke="#e9d8b7" stroke-width={size*.1} aria-hidden="true">{map.nodes.filter(node=>node.building_id&&buildingTiles[node.building_id]).map(node=>{
        const tile=buildingTiles[node.building_id!],p=point(node,map),b={x:(tile.x+.5)*size,y:(tile.y+.5)*size};
        return <path key={node.id} d={`M${p.x} ${p.y}L${b.x+(p.x-b.x)*.28} ${b.y+(p.y-b.y)*.28}`}/>;
      })}</g>
      {(map.tiles??[]).filter(tile=>tile.kind==='building').map(tile=><TownBuilding key={`building-${tile.x}-${tile.y}`} tile={tile} size={size} scale={buildingScales.get(tile.building_id??`${tile.x}-${tile.y}`)??size/115} southEntrance={tile.frontage?map.nodes.some(node=>node.building_id===tile.building_id&&node.y>tile.y):undefined}/>)}
      {map.nodes.filter(node=>node.building_id&&buildingTiles[node.building_id]).map(node=><TownEntrance key={`entry-${node.id}`} node={node} tile={buildingTiles[node.building_id!]} size={size} scale={buildingScales.get(node.building_id!)??size/115}/>)}
      {map.nodes.filter(node=>!['street','junction','road','path'].includes(node.kind)).map(node=>{
        const p=point(node,map),tile=buildingTiles[node.building_id??''];
        const rearEntrance=node.kind==='courtyard',noBuilding=!tile;
        const layout=labels.get(node.id);
        const labelX=layout?.x??p.x,labelY=layout?.y??p.y+size*.35;
        return <g key={`landmark-${node.id}`} aria-hidden="true">
          {noBuilding&&buildings.has(node.kind)&&<g transform={`translate(${p.x} ${p.y-size*.35}) scale(${size/170})`}><Building kind={node.kind} id={node.id}/></g>}
          {node.kind==='bus-stop'&&<g transform={`translate(${p.x-size*.24} ${p.y-size*.17})`} class="delivery-town-bus-stop"><path d="M0 0V-37" stroke="#768875" stroke-width="3"/><rect x="-12" y="-54" width="24" height="22" rx="3" fill="#f8edc8" stroke="#7d987b" stroke-width="2"/><rect x="-8" y="-49" width="16" height="10" rx="2" fill="#7999a1"/><path d="M-8-43H8" stroke="#f8edc8" stroke-width="2"/><circle cx="-5" cy="-37" r="2" fill="#4b6656"/><circle cx="5" cy="-37" r="2" fill="#4b6656"/></g>}
          {tile&&!rearEntrance&&layout&&<path class="delivery-town-label-leader" d={`M${layout.leaderFrom.x} ${layout.leaderFrom.y}L${layout.leaderTo.x} ${layout.leaderTo.y}`} fill="none" stroke="#61765b" stroke-width={unitsPerPixel*1.25}/>}
          {!rearEntrance&&layout&&<text x={labelX} y={labelY} font-size={layout.font} stroke-width={unitsPerPixel*3.5} class={`delivery-town-place-label${layout.secondary?' is-secondary':''}`}><title>{node.kind==='bus-stop'?`Bus stop: ${node.label_en}`:node.label_en}</title>{layout.lines.map((line,i)=><tspan key={i} x={labelX} dy={i?'1.12em':0}>{line}</tspan>)}</text>}
        </g>;
      })}
      <g class="delivery-town-entrance-labels" aria-hidden="true" pointer-events="none">{Array.from(labels.entries()).filter(([id])=>id.startsWith('entrance:')).map(([id,layout])=><g key={id}><path class="delivery-town-entrance-leader" d={`M${layout.leaderFrom.x} ${layout.leaderFrom.y}L${layout.leaderTo.x} ${layout.leaderTo.y}`} fill="none" stroke="#536c54" stroke-width={unitsPerPixel*1.25}/><text x={layout.x} y={layout.y} class="delivery-town-entrance-label" font-size={layout.font} stroke-width={unitsPerPixel*3.5} text-anchor="middle">{layout.lines[0]}</text></g>)}</g>
      <g class="delivery-town-districts" aria-hidden="true">{(map.districts??[]).map(district=><text key={district.id} x={district.x*size+size*.22} y={district.y*size+size*.3} class="delivery-town-district" font-size={12*unitsPerPixel} stroke-width={3*unitsPerPixel}>{ru?district.name_ru:district.name}</text>)}</g>
      {points.length>1&&<polyline points={points.map(p=>`${p.x},${p.y}`).join(' ')} class="delivery-town-route" fill="none" stroke="#356582" stroke-width={size*.06} stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="1 10"/>}
      {seenEncounters.map(encounter=>{const p=point(byId[encounter.position],map);return <g key={`met-${encounter.position}`} transform={`translate(${p.x+size*.16} ${p.y-size*.62}) scale(.75)`} class="delivery-met-person delivery-town-contact" aria-label={ru?encounter.speaker.name:encounter.speaker.name_en}><Person kind={encounter.speaker.portrait} small/><text x="23" y="74">{ru?encounter.speaker.name:encounter.speaker.name_en}</text></g>;})}
      {map.nodes.map(node=>{const p=point(node,map),active=selectable.has(node.id)&&!disabled,selected=tail===node.id;return <g key={node.id} transform={`translate(${p.x} ${p.y})`} role="button" tabIndex={active?0:-1} aria-disabled={!active} aria-label={label('Walk to: ','Идти: ')+(node.kind==='bus-stop'?label('Bus stop — ','Остановка — '):'')+(ru?node.label:node.label_en)} onClick={()=>activate(node.id)} onKeyDown={event=>{if(active&&['Enter',' '].includes(event.key)){event.preventDefault();suppressClick.current=false;activate(node.id);}}} class={`delivery-map-node delivery-town-node${active?' is-available':''}${selected?' is-selected':''}`}>
        <circle r={size*.22} fill="transparent"/>{(active||selected)&&<circle r={active?(corridorEnds.has(node.id)?size*.14:size*.09):size*.065} fill={active?'#fff8df':'#356582'} stroke={active?'#356582':'#eee2c2'} stroke-width={active?2.5:1.5}/>} {active&&<path d="M-4 0H4M0-4V4" stroke="#356582" stroke-width="2"/>}
      </g>;})}
      {(map.closures??[]).filter(closure=>byId[closure.node_id]).map(closure=>{const p=point(byId[closure.node_id],map);return <g key={`closure-${closure.node_id}`} transform={`translate(${p.x} ${p.y})`} class="delivery-town-closure" pointer-events="none"><title>{ru?closure.reason_ru:closure.reason}</title><path d="M-23-11V15M23-11V15" stroke="#8d6d52" stroke-width="5"/><rect x="-30" y="-13" width="60" height="13" rx="2" fill="#f7edd3" stroke="#a17151"/>{[-22,-4,14].map(dx=><path key={dx} d={`M${dx}-12l10 12h8l-10-12Z`} fill="#bd6550"/>)}</g>;})}
      <g transform={`translate(${current.x} ${current.y})`} class="delivery-barsik delivery-town-traveller" pointer-events="none" aria-label={aboard?label('Barsik on the bus','Барсик в автобусе'):guide?label('Your visitor','Твой собеседник'):'Barsik'}>
        <ellipse cy={size*.08} rx={size*.23} ry={size*.085} fill="#64725d" opacity=".22"/>
        {aboard?<g class="delivery-town-bus" transform={`scale(${size/100})${state.heading==='west'?' scale(-1 1)':''}`}><title>{ru?state.transport?.label_ru:state.transport?.label}</title><rect x="-38" y="-36" width="76" height="42" rx="8" fill="#d9aa49" stroke="#8b7145" stroke-width="2"/><path d="M-38-2H38V3H-38Z" fill="#f8ecc9"/><rect x="-31" y="-29" width="17" height="18" rx="2" fill="#a7c4c6"/><rect x="-10" y="-29" width="17" height="18" rx="2" fill="#a7c4c6"/><rect x="13" y="-29" width="18" height="25" rx="2" fill="#a7c4c6" stroke="#a98b4a" stroke-width="2"/><path d="M14-13H31" stroke="#eee1bd" stroke-width="2"/><circle cx="-24" cy="6" r="8" fill="#445a5b"/><circle cx="24" cy="6" r="8" fill="#445a5b"/><circle cx="-24" cy="6" r="3" fill="#d2d7bf"/><circle cx="24" cy="6" r="3" fill="#d2d7bf"/><path d="M35-14H38" stroke="#fff2c0" stroke-width="4"/></g>:guide?<g transform={`translate(${-size*.2} ${-size*.58}) scale(${size/120})`}><Person kind={state.speaker.portrait} small/></g>:<image href="/static/images/barsik-running-v1.webp" x={-size*.29} y={-size*.5} width={size*.58} height={size*.58} transform={state.heading==='west'?'scale(-1 1)':undefined}/>}
        <g transform={`rotate(${{north:0,east:90,south:180,west:270}[state.heading]??0})`}><path d={`M0 ${-size*.65}l${-size*.06} ${size*.1}h${size*.12}Z`} fill="#315a78" stroke="#fff7db" stroke-width="1"/></g>
      </g>
      {!overview&&<svg x={x+viewWidth-viewWidth*.22} y={y+viewHeight-viewWidth*.175} width={viewWidth*.2} height={viewWidth*.153} viewBox={`0 0 ${width} ${height}`} class="delivery-town-minimap" aria-hidden="true" pointer-events="none"><rect width={width} height={height} rx="50" fill="#f5f1dc" stroke="#aab797" stroke-width="20"/>{(map.tiles??[]).filter(tile=>tile.kind==='river'||tile.kind==='bridge').map(tile=><rect key={`${tile.x}-${tile.y}`} x={tile.x*size} y={tile.y*size} width={size} height={size} fill="#98bdc3"/>)}{map.edges.map(([a,b])=>{if(!byId[a]||!byId[b])return null;const p=point(byId[a],map),q=point(byId[b],map);return <path key={`${a}-${b}`} d={`M${p.x} ${p.y}L${q.x} ${q.y}`} stroke="#b9b492" stroke-width="23" fill="none"/>;})}<rect x={x} y={y} width={viewWidth} height={viewHeight} fill="#587991" fill-opacity=".13" stroke="#587991" stroke-width="22"/><circle cx={current.x} cy={current.y} r="34" fill="#cb723b" stroke="#fff6d8" stroke-width="10"/></svg>}
      <g transform={`translate(${x+viewWidth-27*viewWidth/600} ${y+35*viewWidth/600}) scale(${viewWidth/600})`} class="delivery-town-compass" aria-hidden="true" pointer-events="none"><circle cy="8" r="20" fill="#f7f3dc" opacity=".88"/><path d="M0-1L-5 14 0 10 5 14Z" fill="#657969"/><text y="-6" text-anchor="middle" font-size="9" fill="#657969">N</text></g>
    </svg>
    <div class="delivery-town-tools" role="group" aria-label={label('Map controls','Управление картой')}>
      <div class="delivery-town-camera"><button type="button" aria-pressed={overview} onClick={()=>{if(overview)setZoom(1);setOverview(value=>!value);setOffset(null);}}>{overview?label('Explore streets','Посмотреть улицы'):label('Whole town','Весь город')}</button><button type="button" onClick={recenter} aria-label={guide?label('Centre on your visitor','Показать собеседника'):label('Centre on Barsik','Показать Барсика')}>{label('Centre','В центр')}</button></div>
      <div class="delivery-town-pan" role="group" aria-label={label('Move the map','Сдвинуть карту')}><button type="button" aria-label={label('Move map left','Сдвинуть карту влево')} disabled={overview||x<=0} onClick={()=>shift(-1,0)}>←</button><button type="button" aria-label={label('Move map up','Сдвинуть карту вверх')} disabled={overview||y<=0} onClick={()=>shift(0,-1)}>↑</button><button type="button" aria-label={label('Move map down','Сдвинуть карту вниз')} disabled={overview||y+viewHeight>=height} onClick={()=>shift(0,1)}>↓</button><button type="button" aria-label={label('Move map right','Сдвинуть карту вправо')} disabled={overview||x+viewWidth>=width} onClick={()=>shift(1,0)}>→</button></div>
      <div class="delivery-town-zoom" role="group" aria-label={label('Map zoom','Масштаб карты')}><button type="button" aria-label={label('Zoom out','Уменьшить')} disabled={overview} onClick={()=>changeZoom(-.2)}>−</button><button type="button" aria-label={label('Zoom in','Увеличить')} disabled={!overview&&zoom>=2.5} onClick={()=>changeZoom(.2)}>+</button></div>
    </div>
  </div>;
}

export function DeliveryMap(props:MapProps) {
  return props.state.map.scene==='town'?<TownDeliveryMap {...props}/>:<LegacyDeliveryMap {...props}/>;
}
