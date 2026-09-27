import {useGameLanguage} from './GameLocale';
import type {GameOptions, GameRound, MotionVisual, SceneSlotResult} from './journey-games-api';
import './styles/scene-builder.css';

const topics = [
  ['location', 'Location', 'Местоположение', 'Prepositions and endings', 'Предлоги и окончания'],
  ['motion', 'Verbs of motion', 'Глаголы движения', 'Walking, travelling and arriving', 'Пешком, на транспорте, прибытие'],
  ['placement', 'Position and placement', 'Положение предметов', 'Lying, standing and putting', 'Лежит, стоит, положить, поставить'],
  ['agreement', 'Agreement', 'Согласование', 'Adjectives and noun endings', 'Прилагательные и окончания'],
  ['roles', 'Who does what?', 'Кто что делает?', 'Subjects and objects', 'Кто действует и на кого'],
  ['mixed', 'Mixed practice', 'Смешанная практика', 'Mix the five topics', 'Все пять тем'],
] as const;

const motionLevels = [
  ['A1', 'Everyday journeys', 'Повседневные маршруты', 'Walking or travelling, regular trips and setting off. Present, past and future.', 'Пешком или на транспорте, регулярные поездки и начало пути. Настоящее, прошедшее и будущее время.'],
  ['A2', 'Arriving, leaving and carrying', 'Приходить, уходить, нести', 'Arrive, leave, enter or cross. Practise verb pairs such as приходить / прийти, and learn to carry things or lead someone.', 'Приходить или прийти, уходить или уйти. Входить, пересекать улицу, нести вещи и вести людей.'],
  ['B1', 'Complex journeys', 'Сложные маршруты', 'Combine movements in longer routes and situations with more than one action.', 'Несколько действий в одном маршруте: пройти мимо, обойти препятствие и продолжить путь.'],
] as const;

export function SceneBuilderOptions({options, onChange, disabled}: {
  options: GameOptions; onChange: (options: GameOptions) => void; disabled: boolean;
}) {
  const ru=useGameLanguage()==='ru';
  const motion=['motion','mixed'].includes(options.grammar_focus??'location');
  const motionLevel=options.motion_level??'A1';
  const levelDescription=motionLevels.find(([level])=>level===motionLevel)!;
  return <div class="scene-options">
    <fieldset disabled={disabled}><legend>{ru?'Что будем практиковать?':'What would you like to practise?'}</legend>
      <div class="scene-topic-grid">{topics.map(([id,en,russian,detail,detailRu])=><button key={id} type="button" class="scene-topic" aria-label={ru?russian:en} aria-pressed={(options.grammar_focus??'location')===id} onClick={()=>onChange({...options,grammar_focus:id})}><strong>{ru?russian:en}</strong><span>{ru?detailRu:detail}</span></button>)}</div>
    </fieldset>
    {motion&&<fieldset disabled={disabled} class="scene-motion-level"><legend>{ru?'Уровень глаголов движения':'Motion level'}</legend>
      <div class="scene-level-buttons">{motionLevels.map(([level,en,russian])=><button type="button" key={level} aria-label={`${level} ${ru?russian:en}`} aria-pressed={motionLevel===level} onClick={()=>onChange({...options,motion_level:level})}><strong>{level}</strong><span>{ru?russian:en}</span></button>)}</div>
      <p class="scene-level-description">{ru?levelDescription[4]:levelDescription[3]}</p>
    </fieldset>}
    <fieldset disabled={disabled} class="scene-length"><legend>{ru?'Длина игры':'Game length'}</legend>{([5,10] as const).map(rounds=><button type="button" key={rounds} aria-pressed={options.rounds===rounds} onClick={()=>onChange({...options,rounds})}>{rounds} {ru?'заданий':'rounds'}</button>)}</fieldset>
  </div>;
}

