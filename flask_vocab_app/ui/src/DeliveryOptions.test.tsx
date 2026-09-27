import {expect,it,vi} from 'vitest';
import {fireEvent,render,screen} from '@testing-library/preact';
import {DeliveryOptions,orderedDeliveries} from './DeliveryOptions';
import {GameLanguage} from './GameLocale';
import type {DeliveryChoice} from './journey-games-api';

it('offers the actual delivery and presentation choices without starting a game',()=>{
  const onChange=vi.fn();
  render(<DeliveryOptions choices={[{mission_id:'anna',title:'A letter for Anna',title_ru:'Письмо для Анны',area:'park',summary:'Find the second house.',summary_ru:'Найди второй дом.'},{mission_id:'dima',title:'A letter for Dima',title_ru:'Письмо для Димы',area:'riverside',summary:'Cross the river.',summary_ru:'Перейди реку.'}]} options={{source:'vocabulary',rounds:5}} disabled={false} onChange={onChange}/>);
  expect(screen.getByRole('heading',{name:'Park Quarter'})).toBeTruthy();
  expect(screen.getByRole('heading',{name:'Riverside'})).toBeTruthy();
  expect((screen.getByRole('radio',{name:/A letter for Anna/}) as HTMLInputElement).checked).toBe(true);
  fireEvent.click(screen.getByRole('radio',{name:/A letter for Dima/}));
  expect(onChange).toHaveBeenLastCalledWith({source:'vocabulary',rounds:5,delivery_id:'dima'});
  fireEvent.click(screen.getByRole('radio',{name:/Listen first/}));
  expect(onChange).toHaveBeenLastCalledWith({source:'vocabulary',rounds:5,delivery_mode:'listening'});
});

it('lists town missions first and retains other districts and saved choices',()=>{
  render(<DeliveryOptions choices={[
    {mission_id:'park-letter',title:'Park letter',title_ru:'Письмо в парк',area:'park',summary:'A familiar route.',summary_ru:'Знакомый путь.'},
    {mission_id:'town-parcel',title:'Collect a parcel',title_ru:'Забрать посылку',area:'town',summary:'Collect and deliver a parcel.',summary_ru:'Забери и доставь посылку.'},
    {mission_id:'station-guide',title:'Help a visitor',title_ru:'Помочь гостю',area:'station',area_label:'Station district',area_label_ru:'Вокзальный район',summary:'Explain the way.',summary_ru:'Объясни дорогу.'},
  ]} options={{source:'vocabulary',rounds:5}} disabled={false} onChange={vi.fn()}/>);
  expect(screen.getAllByRole('heading').map(item=>item.textContent)).toEqual(['Around town','Station district','Park Quarter']);
  expect((screen.getByRole('radio',{name:/Collect a parcel/}) as HTMLInputElement).checked).toBe(true);
  expect(screen.getByRole('radio',{name:/Park letter/})).toBeTruthy();
});

const generatedChoices:DeliveryChoice[]=[
  {mission_id:'town-detour',title:'The closed bridge',title_ru:'Закрытый мост',area:'town',summary:'Find another river crossing.',summary_ru:'Найди другую переправу.'},
  {mission_id:'town-courtyard',title:'The courtyard entrance',title_ru:'Вход со двора',area:'town',summary:'Find the right entrance to the building.',summary_ru:'Найди нужный вход в здание.'},
  {mission_id:'town-generated',title:'Internal assignment title',title_ru:'Служебное название задания',area:'town',summary:'Internal assignment description',summary_ru:'Служебное описание задания'},
];

it('prefers the procedural engine over a saved legacy composer choice without a scenario selector',()=>{
  const choices=[...generatedChoices,{...generatedChoices[2],mission_id:'town-procedural'}];
  const onChange=vi.fn();
  render(<DeliveryOptions choices={choices} options={{source:'vocabulary',rounds:5,delivery_id:'town-generated'}} disabled={false} onChange={onChange}/>);
  expect(orderedDeliveries(choices).map(choice=>choice.mission_id)).toEqual(['town-procedural']);
  expect(screen.queryByRole('group',{name:'Choose a delivery'})).toBeNull();
  expect(screen.getAllByRole('radio')).toHaveLength(2);
  fireEvent.click(screen.getByRole('radio',{name:/Listen first/}));
  expect(onChange).toHaveBeenCalledWith({source:'vocabulary',rounds:5,delivery_id:'town-procedural',delivery_mode:'listening'});
});

