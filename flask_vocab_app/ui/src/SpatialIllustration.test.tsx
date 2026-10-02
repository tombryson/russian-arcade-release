import {describe,expect,it} from 'vitest';
import {render,screen} from '@testing-library/preact';
import {SpatialIllustration} from './SpatialIllustration';
import {SceneBuilder} from './SceneBuilder';
import {GameLanguage} from './GameLocale';
import type {GameRound,SpatialVisual} from './journey-games-api';

const base:SpatialVisual={kind:'spatial',subject:'book',anchor:'table',relation:'on',orientation:'flat',setting:'home'};

describe('composed spatial scene',()=>{
  it.each(['on','under','behind','in-front','beside','in'] as const)('shows %s with distinct position and depth',relation=>{
    const {container}=render(<SpatialIllustration visual={{...base,anchor:relation==='in'?'box':'table',relation}}/>);
    const svg=container.querySelector('svg')!;
    const subject=container.querySelector('.scene-spatial-subject')!;
    const anchor=container.querySelector('.scene-spatial-anchor')!;
    expect(svg.getAttribute('data-relation')).toBe(relation);
    const y=Number(subject.getAttribute('transform')!.match(/translate\(\d+ (\d+)\)/)![1]);
    if(relation==='on')expect(y).toBeLessThan(210);
    if(relation==='under')expect(y).toBeGreaterThan(300);
    if(relation==='in-front')expect(y).toBeGreaterThan(360);
    if(relation==='beside')expect(subject.getAttribute('transform')).toContain('translate(107');
    // A behind object must be painted before the anchor; a foreground one after.
    const subjectBefore=!!(subject.compareDocumentPosition(anchor)&Node.DOCUMENT_POSITION_FOLLOWING);
    expect(subjectBefore).toBe(relation==='behind');
    if(relation==='in')expect(subject.compareDocumentPosition(container.querySelector('.scene-spatial-front')!)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
  it.each(['cat','book','ball','cup','bag','letter'] as const)('renders the actual %s once and colours the object',subject=>{
    const {container}=render(<SpatialIllustration visual={{...base,subject,anchor:'box',relation:'in-front',color:'red'}}/>);
    const objects=container.querySelectorAll('.scene-spatial-subject');
    expect(objects).toHaveLength(1);
    expect(objects[0].getAttribute('data-subject')).toBe(subject);
    if(subject!=='cat')expect(objects[0].querySelector('[fill="#bb6656"]')).toBeTruthy();
  });
  it('distinguishes a flat book from an upright one',()=>{
    const {container,rerender}=render(<SpatialIllustration visual={base}/>);
    expect(container.querySelector('.scene-spatial-subject [transform*="scale(1 .27)"]')).toBeTruthy();
    rerender(<SpatialIllustration visual={{...base,orientation:'upright'}}/>);
    expect(container.querySelector('.scene-spatial-subject [transform*="scale(1 .27)"]')).toBeNull();
  });
  it.each(['en','ru'] as const)('uses the saved %s caption without showing an answer in the picture',language=>{
    const round:GameRound={id:'generated',prompt:'Complete the sentence.',clues:[],max_choices:1,
      scene_builder:{family:'placement',scene:'spatial-composed',scene_visual:base,scenario:'The book is lying on the table.',scenario_ru:'Книга лежит на столе.',segments:['Книга ','.'],slots:[{id:'verb',label:'Verb',label_ru:'Глагол',choices:[{id:'flat',text:'лежит'},{id:'upright',text:'стоит'}]}]}};
    const {container}=render(<GameLanguage value={language}><SceneBuilder round={round} selected={[]} onChange={()=>{}} disabled={false}/></GameLanguage>);
    expect(screen.getByRole('img',{name:language==='ru'?'Книга лежит на столе.':'The book is lying on the table.'})).toBeTruthy();
    expect(container.querySelector('.scene-spatial-art text')).toBeNull();
    expect(container.querySelector('.scene-spatial-art')).toBeTruthy();
  });
});
