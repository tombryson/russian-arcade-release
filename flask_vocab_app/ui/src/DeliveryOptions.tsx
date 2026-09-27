import type {DeliveryChoice,GameOptions} from './journey-games-api';
import {useGameLanguage} from './GameLocale';

export function generatedDelivery(choices:DeliveryChoice[]) {
  return choices.find(choice=>choice.mission_id==='town-procedural')??choices.find(choice=>choice.mission_id==='town-generated');
}

export function orderedDeliveries(choices:DeliveryChoice[]) {
  const generated=generatedDelivery(choices);
  if(generated)return [generated];
  return [...choices].sort((a,b)=>Number(['park','riverside'].includes(a.area))-Number(['park','riverside'].includes(b.area)));
}

export function DeliveryOptions({choices,options,disabled,onChange}:{choices:DeliveryChoice[];options:GameOptions;disabled:boolean;onChange:(value:GameOptions)=>void}) {
  const ru=useGameLanguage()==='ru';
  const ordered=orderedDeliveries(choices),areas=[...new Set(ordered.map(choice=>choice.area))];
  const generated=generatedDelivery(ordered);
  const changeMode=(delivery_mode:'reading'|'listening')=>onChange({...options,delivery_mode,...(generated?{delivery_id:generated.mission_id}:{})});
  const selected=options.delivery_id??ordered[0]?.mission_id;
  const areaName=(area:string)=>{
    const choice=ordered.find(item=>item.area===area)!;
    if(ru&&choice.area_label_ru)return choice.area_label_ru;
    if(!ru&&choice.area_label)return choice.area_label;
    if(area==='park')return ru?'Парковый квартал':'Park Quarter';
    if(area==='riverside')return ru?'У реки':'Riverside';
    return ru?'По городу':'Around town';
  };
  return <div class={`delivery-options${generated?' is-generated':''}`}>
    {generated?<section aria-labelledby="delivery-introduction"><h2 id="delivery-introduction">{ru?'Доставка для Барсика':'A delivery for Barsik'}</h2><p>{ru?'Забери письмо или посылку. Жители подскажут, куда идти.':'Collect a letter or parcel. Talk to people around town to find out where to take it.'}</p></section>:<fieldset disabled={disabled}><legend>{ru?'Выбери доставку':'Choose a delivery'}</legend>
      {areas.map(area=><div class="delivery-district" key={area}>
        <h2>{areaName(area)}</h2>
        <div>{ordered.filter(choice=>choice.area===area).map(choice=><label key={choice.mission_id} class={`delivery-choice${selected===choice.mission_id?' is-selected':''}`}>
          <input type="radio" name="delivery" value={choice.mission_id} checked={selected===choice.mission_id} onChange={()=>onChange({...options,delivery_id:choice.mission_id})}/>
          <span><strong>{ru?choice.title_ru:choice.title}</strong><small>{ru?choice.summary_ru:choice.summary}</small></span>
        </label>)}</div>
      </div>)}
    </fieldset>}
    <fieldset class="delivery-mode-choice" disabled={disabled}><legend>{ru?'Как практиковаться':'How to practise'}</legend>
      <label><input type="radio" name="delivery-mode" checked={options.delivery_mode!=='listening'} onChange={()=>changeMode('reading')}/><span><strong>{ru?'Читать и слушать':'Read and listen'}</strong><small>{ru?'Текст и озвучка указаний.':'Russian directions with recordings.'}</small></span></label>
      <label><input type="radio" name="delivery-mode" checked={options.delivery_mode==='listening'} onChange={()=>changeMode('listening')}/><span><strong>{ru?'Сначала слушать':'Listen first'}</strong><small>{ru?'Текст скрыт. Его можно открыть в любой момент.':'Listen without the text. Reveal it whenever you need.'}</small></span></label>
    </fieldset>
    {generated?.mission_id==='town-procedural'&&<label class="delivery-new-town"><input type="checkbox" checked={options.delivery_new_town===true} disabled={disabled} onChange={event=>onChange({...options,delivery_id:generated.mission_id,delivery_new_town:event.currentTarget.checked})}/><span>{ru?'Открыть новый город':'Explore a new town'}</span></label>}
  </div>;
}
