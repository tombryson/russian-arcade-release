import {useEffect,useRef,useState} from 'preact/hooks';
import {api,ApiError} from './learning-api';
import {getGame,type GameState} from './journey-games-api';
import {useGameLanguage} from './GameLocale';
import {DeliveryMap,Person,point} from './DeliveryMap';
import {corridorChoices,headingBetween} from './delivery-navigation';
import type {DeliveryLine,DeliveryState} from './delivery-types';
import {GameWords} from './GameWords';
import {GameStudyActions} from './GameStudyActions';
import './styles/delivery-game.css';

const headings=['north','east','south','west'];
const headingLabels={north:['north','север'],east:['east','восток'],south:['south','юг'],west:['west','запад']};

function guideDestination(delivery:DeliveryState,id:string) {
  const node=delivery.map.nodes.find(item=>item.id===id)!;
  const names:Record<string,string>={post:'почты',bakery:'пекарни',market:'рынка',library:'библиотеки',pharmacy:'аптеки',cafe:'кафе',park:'парка',station:'вокзала',house:'дома','bank-office':'банка',courtyard:'входа во двор',bridge:'моста',fountain:'фонтана',square:'площади'};
  const bridgeNames:Record<string,string>={'Северный мост':'северного моста','Южный мост':'южного моста'};
  if(node.kind==='meeting'&&node.label.startsWith('У '))return node.label.slice(2);
  if(node.kind==='bridge'&&bridgeNames[node.label])return bridgeNames[node.label];
  if(node.kind==='bus-stop')return `остановки «${node.label}»`;
  if(names[node.kind])return names[node.kind];
  const neighbours=delivery.map.edges.filter(edge=>edge.includes(id)).map(edge=>delivery.map.nodes.find(item=>item.id===edge.find(value=>value!==id))!);
  const segments=delivery.map.street_segments?.filter(edge=>edge.from===id||edge.to===id);
  if(segments?.some(edge=>edge.kind==='path')&&neighbours.length>2){
    const roads=segments.filter(edge=>edge.kind!=='path');
    if(roads.length<3)return roads.length===2?'пешеходной дорожки':'развилки';
  }
  if(neighbours.length>2||node.kind==='junction')return 'перекрёстка';
  if(neighbours.length<2)return 'конца улицы';
  const [first,second]=neighbours.map(other=>headings.indexOf(headingBetween(node,other)));
  return (first+2)%4===second?'отмеченной точки':'поворота';
}
const guidePhrase=(turn:number,destination:string)=>turn===0?`Идите прямо до ${destination}.`:`Поверните ${turn<0?'налево':'направо'} и идите до ${destination}.`;

// Only graph geometry is used here. The client does not receive a correct route.
export function guideChoices(delivery:DeliveryState) {
  const nodes=Object.fromEntries(delivery.map.nodes.map(node=>[node.id,node]));
  const path=delivery.draft,tail=nodes[path.at(-1)??delivery.position],previous=nodes[path.at(-2)??''];
  let facing=delivery.heading;
  if(previous&&tail)facing=headingBetween(previous,tail);
  const adjacent=corridorChoices(delivery.map,tail.id);
  return {heading:facing,choices:[{turn:-1,text:'Налево',symbol:'↰'},{turn:0,text:'Прямо',symbol:'↑'},{turn:1,text:'Направо',symbol:'↱'}].map(choice=>{
    const direction=headings[(Math.max(0,headings.indexOf(facing))+choice.turn+4)%4];
    const next=adjacent.find(option=>headingBetween(tail,nodes[option.path[1]])===direction);
    return {...choice,node:next?.node_id,path:next?.path,phrase:next?guidePhrase(choice.turn,guideDestination(delivery,next.node_id)):undefined};
  })};
}

export function guideInstructions(delivery:DeliveryState) {
  const entries:{phrase:string;from:number;to:number}[]=[];
  let from=Math.max(0,(delivery.walked?.length??1)-1);
  while(from<delivery.draft.length-1){
    const prefix=delivery.draft.slice(0,from+1),next=delivery.draft[from+1];
    const choice=guideChoices({...delivery,draft:prefix}).choices.find(item=>item.path?.[1]===next);
    if(!choice?.path)break;
    let steps=1;
    while(steps<choice.path.length-1&&delivery.draft[from+steps+1]===choice.path[steps+1])steps++;
    const to=from+steps;
    entries.push({phrase:guidePhrase(choice.turn,guideDestination(delivery,delivery.draft[to])),from,to});
    from=to;
  }
  return entries;
}

