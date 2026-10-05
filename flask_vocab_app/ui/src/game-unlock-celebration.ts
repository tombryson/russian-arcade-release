import '../../static/js/game_unlock_celebration.js';
import '../../static/css/game_unlock_celebration.css';
import {appBasePath,appUrl} from './app-url';

export type GameShopMilestones={enabled:boolean;policy:string;offers:{id:string;price:number}[]};
type CoinSnapshot={profile_id:string;balance:number;game_shop?:GameShopMilestones};
declare global {
  interface Window {
    arcadeGameUnlocks?: {
      update:(data:CoinSnapshot,options:{scope:string;language:string;shopHref:string})=>void;
      reset:()=>void;
    };
  }
}

export function updateGameUnlocks(data:CoinSnapshot) {
  const account=document.querySelector<HTMLElement>('#word-post')?.dataset.sessionScope
    || document.querySelector<HTMLMetaElement>('meta[name="learning-account"]')?.content || 'local';
  window.arcadeGameUnlocks?.update(data,{
    scope:`${account}:${appBasePath() || '/'}`,
    language:document.documentElement.lang,
    shopHref:appUrl('/#shop'),
  });
}

export function resetGameUnlocks() {window.arcadeGameUnlocks?.reset();}
