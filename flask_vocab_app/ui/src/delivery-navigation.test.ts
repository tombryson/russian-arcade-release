import {expect,it} from 'vitest';
import {corridorChoices} from './delivery-navigation';
import type {DeliveryMapData} from './delivery-types';

const map=():DeliveryMapData=>({scene:'town',nodes:[
  {id:'start',x:0,y:0,label:'Почта',label_en:'Post office',kind:'post'},
  {id:'a',x:1,y:0,label:'Улица',label_en:'Street',kind:'street'},
  {id:'bend',x:2,y:0,label:'Улица',label_en:'Street',kind:'street'},
  {id:'b',x:2,y:1,label:'Улица',label_en:'Street',kind:'street'},
  {id:'library',x:2,y:2,label:'Библиотека',label_en:'Library',kind:'library'},
  {id:'after',x:2,y:3,label:'Улица',label_en:'Street',kind:'street'},
],edges:[['start','a'],['a','bend'],['bend','b'],['b','library'],['library','after']]});

it('stops at a bend instead of choosing a turn, then stops at a named landmark',()=>{
  expect(corridorChoices(map(),'start')).toEqual([{node_id:'bend',path:['start','a','bend']}]);
  expect(corridorChoices(map(),'bend')).toContainEqual({node_id:'library',path:['bend','b','library']});
});

it('preserves adjacent-only navigation for saved legacy maps',()=>{
  const legacy=map();delete legacy.scene;
  expect(corridorChoices(legacy,'start')).toEqual([{node_id:'a',path:['start','a']}]);
});

it('stops before choosing a branch at a junction',()=>{
  const town=map();town.nodes.push({id:'branch',x:1,y:1,label:'Улица',label_en:'Street',kind:'street'});town.edges.push(['a','branch']);
  expect(corridorChoices(town,'start')).toEqual([{node_id:'a',path:['start','a']}]);
});