// Dialogue clips share playback, so a second speaker never talks over the first.
let activeRecording: HTMLAudioElement | undefined;
function Recording({line,ru,onHeard,label}:{line:DeliveryLine;ru:boolean;onHeard?:()=>void;label?:string}) {
  const ended=useRef(onHeard);ended.current=onHeard;
  const player=useRef<HTMLAudioElement>();
  const [playing,setPlaying]=useState(false),[slow,setSlow]=useState(false),[failed,setFailed]=useState(false);
  useEffect(()=>()=>{player.current?.pause();if(activeRecording===player.current)activeRecording=undefined;},[]);
  async function play(){
    if(!player.current){player.current=new Audio(line.audio_url);player.current.onended=()=>{setPlaying(false);ended.current?.();};player.current.onpause=()=>setPlaying(false);}
    const audio=player.current;
    if(playing){audio.pause();setPlaying(false);return;}
    if(activeRecording!==audio)activeRecording?.pause();
    activeRecording=audio;audio.currentTime=0;audio.playbackRate=slow?.8:1;setFailed(false);
    try{await audio.play();setPlaying(true);}catch{setFailed(true);setPlaying(false);}
  }
  return <>
    <div class="delivery-recording">
      <button type="button" onClick={()=>void play()} aria-label={`${ru?(playing?'Пауза':'Послушать'):(playing?'Pause':'Listen')}: ${line.text??label??(ru?'Указания':'Directions')}`}><span aria-hidden="true">{playing?'Ⅱ':'▶'}</span> {ru?(playing?'Пауза':'Послушать'):(playing?'Pause':'Listen')}</button>
      <button type="button" aria-pressed={slow} onClick={()=>{setSlow(!slow);if(player.current)player.current.playbackRate=slow?1:.8;}}>{ru?'Медленнее':'Slower'}</button>
    </div>
    {failed&&<p class="delivery-recording-error" role="status">{ru?'Запись не загрузилась. Можно читать и продолжать.':'Recording unavailable. You can read and continue.'}</p>}
  </>;
}

