import type {SpatialVisual} from './journey-games-api';

const palette={red:'#bb6656',blue:'#577fa6',yellow:'#d8ae44',green:'#78976a'};

function Subject({visual,x,y,scale=1}:{visual:SpatialVisual;x:number;y:number;scale?:number}) {
  const color=palette[visual.color??'blue'];
  const flat=visual.orientation==='flat';
  return <g class="scene-spatial-subject" data-subject={visual.subject} data-orientation={visual.orientation} data-color={visual.color} transform={`translate(${x} ${y}) scale(${scale})`}>
    <ellipse cx="0" cy="2" rx="46" ry="8" fill="#7d6d52" opacity=".14"/>
    {visual.subject==='book'&&<g transform={flat?'translate(0 -2) scale(1 .27) skewX(-22)':undefined}>
      <path d="M-32-76H31V-2H-32Z" fill={color} stroke="#4e5557" stroke-width="2"/>
      <path d="M-25-76V-2" stroke="#fff1d1" stroke-opacity=".5" stroke-width="3"/>
      <path d="M-23-1H31V-9H-23" fill="#f6eed9" stroke="#a6a090" stroke-width="1.5"/>
      <path d="M-11-55H16m-27 12h21" stroke="#fff1d1" stroke-width="3" stroke-linecap="round"/>
    </g>}
    {visual.subject==='letter'&&<g transform={flat?'scale(1 .45) skewX(-18)':undefined}>
      <rect x="-44" y="-57" width="88" height="54" rx="3" fill={visual.color?color:'#f8eed2'} stroke="#95856e" stroke-width="2"/>
      <path d="m-43-55 43 29 43-29m-86 50 29-21m57 21-29-21" fill="none" stroke="#95856e" stroke-width="2"/>
    </g>}
    {visual.subject==='ball'&&<g><circle cy="-36" r="35" fill={color} stroke="#536267" stroke-width="2"/><path d="M-24-62q31 20 4 55m43-56Q-8-40 24-12" fill="none" stroke="#f8ecd2" stroke-width="5"/></g>}
    {visual.subject==='cup'&&<g><path d="M23-55q32-5 28 18Q46-16 24-24" fill="none" stroke={color} stroke-width="10"/><path d="M-29-60H29l-5 49q-24 14-48 0Z" fill={color} stroke="#586361" stroke-width="2"/><ellipse cy="-59" rx="29" ry="7" fill="#f6ebd1" stroke="#586361" stroke-width="2"/><ellipse cy="-58" rx="23" ry="3" fill="#a57e59"/></g>}
    {visual.subject==='bag'&&<g><path d="M-19-61v-12q19-23 38 0v12" fill="none" stroke="#74634e" stroke-width="7"/><path d="M-34-65H34l7 60H-41Z" fill={color} stroke="#586361" stroke-width="2"/><path d="M-19-65v12m38-12v12" stroke="#e5d4ae" stroke-width="4"/></g>}
    {visual.subject==='cat'&&<g><path d="M25-7q47 11 38-35" fill="none" stroke="#b78658" stroke-width="12" stroke-linecap="round"/><ellipse cy="-28" rx="31" ry="29" fill="#c89967"/><path d="m-24-53-3-28 22 15 22-3 16-15 1 34q-25 28-58-3Z" fill="#c89967" stroke="#a87c50" stroke-width="1.5"/><path d="m-21-61-1-12 11 8m33-2 7-9v15" fill="#dcad94"/><circle cx="-12" cy="-53" r="3" fill="#435254"/><circle cx="15" cy="-53" r="3" fill="#435254"/><path d="m-3-44 7 0-4 5Z" fill="#8e6153"/><path d="m-17-8-2 7m35-7 2 7" stroke="#a87c50" stroke-width="8" stroke-linecap="round"/></g>}
  </g>;
}