it('introduces a new delivery without revealing its story or offering a puzzle selector',()=>{
  const onChange=vi.fn();
  render(<DeliveryOptions choices={generatedChoices} options={{source:'vocabulary',rounds:5,delivery_id:'town-detour',delivery_mode:'reading'}} disabled={false} onChange={onChange}/>);
  expect(screen.getByRole('heading',{name:'A delivery for Barsik'})).toBeTruthy();
  expect(screen.getByText('Collect a letter or parcel. Talk to people around town to find out where to take it.')).toBeTruthy();
  for(const choice of generatedChoices){
    expect(screen.queryByText(choice.title)).toBeNull();
    expect(screen.queryByText(choice.summary)).toBeNull();
  }
  expect(screen.queryByRole('group',{name:'Choose a delivery'})).toBeNull();
  expect(screen.getAllByRole('radio')).toHaveLength(2);
  expect((screen.getByRole('radio',{name:/Read and listen/}) as HTMLInputElement).checked).toBe(true);
  expect(orderedDeliveries(generatedChoices).map(choice=>choice.mission_id)).toEqual(['town-generated']);
  fireEvent.click(screen.getByRole('radio',{name:/Listen first/}));
  expect(onChange).toHaveBeenLastCalledWith({source:'vocabulary',rounds:5,delivery_id:'town-generated',delivery_mode:'listening'});
});

it('provides the same spoiler-free setup in Russian and disables controls during preparation',()=>{
  render(<GameLanguage.Provider value="ru"><DeliveryOptions choices={generatedChoices} options={{source:'vocabulary',rounds:5,delivery_mode:'listening'}} disabled onChange={vi.fn()}/></GameLanguage.Provider>);
  expect(screen.getByRole('heading',{name:'Доставка для Барсика'})).toBeTruthy();
  for(const choice of generatedChoices){
    expect(screen.queryByText(choice.title_ru)).toBeNull();
    expect(screen.queryByText(choice.summary_ru)).toBeNull();
  }
  expect(screen.getAllByRole('radio')).toHaveLength(2);
  expect((screen.getByRole('radio',{name:/Сначала слушать/}) as HTMLInputElement).checked).toBe(true);
  expect(screen.getByRole('group',{name:'Как практиковаться'}).hasAttribute('disabled')).toBe(true);
});

it('makes a new town an optional procedural choice without selecting it by default',()=>{
  const onChange=vi.fn();
  render(<DeliveryOptions choices={[{...generatedChoices[2],mission_id:'town-procedural'}]} options={{source:'vocabulary',rounds:5,delivery_mode:'listening'}} disabled={false} onChange={onChange}/>);
  const checkbox=screen.getByRole('checkbox',{name:'Explore a new town'}) as HTMLInputElement;
  expect(checkbox.checked).toBe(false);
  expect(onChange).not.toHaveBeenCalled();
  fireEvent.click(checkbox);
  expect(onChange).toHaveBeenCalledWith({source:'vocabulary',rounds:5,delivery_mode:'listening',delivery_id:'town-procedural',delivery_new_town:true});
});

it('does not offer new town generation for prepared or legacy deliveries',()=>{
  render(<DeliveryOptions choices={generatedChoices} options={{source:'vocabulary',rounds:5}} disabled={false} onChange={vi.fn()}/>);
  expect(screen.queryByRole('checkbox',{name:'Explore a new town'})).toBeNull();
});

it('translates and disables the new-town choice during preparation',()=>{
  render(<GameLanguage.Provider value="ru"><DeliveryOptions choices={[{...generatedChoices[2],mission_id:'town-procedural'}]} options={{source:'vocabulary',rounds:5,delivery_new_town:true}} disabled onChange={vi.fn()}/></GameLanguage.Provider>);
  const checkbox=screen.getByRole('checkbox',{name:'Открыть новый город'}) as HTMLInputElement;
  expect(checkbox.checked).toBe(true);
  expect(checkbox.disabled).toBe(true);
});
