import type {DeliveryMapData,DeliveryNode} from './delivery-types';

export type CorridorChoice={node_id:string;path:string[]};

export function headingBetween(from:DeliveryNode,to:DeliveryNode) {
  return to.x>from.x?'east':to.x<from.x?'west':to.y>from.y?'south':'north';
}

// One interaction covers a straight street, but never makes a decision at its
// next junction for the learner. The saved path still includes every node.
export function corridorChoices(map:DeliveryMapData,from:string):CorridorChoice[] {
  const nodes=Object.fromEntries(map.nodes.map(node=>[node.id,node]));
  const adjacent=new Map<string,string[]>();
  for(const [a,b] of map.edges){adjacent.set(a,[...(adjacent.get(a)??[]),b]);adjacent.set(b,[...(adjacent.get(b)??[]),a]);}
  if(!nodes[from])return [];
  return (adjacent.get(from)??[]).map(first=>{
    const path=[from,first];
    const direction=headingBetween(nodes[from],nodes[first]);
    if(map.scene==='town')while(path.length<=map.nodes.length){
      const id=path.at(-1)!,previous=path.at(-2)!,node=nodes[id],neighbours=adjacent.get(id)??[];
      if(node.kind!=='street'||neighbours.length!==2)break;
      const next=neighbours.find(value=>value!==previous);
      if(!next||path.includes(next)||headingBetween(node,nodes[next])!==direction)break;
      path.push(next);
    }
    return {node_id:path.at(-1)!,path};
  });
}