function Anchor({kind,front=false,open=false}:{kind:SpatialVisual['anchor'];front?:boolean;open?:boolean}) {
  if(kind==='box')return <g class={front?'scene-spatial-front':'scene-spatial-anchor'} data-anchor={kind}>
    {front?<><path d="M207 269h186v83H207Z" fill="#c79e6a" stroke="#967650" stroke-width="3"/><path d="M301 272v77" stroke="#e2bf86" stroke-width="11"/></>:<><path d="m207 269 27-59h132l27 59Z" fill={open?'#9e7952':'#d5b17a'} stroke="#806449" stroke-width="3"/>{open&&<path d="m234 210-35-30-27 70 35 18m160-58 32-31 32 69-36 20" fill="#d5b17a" stroke="#967650" stroke-width="3"/>}</>}
  </g>;
  if(front)return null;
  return <g class="scene-spatial-anchor" data-anchor={kind}>
    {kind==='table'?<><path d="M214 231v113m170-113v113" stroke="#987553" stroke-width="16"/><path d="M201 225h196v39H201Z" fill="#b28c60"/><path d="m196 216 24-20h157l25 20v18H196Z" fill="#cea776" stroke="#977653" stroke-width="3"/></>:kind==='chair'?<><path d="M234 255v90m133-90v90" stroke="#987553" stroke-width="13"/><path d="M241 250V134h119v116" fill="#bd996c" stroke="#987553" stroke-width="8"/><path d="M258 150v82m26-82v82m27-82v82m28-82v82" stroke="#f3e7ca" stroke-width="13"/><path d="m223 245 17-15h122l17 15v17H223Z" fill="#cda774" stroke="#987553" stroke-width="3"/></>:<><rect x="208" y="173" width="184" height="174" fill="#bb996e" stroke="#947555" stroke-width="9"/><rect x="224" y="188" width="152" height="62" fill="#e2c8a0"/><rect x="224" y="267" width="152" height="62" fill="#e2c8a0"/><path d="M208 257h184m-184 89v10m184-10v10" stroke="#947555" stroke-width="9"/></>}
  </g>;
}

/** Position and paint order both express the relation; no text answer is drawn. */
export function SpatialIllustration({visual}:{visual:SpatialVisual}) {
  const {anchor,relation}=visual;
  const top={table:195,chair:230,box:240,shelf:168}[anchor];
  const pose=relation==='on'?{x:300,y:top}:relation==='under'?{x:300,y:338}:relation==='beside'?{x:107,y:347}:relation==='in-front'?{x:300,y:382}:relation==='in'?{x:300,y:296}:{x:300,y:anchor==='shelf'?198:anchor==='chair'?181:250};
  const behind=relation==='behind';
  const afterBox=anchor==='box'&&['in-front','beside'].includes(relation);
  const subject=<Subject visual={visual} {...pose} scale={behind?.85:1}/>;
  return <svg viewBox="0 0 500 410" class="scene-route-art scene-spatial-art" data-relation={relation} data-setting={visual.setting} aria-hidden="true">
    <path d="M0 0h500v410H0Z" fill="#f7efdc"/><path d="M0 321h500v89H0Z" fill="#e6d4ad"/><path d="M0 321h500" stroke="#d5c39c" stroke-width="3"/>
    {visual.setting==='classroom'?<g><rect x="34" y="46" width="155" height="88" rx="4" fill="#8caa96" stroke="#b09169" stroke-width="7"/><path d="M52 115h116" stroke="#ebead4" stroke-width="3"/></g>:visual.setting==='office'?<g><rect x="54" y="48" width="87" height="77" rx="4" fill="#faf3de" stroke="#baa17c" stroke-width="3"/><path d="M54 68h87m-70 17h51m-51 18h51" stroke="#a7b8b3" stroke-width="4"/></g>:<g><rect x="40" y="47" width="135" height="102" rx="5" fill="#c3d9d6" stroke="#e4d4b5" stroke-width="8"/><path d="M107 48v101m-67-51h135" stroke="#faf0d8" stroke-width="6"/></g>}
    {behind&&subject}
    <Anchor kind={anchor} open={relation==='in'}/>
    {!behind&&!afterBox&&subject}
    {anchor==='box'&&<Anchor kind="box" front/>}
    {/* Front/beside objects must remain in front of a box, too. */}
    {afterBox&&subject}
  </svg>;
}