function MotionPerson({x, y, facing=1, scale=1, carrying=false, standing=false, coat='#73989a'}: {x:number;y:number;facing?:number;scale?:number;carrying?:boolean;standing?:boolean;coat?:string}) {
  return <g class="scene-motion-person" transform={`translate(${x} ${y}) scale(${facing*scale} ${scale})`}>
    <ellipse cx="2" cy="73" rx="32" ry="7" fill="#857357" opacity=".13"/>
    <path d={standing?'m-10 35-2 35m23-35 2 35':'m-8 35-12 35m28-35 19 31'} stroke="#3f5359" stroke-width="10" stroke-linecap="round"/>
    <path d={standing?'m-12 70 8 1m17-1 8 1':'m-12 70-9 3m46-7 9 3'} stroke="#5d5049" stroke-width="7" stroke-linecap="round"/>
    <path d="M-14-9Q1-17 15-6l6 43H-22Z" fill={coat}/>
    <path d={carrying?'m-13 2 10 19 22-1':'m-12 0-13 19m38-18 17 13'} fill="none" stroke={coat} stroke-width="10" stroke-linecap="round"/>
    <circle cx="2" cy="-31" r="18" fill="#e6b590"/><path d="M-16-28q-6-28 19-26q21-1 20 21L9-42-9-31Z" fill="#795448"/>
    <circle cx="13" cy="-30" r="1.8" fill="#3f5055"/><path d="m17-23 5 1-4 3" fill="#e6b590"/>
    {carrying&&<g><rect x="9" y="2" width="37" height="30" rx="3" fill="#c9a568" stroke="#a9834f" stroke-width="2"/><path d="M26 3v10m-16 3h34" stroke="#f7e2b7" stroke-width="5"/><path d="m5 21 13 1" stroke="#e6b590" stroke-width="7" stroke-linecap="round"/></g>}
  </g>;
}

function MotionTransport({kind, x, y, facing, scale=1}: {kind:MotionVisual['transport'];x:number;y:number;facing:number;scale?:number}) {
  const long=kind==='bus'||kind==='train';
  return <g class="scene-motion-vehicle" transform={`translate(${x} ${y}) scale(${facing*scale} ${scale})`}>
    <ellipse cy="35" rx={long?78:66} ry="9" fill="#857357" opacity=".14"/>
    {kind==='train'?<>
      <path d="M-76 43H88m-164 9H88m-152-13v18m25-18v18m25-18v18m25-18v18m25-18v18m25-18v18" stroke="#968e7f" stroke-width="3"/>
      <path d="M-75-38H42q28 0 36 44v22H-75Z" fill="#78989b" stroke="#506f74" stroke-width="2"/>
      <path d="M-73 10H76" stroke="#f3dfb4" stroke-width="8"/><path d="m-19-39 17-17 20 17m-29-17h21" fill="none" stroke="#657578" stroke-width="4"/>
      {[-58,-28,2].map(cx=><rect key={cx} x={cx} y="-25" width="21" height="22" rx="4" fill="#e1edf0"/>)}<path d="M39-26h7q16 2 20 23H39Z" fill="#e1edf0"/>
    </>:kind==='bus'?<>
      <rect x="-75" y="-40" width="150" height="69" rx="13" fill="#bf8e65" stroke="#947052" stroke-width="2"/>
      {[-61,-28,5].map(cx=><rect key={cx} x={cx} y="-28" width="26" height="25" rx="4" fill="#d6e6e6"/>)}<rect x="42" y="-28" width="22" height="47" rx="4" fill="#d6e6e6"/><path d="M-74 7H30" stroke="#ead6a9" stroke-width="8"/><path d="M53-27v46" stroke="#947052" stroke-width="2"/>
    </>:<>
      <path d="m-52-3 18-30h48L44-5l17 6q9 4 9 15v13H-65V9q0-10 13-12Z" fill={kind==='taxi'?'#d7ae58':'#7f9ea1'} stroke={kind==='taxi'?'#b98d42':'#5c7e83'} stroke-width="2"/>
      <path d="m-37-5 12-20h13v20Zm32-20h16L31-5H-5Z" fill="#dce9e7"/>
      {kind==='taxi'&&<><rect x="-13" y="-43" width="31" height="11" rx="3" fill="#f7e7b5"/><path d="M-7-38H11" stroke="#795f37" stroke-width="3"/></>}
      <path d="M54 8h10" stroke="#f8e9b4" stroke-width="5" stroke-linecap="round"/>
    </>}
    {(long?[-48,47]:[-39,42]).map(cx=><g key={cx}><circle cx={cx} cy="28" r="12" fill="#46575a"/><circle cx={cx} cy="28" r="5" fill="#b2b9ad"/></g>)}
  </g>;
}