export function DeliveryGame({state,onState}:{state:GameState;onState:(next:GameState)=>void}) {
  const d=state.delivery!,ru=useGameLanguage()==='ru';
  const text=(en:string,rus:string)=>ru?rus:en;
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[blocked,setBlocked]=useState(false),[uncertain,setUncertain]=useState(false);
  const [moving,setMoving]=useState<string[]>([]),[showNotebook,setShowNotebook]=useState(false);
  const [zoomed,setZoomed]=useState(false);
  const [selectedStop,setSelectedStop]=useState('');
  const [receipts,setReceipts]=useState<{line_id:string;leg:number;reviewing:boolean}[]>([]);
  const mapViewport=useRef<HTMLDivElement>(null);
  const pending=useRef(false),mounted=useRef(true),last=useRef<unknown>();
  const focus=useRef<HTMLHeadingElement>(null);
  const world=useRef<HTMLDivElement>(null),panel=useRef<HTMLElement>(null),previousPhase=useRef(d.phase);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  useEffect(()=>{focus.current?.focus({preventScroll:true});},[d.leg,d.phase]);
  useEffect(()=>{
    if(previousPhase.current!==d.phase&&window.matchMedia?.('(max-width: 760px)').matches){
      (d.phase==='planning'?world.current:panel.current)?.scrollIntoView({block:'start'});
    }
    previousPhase.current=d.phase;
  },[d.phase]);
  useEffect(()=>{if(moving.length<1)return;const timer=setTimeout(()=>setMoving(p=>p.slice(1)),220);return()=>clearTimeout(timer);},[moving]);
  const locked=busy||blocked||uncertain||moving.length>0||receipts.length>0;
  const nodes=Object.fromEntries(d.map.nodes.map(n=>[n.id,n]));
  const town=d.map.scene==='town',transit=!!d.transport_leg,guide=d.interaction==='guide';
  const routeChoices=guideChoices(d),transport=d.transport;
  const currentStop=transport?.stop_id??transport?.board;
  const currentStopIndex=transport?.stops.findIndex(stop=>stop.id===currentStop)??-1;
  const nextStops=transport?.stops.filter((stop,index)=>index>currentStopIndex&&stop.id!==currentStop&&!transport.visited?.includes(stop.id))??[];
  useEffect(()=>setSelectedStop(''),[d.leg,transport?.status,transport?.stop_id]);
  useEffect(()=>{
    const el=mapViewport.current;if(!el||!zoomed||town)return;
    const p=point(nodes[d.position]),scale=el.scrollWidth/870;
    el.scrollTo({left:p.x*scale-el.clientWidth/2,top:p.y*scale-el.clientHeight/2});
  },[zoomed]);
  const tail=d.draft.at(-1)!,corridors=corridorChoices(d.map,tail),adjacent=corridors.map(item=>item.node_id);
  const instructions=guide?guideInstructions(d):[];
  const walked=d.walked?.length?d.walked:[d.draft[0]];
  const hasPlannedMovement=d.draft.length>walked.length;
  const nextRoute=(id:string)=>[...d.draft,...(corridors.find(item=>item.node_id===id)?.path.slice(1)??(d.map.edges.some(edge=>edge.includes(tail)&&edge.includes(id))?[id]:[]))];
  const undoRoute=()=>d.draft.slice(0,Math.max(walked.length,guide&&instructions.length?instructions.at(-1)!.from+1:d.draft.length-1));
  const canGo=!d.question_required&&d.can_go!==false&&hasPlannedMovement&&(town||(tail!==d.draft[0]&&!['street','junction'].includes(nodes[tail].kind)));
  async function send(action:string,payload:Record<string,unknown>={},replay=false){
    if(pending.current||blocked)return;
    pending.current=true;setBusy(true);setError('');
    const request=replay?last.current:{request_id:crypto.randomUUID(),revision:d.revision,action,payload};last.current=request;
    try{
      const next=await api<GameState>(`/api/v1/games/sessions/${state.id}/route-command`,request);
      if(!mounted.current)return;
      if(next.profile_id!==state.profile_id)throw new ApiError(text('Your profile changed. Reopen this delivery.','Профиль изменился. Открой доставку снова.'),'profile_changed');
      setUncertain(false);
      if(['go','ride'].includes(action)&&next.delivery?.last_path.length&&!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)setMoving(next.delivery.last_path);
      onState(next);
    }catch(cause){
      if(!mounted.current)return;
      if(cause instanceof ApiError&&['state_conflict','delivery_finished'].includes(cause.code)){
        try{const next=await getGame(state.id);if(next.profile_id!==state.profile_id)throw new Error();onState(next);setUncertain(false);setError(text('The latest saved position is now open.','Открыта последняя сохранённая позиция.'));}
        catch{setBlocked(true);setError(text('Reopen this delivery to continue.','Открой доставку снова.'));}
      }else{
        setError(cause instanceof Error?cause.message:text('The delivery could not save.','Не удалось сохранить доставку.'));
        setBlocked(cause instanceof ApiError&&['profile_changed','forbidden','not_found','profile_required'].includes(cause.code));
        setUncertain(!(cause instanceof ApiError));
      }
    }finally{pending.current=false;if(mounted.current)setBusy(false);}
  }
  function heard(line:DeliveryLine) {
    if(d.phase==='completed'||d.heard?.includes(line.id))return;
    setReceipts(queue=>queue.some(item=>item.line_id===line.id)?queue:[...queue,{line_id:line.id,leg:d.leg,reviewing:!!d.reviewing}]);
  }
  // An audio clip can finish while a route point is saving. Drain receipts only
  // after that response supplies the next revision, rather than dropping them.
  useEffect(()=>{
    if(busy||blocked||uncertain||!receipts.length)return;
    const [receipt,...rest]=receipts;
    setReceipts(rest);
    if(receipt.leg===d.leg&&receipt.reviewing===!!d.reviewing&&d.phase!=='completed'&&!d.heard?.includes(receipt.line_id))
      void send('listen',{line_id:receipt.line_id,leg:receipt.leg});
  },[busy,blocked,uncertain,receipts,d.revision]);
  const stages=d.stages??[{name:'Sasha',name_ru:'Саша',title:'Finding Sasha',title_ru:'Поиск Саши'},{name:'Olya',name_ru:'Оля',title:'Before the bridge',title_ru:'Перед мостом'},{name:'The letter',name_ru:'Письмо',title:'Finding the address',title_ru:'Поиск адреса'}];
  const finalLeg=d.leg===stages.length-1;
  const person=d.phase==='arrived'||d.phase==='completed'?d.arrival_speaker:d.speaker;
  const completed=d.phase==='completed',planning=d.phase==='planning';
  const retry=()=>void send('retry');
  const help=(kind:string)=>void send('help',{kind});
  const lines=d.phase==='completed'&&d.ending?[d.ending]:d.lines;
  const heading=completed?(town?text('Task complete.','Задание выполнено.'):text('Letter delivered.','Письмо доставлено.')):
    d.phase==='arrived'?(town?text('You’ve arrived.','Ты на месте.'):text(`You found ${person.name_en}.`,`${person.name} здесь.`)):
    d.phase==='feedback'?(d.feedback?.navigation?text('Keep going.','Продолжай путь.'):text('Let’s check the directions.','Проверим указания.')):
    ru?d.objective_ru:d.objective;
  return <section class={`page delivery-game is-${d.phase}`} aria-busy={busy}>
    <header class="delivery-top"><div><a class="text-link" href="#activities">← {text('All activities','Все занятия')}</a><p class="kicker">{text('Follow the directions','Следуй указаниям')}</p><h1>{ru?d.title_ru:state.title}</h1></div>
      <ol class="delivery-stages" aria-label={text('Delivery progress','Этапы доставки')}>{stages.map((stage,i)=><li key={i} class={i<d.leg||completed?'is-done':i===d.leg?'is-active':''} aria-current={!completed&&i===d.leg?'step':undefined}><span>{i<d.leg||completed?'✓':i+1}</span>{ru?stage.name_ru:stage.name}</li>)}</ol>
    </header>
    {d.reviewing&&<div class="delivery-review-notice"><p><strong>{text('Practise this section','Повтори этот участок')}</strong> · {text(stages[d.leg].title,stages[d.leg].title_ru)}<span>{text('Your original result and coins stay the same.','Первый результат и монеты не изменятся.')}</span></p><button class="text-link" disabled={locked} onClick={()=>void send('review_exit')}>{text('Back to delivery results','К результатам доставки')}</button></div>}
    <div class={`delivery-layout${town?' is-town':''}`}>
      <div class="delivery-world" ref={world}>
        {planning&&<div class="delivery-mobile-instruction">{(d.text_visible===false?d.lines:d.lines.slice(-1)).map((line,i)=><div class="delivery-mobile-message" key={line.id}><p lang={line.text?"ru":undefined}>{line.text??text(`Message ${i+1}`,`Сообщение ${i+1}`)}</p><Recording line={line} ru={ru} label={text(`Message ${i+1}`,`Сообщение ${i+1}`)} onHeard={()=>heard(line)}/>{d.heard?.includes(line.id)&&<small class="delivery-listened">✓ {text('Played','Прослушано')}</small>}</div>)}{d.text_visible===false&&<button class="text-link" disabled={locked} onClick={()=>help('transcript')}>{text('Read the directions','Прочитать указания')}</button>}<button class="text-link" onClick={()=>panel.current?.scrollIntoView({block:'start'})}>{text('Conversation and help','Разговор и подсказки')} ↓</button></div>}
        <div class="delivery-map-frame">
          {!town&&<div class="delivery-map-tools"><span>{text('Neighbourhood map','Карта района')}</span><button class="text-link" aria-pressed={zoomed} onClick={()=>setZoomed(!zoomed)}>{zoomed?text('Fit map','Вся карта'):text('Enlarge map','Увеличить карту')} {zoomed?'−':'+'}</button></div>}
          <div ref={mapViewport} class={`delivery-map-viewport${zoomed&&!town?' is-zoomed':''}`}><DeliveryMap state={d} path={d.draft} position={moving[0]??d.position} disabled={locked||!planning||transit||guide||!!d.question_required} onNode={id=>void send('plan',{path:nextRoute(id)})} ru={ru}/></div>
        <div class="delivery-location"><span aria-hidden="true">●</span> {guide?text(`${d.speaker.name_en} is at`,`${d.speaker.name}:`):text('Barsik is at','Барсик:')} <strong lang="ru">{nodes[moving[0]??d.position].label}</strong></div>
      </div>
      {d.phase==='dialogue'&&<div class="delivery-route-start"><button class="cta delivery-begin" disabled={locked||!!d.question_required} onClick={()=>void send('begin')}>{guide?text('Give directions','Объяснить дорогу'):transit?text('Plan the journey','Спланировать поездку'):text('Plan the route','Построить маршрут')} <span aria-hidden="true">→</span></button>{d.question_required&&<p>{text('Ask a question before setting off.','Задай вопрос перед отправлением.')}</p>}</div>}
      {planning&&!transit&&!guide&&<div class="delivery-mobile-neighbours"><p>{text('Add the next stop to your route:','Добавь следующую точку маршрута:')}</p><div>{adjacent.map(id=><button key={id} disabled={locked||!!d.question_required} onClick={()=>void send('plan',{path:nextRoute(id)})}><span aria-hidden="true">{nodes[id].x>nodes[tail].x?'→':nodes[id].x<nodes[tail].x?'←':nodes[id].y>nodes[tail].y?'↓':'↑'}</span> <span lang="ru">{nodes[id].label}</span></button>)}</div></div>}
      {planning&&guide&&<section class="delivery-guide-controls" aria-label={text('Give directions','Объяснить дорогу')}><strong>{text('Give directions','Объяснить дорогу')}</strong><p>{text(`${d.draft.length>1?'Facing':d.speaker.name_en+' starts facing'} ${headingLabels[routeChoices.heading as keyof typeof headingLabels]?.[0]??routeChoices.heading}${d.draft.length>1?' at the end of your route':''}. Choose the next junction or landmark.`,`${d.draft.length>1?'В конце маршрута ты смотришь':d.speaker.name+' начинает путь, глядя'} на ${headingLabels[routeChoices.heading as keyof typeof headingLabels]?.[1]??routeChoices.heading}. Выбери следующий перекрёсток или ориентир.`)}</p><div>{routeChoices.choices.map(choice=><button key={choice.turn} type="button" aria-label={choice.node?`${choice.text}. До ${guideDestination(d,choice.node)}`:choice.text} disabled={locked||!!d.question_required||!choice.node} onClick={()=>void send('plan',{path:nextRoute(choice.node!)})}><span aria-hidden="true">{choice.symbol}</span> <span><span lang="ru">{choice.text}</span>{choice.node&&<small lang="ru">{`До ${guideDestination(d,choice.node)}`}</small>}</span></button>)}</div>{instructions.length>0&&<ol class="delivery-spoken-route" aria-label={text('Your Russian directions','Твои указания по-русски')}>{instructions.map((item,index)=><li key={index} lang="ru">{item.phrase}</li>)}</ol>}</section>}
      {planning&&!transit&&<div class="delivery-plan"><div><strong>{guide?text('Your directions','Твои указания'):text('Your route','Твой маршрут')}</strong><p>{d.can_go===false?text('Listen to the messages or read the directions before setting off.','Послушай или прочитай указания перед отправлением.'):guide?text('Choose the next part of the route, then let them follow your directions.','Выбери следующий участок маршрута и проверь свои указания.'):text('Choose connected points, then a place to stop.','Выбирай связанные точки, затем место остановки.')}</p></div><div class="delivery-plan-actions"><button class="text-link" disabled={locked||!hasPlannedMovement} onClick={()=>void send('plan',{path:undoRoute()})}>{text('Undo','Отменить')}</button><button class="text-link" disabled={locked||!hasPlannedMovement} onClick={()=>void send('plan',{path:walked})}>{text('Clear route','Сбросить маршрут')}</button><button class="cta" disabled={locked||!canGo} onClick={()=>void send('go',{path:d.draft})}>{guide?text('Try these directions','Проверить указания'):text('Go','В путь')} <span aria-hidden="true">→</span></button></div></div>}
      {planning&&transit&&transport&&<section class="delivery-transit" aria-label={text('Public transport','Общественный транспорт')}>
        <div class="delivery-transit-heading"><strong>{ru?transport.label_ru:transport.label}</strong><span>{transport.status==='waiting'?text('At the stop','На остановке'):text('On board','В транспорте')}</span></div>
        {transport.status==='waiting'?<><p>{text('Board, then choose where to get off using the directions you heard.','Садись и выбери остановку по услышанным указаниям.')}</p>{d.can_go===false&&<p class="quiet">{text('Listen to the messages or read the directions before boarding.','Послушай или прочитай указания перед посадкой.')}</p>}<button class="cta" disabled={locked||d.can_go===false||!!d.question_required} onClick={()=>void send('board',{transport_id:transport.id})}>{ru?'Сесть':`Board ${transport.label}`} </button></>:<>
          <p>{text('Current stop:','Текущая остановка:')} <strong>{ru?transport.stops.find(stop=>stop.id===currentStop)?.label_ru:transport.stops.find(stop=>stop.id===currentStop)?.label}</strong></p>
          {!!nextStops.length&&<fieldset disabled={locked}><legend>{text('Where will you travel to?','До какой остановки поедешь?')}</legend><div class="delivery-stop-choices">{nextStops.map(stop=><label key={stop.id} class={selectedStop===stop.id?'is-selected':''}><input type="radio" name={`stop-${state.id}`} checked={selectedStop===stop.id} onChange={()=>setSelectedStop(stop.id)}/><span lang="ru">{stop.label_ru}</span>{!ru&&<small>{stop.label}</small>}</label>)}</div></fieldset>}
          <div class="delivery-transit-actions">{!!nextStops.length&&<button class="cta" disabled={locked||!nextStops.some(stop=>stop.id===selectedStop)} onClick={()=>void send('ride',{stop_id:selectedStop})}>{text('Travel to this stop','Ехать до этой остановки')} →</button>}<button class="cta" disabled={locked||!transport.stop_id||transport.stop_id===transport.board} onClick={()=>void send('alight')}>{text('Get off here','Выйти здесь')}</button></div>
        </>}
      </section>}
      {moving.length>0&&<div class="delivery-plan" role="status">{text('On the way…','В пути…')}<button class="text-link" onClick={()=>setMoving([])}>{text('Skip animation','Пропустить анимацию')}</button></div>}
      <details class="delivery-text-map"><summary>{text('Map and keyboard controls','Карта и управление с клавиатуры')}</summary><p>{guide?text('North is at the top. Choose a Russian direction to reach the next junction or landmark. Undo removes your last phrase.','Север вверху. Выбери указание по-русски, чтобы дойти до следующего перекрёстка или ориентира. Кнопка «Отменить» убирает последнюю фразу.'):transit?text('Choose stops in the transport controls below the map. You cannot walk during this part of the journey.','Выбирай остановки под картой. На этом участке нужно ехать, а не идти пешком.'):text('North is at the top. Select the next junction or landmark on a connected street. Use Tab and Enter, or select a point on the map.','Север вверху. Выбирай следующий перекрёсток или ориентир на связанной улице. Используй Tab и Enter или выбирай точки на карте.')}</p>
        {planning&&!transit&&!guide&&<><p>{text('Next to your planned position:','Рядом с концом маршрута:')}</p><div class="delivery-neighbours">{adjacent.map(id=><button key={id} disabled={locked||!!d.question_required} onClick={()=>void send('plan',{path:nextRoute(id)})}>{nodes[id].x>nodes[tail].x?text('East','Восток'):nodes[id].x<nodes[tail].x?text('West','Запад'):nodes[id].y>nodes[tail].y?text('South','Юг'):text('North','Север')}: <span lang="ru">{nodes[id].label}</span></button>)}</div></>}
        <ol>{d.draft.map((id,i)=><li key={i} lang="ru">{nodes[id].label}</li>)}</ol><p>{text('Streets and entrances','Улицы и входы')}</p><ul>{d.map.edges.map(([a,b])=><li key={a+b} lang="ru">{nodes[a].label} ↔ {nodes[b].label}</li>)}</ul>
      </details>
      </div>
      <aside class="delivery-panel" ref={panel}>
        {!town&&<div class="delivery-envelope" aria-label={text('Letter addressed to','Письмо кому')+' '+d.envelope}><svg viewBox="0 0 55 38" aria-hidden="true"><rect x="2" y="2" width="50" height="33" rx="3" fill="#f5e4b6" stroke="#c9ae74"/><path d="M3 3L27 23 52 3M3 35L20 18M52 35L34 18" stroke="#c9ae74" fill="none"/><circle cx="28" cy="20" r="6" fill="#b95c47"/></svg><span lang="ru">{d.envelope}</span><span class="delivery-envelope-note">{text('Find the address and complete the delivery.','Найди адрес и заверши доставку.')}</span></div>}
        {!!d.inventory?.length&&<div class="delivery-inventory" aria-label={text('In your bag','В сумке')}><strong>{text('In your bag','В сумке')}</strong><ul>{d.inventory.map(item=><li key={item.id}><span aria-hidden="true">▣</span>{ru?item.label_ru:item.label}</li>)}</ul></div>}
        <div class="delivery-speaker"><Person kind={person.portrait}/><div><strong>{ru?person.name:person.name_en}</strong><span>{ru?person.role:person.role_en}</span></div></div>
        <h2 tabIndex={-1} ref={focus}>{heading}</h2>
        {error&&<div class="delivery-error" role="alert">{error}{uncertain&&<button class="text-link" disabled={busy} onClick={()=>void send('retry',{},true)}>{text('Retry saving','Повторить сохранение')}</button>}{blocked&&<a href={'#games/session/'+state.id} onClick={()=>window.location.reload()}>{text('Reopen delivery','Открыть доставку')}</a>}</div>}
        {d.phase==='feedback'&&d.feedback&&<div class={`delivery-feedback${d.feedback.navigation?' is-navigation':''}`} role="status">
          <p>{ru?d.feedback.ru:d.feedback.en}</p>
          {!!d.feedback.checks?.length&&<ul class="delivery-route-checks" aria-label={text('Route progress','Что уже выполнено')}>{d.feedback.checks.map(check=><li key={check.id} class={check.complete?'is-complete':''}><span aria-hidden="true">{check.complete?'✓':'○'}</span><span><span class="sr-only">{check.complete?text('Done: ','Выполнено: '):text('Still to do: ','Ещё нужно: ')}</span>{ru?check.label_ru:check.label}</span></li>)}</ul>}
          {!d.feedback.navigation&&<p class="quiet">{d.reviewing?text('Try again or ask for a hint.','Попробуй снова или попроси подсказку.'):text('Your first attempt is saved. You can try again or follow a guide.','Первая попытка сохранена. Попробуй снова или воспользуйся подсказкой.')}</p>}
          <button class="cta" disabled={locked} onClick={d.feedback.navigation?()=>void send('continue'):retry}>{d.feedback.navigation?text('Continue from here','Продолжить отсюда'):text('Try from the last stop','Снова от последней остановки')} →</button>
        </div>}
        {d.phase==='arrived'&&!moving.length&&<div class="delivery-arrival">{d.reviewing?<><p>{text('You followed the directions to the right place.','Ты выполнил указания и нашёл нужное место.')}</p><button class="cta" disabled={locked} onClick={()=>void send('review_exit')}>{text('Back to delivery results','К результатам доставки')} →</button></>:<><p>{(ru?d.arrival_text_ru:d.arrival_text)??(town?text('You reached the next stop.','Ты добрался до следующей остановки.'):finalLeg?text('You’ve reached the address. Give them the letter.','Ты нашёл адрес. Передай письмо.'):text('Stop for a moment. They can help you with the next part of the delivery.','Остановись на минутку. Здесь тебе подскажут дальнейший путь.'))}</p><button class="cta" disabled={locked} onClick={()=>void send(finalLeg?'deliver':'talk')}>{(ru?d.arrival_action_label_ru:d.arrival_action_label)??(town?finalLeg?text('Finish task','Завершить задание'):text('Continue','Продолжить'):finalLeg?text('Deliver the letter','Передать письмо'):text(`Talk to ${person.name_en}`,`Поговорить: ${person.name}`))} →</button></>}</div>}
        {(!['arrived','completed'].includes(d.phase)||completed)&&<div class="delivery-dialogue">{lines.map(item=><div class="delivery-line" key={item.id}><p lang={item.text?"ru":undefined}>{item.text??text(`Message ${lines.indexOf(item)+1}`,`Сообщение ${lines.indexOf(item)+1}`)}</p>{item.english&&<p class="delivery-translation" lang="en">{item.english}</p>}<Recording line={item} ru={ru} label={text(`Message ${lines.indexOf(item)+1}`,`Сообщение ${lines.indexOf(item)+1}`)} onHeard={()=>heard(item)}/>{!completed&&d.mode==='listening'&&d.heard?.includes(item.id)&&<small class="delivery-listened">✓ {text('Played','Прослушано')}</small>}</div>)}</div>}
        {!['arrived','completed'].includes(d.phase)&&!!d.questions?.length&&<fieldset class="delivery-questions" disabled={locked}><legend>{text('Ask a question','Задай вопрос')}{d.question_required&&<span>{text('Choose a question before setting off.','Выбери вопрос перед отправлением.')}</span>}</legend>{d.questions.map(question=><button key={question.id} type="button" disabled={!!question.reply} class={question.reply?'is-asked':''} onClick={()=>void send('ask',{question_id:question.id})}><span lang="ru">{question.reply&&<span aria-hidden="true">✓ </span>}{question.text}</span>{!ru&&d.support.english&&<small>{question.text_en}</small>}</button>)}</fieldset>}
        {d.text_visible===false&&!['arrived','completed'].includes(d.phase)&&<button class="text-link delivery-read" disabled={locked} onClick={()=>help('transcript')}>{text('Read the directions','Прочитать указания')}</button>}
        {d.clarification&&!['arrived','completed'].includes(d.phase)&&<div class="delivery-clarification" role="status"><p lang={d.clarification.text?"ru":undefined}>{d.clarification.text??text("Here’s another explanation.","Вот ещё одно объяснение.")}</p>{d.clarification.english&&<p class="delivery-translation">{d.clarification.english}</p>}<Recording line={d.clarification} ru={ru} onHeard={()=>heard(d.clarification!)}/></div>}
        {!['arrived','completed'].includes(d.phase)&&<details class="delivery-help"><summary>{text('Ask for help','Попросить помощи')}</summary><div><button disabled={locked} onClick={()=>help('clarify')} lang="ru">{d.clarify_prompt??'Объясни, пожалуйста.'}</button>{!d.support.english&&<button disabled={locked} onClick={()=>help('english')}>{text('Show the English meaning','Показать перевод на английский')}</button>}{!transit&&<button disabled={locked} onClick={()=>help('route')}>{text('Show me the route','Покажи маршрут')}</button>}</div></details>}
        {planning&&d.support.route&&!transit&&<p class="delivery-guided" role="status">{guide?text('The suggested route is on the map. Try these directions to follow it.','Маршрут показан на карте. Нажми «Проверить указания».'):text('The suggested route is on the map. Press Go to follow it.','Маршрут показан на карте. Нажми «В путь».')}</p>}
        {!completed&&d.phase!=='arrived'&&d.glossary.length>0&&<div class="delivery-vocabulary"><span>{text('A word you’re unsure of?','Незнакомое слово?')}</span><div>{d.glossary.map(w=><button key={w.lemma} disabled={locked} onClick={()=>help('word:'+w.lemma)} lang="ru">{w.form}</button>)}</div>{d.word&&<div role="status"><strong lang="ru">{d.word.form}</strong> — {d.word.target_meaning}<p lang="ru">{d.word.sentence}</p><p>{d.word.translation}</p></div>}</div>}
        {completed&&<div class="delivery-completion"><div class="delivery-handover" aria-hidden="true"><img src="/static/images/barsik-running-v1.webp" alt=""/><span>{town?'✓':'✉'}</span><Person kind={person.portrait}/></div><p>{(ru?d.completion_text_ru:d.completion_text)??(town?text('You completed the task using Russian directions.','Ты выполнил задание по указаниям на русском.'):text('You helped Barsik find his way, meet the neighbours and deliver a letter.','Ты помог Барсику найти дорогу, познакомиться с соседями и доставить письмо.'))}</p>{state.reward&&<p class="delivery-coins">◉ +{state.reward.amount??0} <span>{state.reward.status==='pending'?text('Save a profile to keep your coins.','Создай профиль, чтобы сохранить монеты.'):state.reward.amount?text('Lingocoins earned','Лингомонет заработано'):text('Activity complete. Today’s reward limit or replay rule applies.','Задание завершено. Награда уже получена или достигнут дневной лимит.')}</span></p>}
          <ul class="delivery-results">{d.first_checks.map(r=><li key={r.leg}><span>{r.correct&&!r.assisted?'✓':'↺'}</span>{text(stages[r.leg].title,stages[r.leg].title_ru)}<small>{r.correct&&!r.assisted?r.presentation==='listening'?text('Listened · First try','На слух · С первой попытки'):text('Read and followed · First try','С текстом · С первой попытки'):text('Practised with help or correction','С помощью или исправлением')}</small>{d.practice_sections?.find(section=>section.leg===r.leg)?.needs_practice&&<button class="text-link" disabled={locked} onClick={()=>void send('review_start',{leg:r.leg})}>{text('Practise this section','Повторить этот участок')}</button>}</li>)}</ul>
          {!!d.practice_sections?.length&&<details class="delivery-section-practice"><summary>{text('Revisit a section','Повторить участок')}</summary>{d.practice_sections.map(section=><button class="text-link" key={section.leg} disabled={locked} onClick={()=>void send('review_start',{leg:section.leg})}>{text(section.title,section.title_ru)}</button>)}</details>}
          <a class="cta" href="#games/directions">{text('Another delivery','Ещё доставка')} →</a>
          {!!state.words?.length&&<GameWords sessionId={state.id} words={state.words}/>}{state.study_available&&<GameStudyActions sessionId={state.id} words={state.words}/>}
        </div>}
        <button class="text-link delivery-notebook-toggle" aria-expanded={showNotebook} onClick={()=>setShowNotebook(!showNotebook)}>{text('Directions notebook','Записанные указания')} {showNotebook?'−':'+'}</button>
        {showNotebook&&<div class="delivery-notebook">{d.notebook.map((entry,i)=><div key={i}><strong>{ru?entry.speaker.name:entry.speaker.name_en}</strong>{entry.lines.map(line=><p key={line.id} lang="ru">{line.text??text('Text hidden for listening practice.','Текст скрыт для практики на слух.')}</p>)}</div>)}</div>}
      </aside>
    </div>
  </section>;
}