function MotionIllustration({visual}: {visual:MotionVisual}) {
  const {mode,stage,setting,destination}=visual;
  const leaving=stage==='departure'||stage==='exit';
  const outdoors=setting==='park'||setting==='bridge'||setting==='street';
  const doorway=stage==='enter'||stage==='exit';
  // Completed actions belong beyond their boundary; arrows show the route
  // already taken. Scale entering figures to the courtyard/doorway depth.
  const personPose=stage==='enter'?(setting==='courtyard'?{x:391,y:230,scale:.58}:{x:421,y:248,scale:.46}):stage==='exit'?{x:252,y:249,scale:.9}:stage==='cross'?{x:397,y:249,scale:.9}:['arrival','approach','return'].includes(stage)?{x:368,y:248,scale:.83}:leaving?{x:150,y:243,scale:1}:['past','detour'].includes(stage)?{x:443,y:257,scale:.86}:{x:190,y:243,scale:1};
  const vehiclePose=stage==='enter'?{x:388,y:246,scale:.58}:stage==='exit'?{x:208,y:286,scale:1}:stage==='cross'?{x:412,y:283,scale:.78}:['arrival','approach','return'].includes(stage)?{x:350,y:306,scale:.82}:leaving?{x:156,y:288,scale:.95}:['past','detour'].includes(stage)?{x:423,y:310,scale:.7}:{x:189,y:282,scale:1};
  const routes:Record<MotionVisual['stage'],{path:string;x:number;y:number;angle:number}[]>={
    journey:[{path:'M67 337Q191 346 304 305',x:304,y:305,angle:-21}],
    habit:[{path:'M88 316Q196 283 301 316',x:301,y:316,angle:18},{path:'M301 353Q196 386 88 353',x:88,y:353,angle:198}],
    arrival:[{path:'M66 337Q228 355 367 287',x:367,y:287,angle:-28}],
    departure:[{path:'M366 287Q232 346 79 337',x:79,y:337,angle:183}],
    enter:setting==='courtyard'?[{path:'M76 339Q317 367 388 279',x:388,y:279,angle:-48}]:[{path:'M76 339Q334 366 421 286',x:421,y:286,angle:-43}],
    exit:[{path:'M392 280Q290 351 79 337',x:79,y:337,angle:184}],
    cross:[{path:'M62 337H438',x:438,y:337,angle:0}],
    approach:[{path:'M237 349Q304 355 367 327',x:367,y:327,angle:-24}],
    past:[{path:'M63 343Q248 378 441 323',x:441,y:323,angle:-16}],
    detour:[{path:'M65 329C81 272 144 268 186 294S266 380 425 320',x:425,y:320,angle:-22}],
    return:[{path:'M358 327C202 391 86 309 125 271C164 236 229 281 252 303Q297 340 366 292',x:366,y:292,angle:-35}],
  };
  const tree=(x:number,y:number,scale=1)=><g transform={`translate(${x} ${y}) scale(${scale})`}><path d="M0-5v71" stroke="#937556" stroke-width="11" stroke-linecap="round"/><path d="M-38-15Q-44-50-13-51Q-1-77 22-51Q58-45 42-10Q52 17 18 23Q-19 39-39 12Q-51 1-38-15Z" fill="#a9b68b"/><path d="m0 28-17-14M0 12 16-6" stroke="#84946c" stroke-width="4" fill="none"/></g>;
  const sign=<g><rect x="304" y={outdoors?175:160} width="164" height="35" rx="6" fill="#fbf2db" stroke="#b8a57d" stroke-width="2"/><text x="386" y={outdoors?198:183} text-anchor="middle" fill="#4c5d5e" font-size={destination.length>13?14:18} font-weight="600" font-family="var(--wp-font-reading, sans-serif)">{destination}</text></g>;
  return <svg viewBox="0 0 500 410" class="scene-route-art" aria-hidden="true">
    <path fill="#f7efdc" d="M0 0h500v410H0Z"/><circle cx="92" cy="77" r="31" fill="#efdaa3"/>
    <path d="M0 214q89-37 174-4t174 0q92-37 152-12v212H0Z" fill="#dedec2"/><path d="M0 286q242-22 500 2v122H0Z" fill="#e9d6af"/>
    <path d="M0 323q235-24 500-3v90H0Z" fill="#f1e3c8"/>
    {tree(47,200,.62)}
    {setting==='park'?<>
      {tree(328,176,1.05)}{tree(448,207,.75)}{['approach','departure'].includes(stage)?<g fill="none" stroke="#8d9b8b" stroke-width="5"><path d="M323 278v-68m130 68v-68m-130 20h130m-130 38h130"/>{[339,355,371,387,403,419,435].map(x=><path key={x} d={`M${x} 228v49`}/>)}</g>:<path d="M302 244h101m-96 12h97m-88-9v29m79-29v29" stroke="#ae8c61" stroke-width="7" stroke-linecap="round"/>}
      <path d="M320 205v70m132-70v70" stroke="#a68e67" stroke-width="5"/>{sign}
    </>:setting==='bridge'?<>
      <path d="M138 410V266q74-24 143 0v144" fill="#a4c2c3"/><path d="M148 376q33-12 52 0m15 19q30-12 57 0" stroke="#d5e3dc" stroke-width="5" fill="none" stroke-linecap="round"/>
      <rect class="scene-motion-bridge" x="100" y="287" width="219" height="65" fill="#c8bca0"/><path d="M95 283h230m-230 32h230" stroke="#a28c6d" stroke-width="7"/>{[106,143,180,217,254,291,318].map(x=><path key={x} d={`M${x} 282v37`} stroke="#a28c6d" stroke-width="5"/>)}
      <path d="M320 210v67m132-67v67" stroke="#a68e67" stroke-width="5"/>{sign}
    </>:setting==='street'?<>
      {stage==='cross'?<><path d="M155 410 196 222h94l43 188" fill="#b9b7a8"/>{[267,287,307,327,347].map((y,i)=><path key={y} d={`M${188-i*4} ${y}h${108+i*8}v11H${188-i*4}Z`} fill="#f8f0d9"/>)}</>:<><path d="M310 276V159h151v117" fill="#d7c7aa"/><path d="M302 151h167v12H302Z" fill="#b79b76"/><rect x="327" y="219" width="47" height="42" rx="3" fill="#abc4c3" stroke="#f6e8c9" stroke-width="4"/><rect x="398" y="217" width="44" height="60" rx="3" fill={doorway?'#627778':'#91aaa5'}/>{doorway&&<path d="m398 217 14 9v51h-14Z" fill="#b99b70"/>}<path d="M0 372h500m-440 0 8-30m90 30 5-24m191 24-5-27m95 27-8-33" stroke="#d8c6a5" stroke-width="2"/></>}
      <path d="M323 210v68m130-68v68" stroke="#a68e67" stroke-width="5"/>{sign}
    </>:setting==='courtyard'?<>
      <rect class="scene-motion-courtyard-interior" x="330" y="196" width="113" height="89" fill="#c9cfac"/>
      <path d="M297 285V150h33v135m113 0V150h33v135" fill="#cab799"/><path d="M320 162q66-51 132 0" stroke="#bcaa8b" stroke-width="18" fill="none"/>
      <path d="m331 201-12 10v67l12-9Zm112 0 12 10v67l-12-9Z" fill="#a9b79c" stroke="#81937f" stroke-width="3"/><path d="M330 285h113" stroke="#a1aa8b" stroke-width="4"/>{tree(385,185,.5)}{sign}
    </>:<>
      <path d="M295 291V144h177v147" fill={setting==='home'?'#cebaa0':'#d8c5a4'}/>
      {setting==='home'?<path d="m282 151 101-78 102 78Z" fill="#b87960"/>:<path d="M286 139h195v16H286Z" fill="#ad8967"/>}
      <rect x="310" y="209" width="49" height="46" rx="4" fill="#abc4c3" stroke="#f6e8c9" stroke-width="5"/><path d="M335 211v42m-23-21h44" stroke="#f6e8c9" stroke-width="3"/>
      <rect class="scene-motion-doorway" x="377" y="213" width="64" height="78" rx="4" fill={doorway?'#627778':'#91aaa5'}/>
      {doorway?<path d="m378 214 25 14v64l-25-1Z" fill="#b99b70" stroke="#967f60" stroke-width="2"/>:<><path d="M409 215v75" stroke="#e6d7b6" stroke-width="4"/><path d="M402 255v10m14-10v10" stroke="#e6d7b6" stroke-width="3"/></>}
      <path d="M369 293h80" stroke="#b2a181" stroke-width="6" stroke-linecap="round"/>
      {setting==='shop'&&<><path d="M294 185h180l-12 24H306Z" fill="#bb8066"/>{[315,352,389,426].map(x=><path key={x} d={`M${x} 185h18l3 24h-22Z`} fill="#f3dfbb"/>)}</>}
      {setting==='station'&&<g><circle cx="383" cy="117" r="18" fill="#f9f0d9" stroke="#9f8d6d" stroke-width="3"/><path d="M383 104v13l10 5" fill="none" stroke="#6d776b" stroke-width="3" stroke-linecap="round"/></g>}
      {setting==='airport'&&<g transform="translate(391 105)"><path d="m-40 5 31-10 5-21 8-2 6 22 29 8v7L7 5 3 22h-7L-8 5l-32 8Z" fill="#8b9e9b"/></g>}
      {sign}
    </>}
    {stage==='habit'&&<g transform="translate(54 93)"><rect width="58" height="57" rx="8" fill="#fbf2db" stroke="#bfa880" stroke-width="2"/><path d="M0 15h58" stroke="#c58c70" stroke-width="8"/><path d="M13-5v11m32-11v11" stroke="#91785c" stroke-width="4" stroke-linecap="round"/>{[16,29,42].map(x=><g key={x}><circle cx={x} cy="30" r="3" fill="#92a38c"/><circle cx={x} cy="43" r="3" fill="#92a38c"/></g>)}</g>}
    {routes[stage].map(({path,x,y,angle},index)=><g key={index} fill="none" stroke="#a77a3f" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"><path d={path} stroke-dasharray="6 10"/><path d="m-13-9 13 9-13 9" transform={`translate(${x} ${y}) rotate(${angle})`}/></g>)}
    {stage==='detour'&&(visual.obstacle==='puddle'?<g transform="translate(221 330)"><path d="M-48-7q6-18 36-10Q5-27 24-13Q58-13 49 3Q32 19 9 9Q-25 22-44 10Q-62 2-48-7Z" fill="#a2bfc1"/><path d="M-34-1q19-8 35-3m7 10q17 5 28-3" stroke="#deebe3" stroke-width="3" fill="none" stroke-linecap="round"/></g>:<g transform="translate(225 319)"><path d="m-31-15-6 35m61-35 7 35" stroke="#aa8b66" stroke-width="6"/><rect x="-39" y="-17" width="78" height="18" rx="3" fill="#f5e7c7" stroke="#ba9970" stroke-width="2"/><path d="m-29-16 17 16m9-16L14 0m9-16L38-1" stroke="#bb8268" stroke-width="9"/></g>)}
    {mode==='transport'?<MotionTransport kind={visual.transport??'bus'} {...vehiclePose} facing={leaving?-1:1}/>:<>
      <MotionPerson {...personPose} facing={leaving?-1:1} carrying={mode==='carrying'} standing={['enter','exit','arrival','approach','cross'].includes(stage)}/>
      {mode==='leading'&&<g transform={`translate(${personPose.x} ${personPose.y}) scale(${personPose.scale})`}><MotionPerson x={leaving?53:-53} y={18} facing={leaving?-1:1} scale={.74} coat="#c78f72"/><path d={leaving?'M26 14q17 6 22 7':'M-24 16q-10 7-19 6'} stroke="#e6b590" stroke-width="6" stroke-linecap="round" fill="none"/></g>}
    </>}
    {stage==='arrival'&&<g fill="none" stroke="#8e9e77" stroke-width="4" stroke-linecap="round"><path d="m364 259-10-6m16-3-2-11m12 12 7-9"/></g>}
  </svg>;
}

function SceneIllustration({scene, description, motion}: {scene:string;description:string;motion?:MotionVisual}) {
  const image=(name:string,className:string)=> <img src={`/static/images/scene-builder/${name}-v1.webp`} class={className} alt="" aria-hidden="true" draggable={false}/>;
  const location=scene.startsWith('cat-');
  const book=scene.startsWith('book-');
  const roles=scene==='girl-calls-boy'||scene==='boy-calls-girl';
  if(scene==='motion-route'&&motion)return <div class="scene-illustration scene-motion-route" role="img" aria-label={description}><MotionIllustration visual={motion}/></div>;
  return <div class={`scene-illustration scene-${scene}`} role="img" aria-label={description}>
    <div class="scene-room-wall"/><div class="scene-room-floor"/>
    {location && <>{image('table','scene-table')}{image('cat','scene-cat')}</>}
    {book && <>{image('table','scene-table')}{image(scene==='book-upright'?'book-upright':'book','scene-book')}</>}
    {['walking','taxi','walking-away','taxi-moving','taxi-away','doorway-inside','courtyard-in','courtyard-out'].includes(scene)&&image(scene,'scene-travel')}
    {roles&&<svg viewBox="0 0 500 350" class="scene-people" aria-hidden="true">
      <g transform="translate(125 65)"><path d="M-37 82Q-52-10 0-10Q55-10 35 82" fill="#775044"/><circle cy="36" r="32" fill="#e6b590"/><path d="M-42 100Q0 61 42 100L57 190H-57Z" fill="#c88265"/><path d="M-22 191v54m44-54v54" stroke="#354d55" stroke-width="18" stroke-linecap="round"/><circle cx="-11" cy="33" r="3" fill="#35434a"/><circle cx="11" cy="33" r="3" fill="#35434a"/><path d="M-8 48q8 8 16 0" fill="none" stroke="#a55e4c" stroke-width="3"/></g>
      <g transform="translate(375 65)"><circle cy="36" r="32" fill="#e6b590"/><path d="M-33 26q-3-45 34-39q43 0 31 48L13 6-11 20z" fill="#694c40"/><path d="M-44 105Q0 66 44 105l10 79H-54Z" fill="#73989a"/><path d="M-22 188v56m44-56v56" stroke="#354d55" stroke-width="18" stroke-linecap="round"/><circle cx="-11" cy="33" r="3" fill="#35434a"/><circle cx="11" cy="33" r="3" fill="#35434a"/><path d="M-8 48q8 8 16 0" fill="none" stroke="#a55e4c" stroke-width="3"/></g>
      <g transform={scene==='boy-calls-girl'?'translate(500 0) scale(-1 1)':undefined}><path d="M177 112q65-49 126 0" fill="none" stroke="#a77840" stroke-width="5" stroke-dasharray="8 9"/><path d="m292 94 17 22-27 1" fill="none" stroke="#a77840" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/><path d="m170 95 7-12m-22 9 1-13" stroke="#a77840" stroke-width="4" stroke-linecap="round"/></g>
      <text x="125" y="342" text-anchor="middle" fill="#3f5055" font-size="18">Анна</text><text x="375" y="342" text-anchor="middle" fill="#3f5055" font-size="18">Иван</text>
    </svg>}
  </div>;
}

export function SceneBuilder({round, selected, onChange, disabled, expected, slotResults}: {
  round:GameRound;selected:string[];onChange:(values:string[])=>void;disabled:boolean;expected?:string[];slotResults?:SceneSlotResult[];
}) {
  const ru=useGameLanguage()==='ru';
  const scene=round.scene_builder;
  if(!scene)return null;
  const checked=!!expected;
  const scenario=ru?scene.scenario_ru:scene.scenario;
  const chosenText=(index:number,values:string[])=>{
    const text=scene.slots[index].choices.find(choice=>choice.id===values[index])?.text??'';
    return index===0 && !scene.segments[0] ? text.charAt(0).toUpperCase()+text.slice(1) : text;
  };
  const completeSentence=expected?scene.segments.map((segment,index)=>segment+(index<scene.slots.length?chosenText(index,expected):'')).join(''):'';
  function choose(index:number,id:string) {
    const next=scene!.slots.map((_,i)=>selected[i]??'');
    next[index]=id;
    onChange(next);
  }
  return <div class="scene-builder">
    <figure class="scene-figure"><SceneIllustration scene={scene.scene} description={scenario} motion={scene.motion_visual}/><figcaption>{scenario}</figcaption></figure>
    <div class="scene-construction">
      <div class="scene-sentence" lang="ru" aria-label={ru?'Ваше предложение':'Your sentence'}>{scene.segments.map((segment,index)=><span key={index}>{segment}{index<scene.slots.length&&<span class={`scene-blank${selected[index]?' is-filled':''}${checked?(selected[index]===expected[index]?' is-correct':' is-incorrect'):''}`} aria-label={!selected[index]?(ru?`Пропуск ${index+1}`:`Blank ${index+1}`):undefined}>{chosenText(index,selected)||'…'}</span>}</span>)}</div>
      <div class="scene-choice-banks">{scene.slots.map((slot,index)=>{
        const result=slotResults?.find(item=>item.id===slot.id);
        return <fieldset key={slot.id} class="scene-choice-bank" disabled={disabled}><legend><span class="scene-slot-number" aria-hidden="true">{index+1}</span>{ru?slot.label_ru:slot.label}</legend><div class="scene-choice-buttons">{slot.choices.map(choice=><button key={choice.id} type="button" lang="ru" aria-pressed={selected[index]===choice.id} class={`${selected[index]===choice.id?'is-selected ':''}${checked&&expected[index]===choice.id?'is-answer':''}`} onClick={()=>choose(index,choice.id)}>{choice.text}{checked&&expected[index]===choice.id&&<span aria-hidden="true"> ✓</span>}</button>)}</div>{result&&<p class={`scene-slot-feedback${result.correct?' is-correct':''}`}><span aria-hidden="true">{result.correct?'✓':'↪'} </span>{ru?result.explanation_ru:result.explanation}</p>}</fieldset>;
      })}</div>
      {checked&&<div class="scene-correct-sentence"><p>{ru?'Полное предложение':'The complete sentence'}</p><strong lang="ru">{completeSentence}</strong></div>}
    </div>
  </div>;
}
