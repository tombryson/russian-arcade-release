import {api} from './learning-api';
import type {DeliveryState} from './delivery-types';

export type JourneyGameId='pack-bag'|'directions'|'pairs'|'mailbox-sort'|'missing-stamp'|'radio'|'detective'|'letter-back'|'scene-builder';
export type GameUnlock={required_coins:number;earned_coins:number;remaining_coins:number};
export type GamePurchase={price:number;owned:boolean;can_purchase:boolean};
export type GameShopState={balance:number|null;first_purchase:boolean;price:number;enabled:boolean};
export type GamePurchaseReceipt={game_id:JourneyGameId;charged:number;balance:number;owned:true;already_owned:boolean};
export type GameSummary={id:JourneyGameId;title:string;description:string;lesson_id:string;lesson_title:string;lesson_href:string;unlocked:boolean;unlock?:GameUnlock;purchase?:GamePurchase;new:boolean;availability?:'sample'|'local-only';active_session_id:string|null};
export type GameSources={word_count:number;form_count:number;topics:string[];lessons:{id:string;title:string;count:number}[]};
export type MotionLevel='A1'|'A2'|'B1';
export type GameOptions={source:'vocabulary'|'lesson';lesson_id?:string;topic?:string;difficulty?:number;rounds:5|10;delivery_id?:string;delivery_mode?:'reading'|'listening';delivery_new_town?:boolean;grammar_focus?:'location'|'motion'|'placement'|'agreement'|'roles'|'mixed';motion_level?:MotionLevel};
export type DeliveryChoice={mission_id:string;title:string;title_ru:string;area:string;summary:string;summary_ru:string;area_label?:string;area_label_ru?:string};
export type GameCatalogueState={profile_id:string|null;public_demo?:boolean;shop?:GameShopState;games:GameSummary[];deliveries?:DeliveryChoice[];sources?:GameSources};
export type Heading='north'|'east'|'south'|'west';
export type MapPosition={x:number;y:number;heading:Heading};
export type GameBoard={width:number;height:number;start:MapPosition;landmarks:{x:number;y:number;visual:string;image_url?:string;label?:string}[]};
export type GameObject={id:string;visual:string;label:string;image_url?:string};
export type GameClue={text?:string;audio_key:string};
export type GameTextOption={id:string;text:string;audio_key?:string};
export type SceneSlotResult={id:string;correct:boolean;expected:string;text:string;explanation:string;explanation_ru:string};
export type MotionVisual={mode:'foot'|'transport'|'carrying'|'leading';stage:'journey'|'habit'|'arrival'|'departure'|'enter'|'exit'|'cross'|'approach'|'past'|'detour'|'return';setting:'street'|'station'|'airport'|'park'|'courtyard'|'bridge'|'shop'|'home';transport?:'bus'|'train'|'car'|'taxi';obstacle?:'puddle'|'roadworks';destination:string};
export type SceneBuilderRound={family:string;scenario:string;scenario_ru:string;scene:string;level?:MotionLevel;skill?:string;motion_visual?:MotionVisual;segments:string[];slots:{id:string;label:string;label_ru:string;choices:{id:string;text:string}[]}[]};
export type GameRound={scene_builder?:SceneBuilderRound;id:string;mechanic?:string;objective?:'grammar'|'vocabulary';prompt:string;clues:GameClue[];hint?:string;hint_ru?:string;objects?:GameObject[];board?:GameBoard;max_choices:number;left?:GameTextOption[];right?:GameObject[];sentences?:GameTextOption[];bins?:{id:string;label:string;description?:string}[];sentence?:string;translation?:string;visual?:string;image_url?:string;audio_required?:boolean;choices?:{id:string;text?:string;visual?:string;label?:string;image_url?:string}[];destinations?:{id:string;visual:string;route:string[];label:string;image_url?:string}[];tiles?:GameTextOption[];support?:{listened_audio_keys:string[];transcript:boolean}};
export type GameBroadcast={title:string;audio_key:string;duration_seconds?:number;script?:string;listened:boolean;transcript:boolean};
export type GameWord={card_key?:string;lemma:string;form:string;sentence?:string;translation?:string;target_meaning?:string;in_vocabulary?:boolean};
export type GameWordLookup={word:string;lemma:string|null;pos?:string|null;grammar?:Record<string,string>;word_id?:number|null;in_vocabulary:boolean;can_add:boolean;context?:string;translation?:string;meaning?:string;message?:string;dictionary_url?:string|null;choices:{lemma:string;pos?:string;label:string;word_id?:number|null;in_vocabulary:boolean;can_add:boolean;dictionary_url?:string}[];added?:boolean};
export type GameState={delivery?:DeliveryState;profile_id:string|null;id:string;game_id:JourneyGameId;title:string;phase:'preparing'|'listening'|'play'|'feedback'|'ready'|'completed'|'practice'|'practice_feedback';sample?:boolean;practice?:{mode:'correction'|'review';index:number;total:number};broadcast?:GameBroadcast;words?:GameWord[];summary?:{correct_rounds:number;total_rounds:number;missed_rounds?:number;matched:number;total:number};preparation?:{status:'pending'|'running'|'ready'|'failed';ready:number;total:number;stage:string;message:string;error?:string};round_index:number;total_rounds:number;round:GameRound|null;result:null|{answer:string[];correct:boolean;expected_answer:string[];feedback:string;explanation?:string;explanation_ru?:string;path?:MapPosition[];score?:number;matched?:number;total?:number;answer_audio?:GameClue[];slot_results?:SceneSlotResult[];correct_sentence?:string;translation?:string;translation_ru?:string};reward:null|{amount:number;status:'credited'|'pending';awarded_now:boolean;reason?:'awarded'|'already_rewarded'|'daily_cap'|'profile_needed'};source:{lesson_id?:string;kind?:'vocabulary'|'lesson'|'first_steps'|'route'|'sample'|'grammar';title:string;href:string};study_available?:boolean};
export type GameAction='hint'|'answer'|'continue'|'complete'|'listen'|'transcript'|'quiz'|'retry'|'review'|'practice_answer'|'practice_continue'|'practice_exit'|'practice_hint'|'practice_transcript';
export type GameAudio={status:'ready'|'pending'|'failed'|'unavailable';url?:string;message?:string};
export async function getGames(signal?:AbortSignal):Promise<GameCatalogueState> {
  const value=await api<GameCatalogueState>('/api/v1/games',undefined,signal);
  if(!value||!Array.isArray(value.games)||!value.games.every(game=>game&&typeof game.id==='string'&&typeof game.title==='string'&&typeof game.unlocked==='boolean'&&typeof game.lesson_href==='string'))throw new Error('Your games could not load. Please try again.');
  if(value.games.some(game=>game.unlock && (![game.unlock.required_coins,game.unlock.earned_coins,game.unlock.remaining_coins].every(value=>Number.isInteger(value)&&value>=0))))throw new Error('Your games could not load. Please try again.');
  if(value.shop && (!(value.shop.balance===null || Number.isInteger(value.shop.balance)) || !Number.isInteger(value.shop.price) || value.shop.price<0 || typeof value.shop.first_purchase!=='boolean' || typeof value.shop.enabled!=='boolean'))throw new Error('Your shop could not load. Please try again.');
  if(value.games.some(game=>game.purchase && (!Number.isInteger(game.purchase.price)||game.purchase.price<0||typeof game.purchase.owned!=='boolean'||typeof game.purchase.can_purchase!=='boolean')))throw new Error('Your shop could not load. Please try again.');
  if(value.sources){const sources=value.sources;if(!Number.isFinite(sources.word_count)||!Number.isFinite(sources.form_count)||!Array.isArray(sources.topics)||!sources.topics.every(topic=>typeof topic==='string')||!Array.isArray(sources.lessons)||!sources.lessons.every(lesson=>lesson&&typeof lesson.id==='string'&&typeof lesson.title==='string'&&Number.isFinite(lesson.count)))throw new Error('Your word sources could not load. Please try again.');}
  return value;
}
export const startGame=(gameId:string,requestId:string,options:GameOptions|Pick<GameOptions,'grammar_focus'|'rounds'|'motion_level'>={source:'vocabulary',rounds:5},newGame=false)=>api<GameState>(`/api/v1/games/${encodeURIComponent(gameId)}/start`,{request_id:requestId,options,...(newGame?{new_game:true}:{})});
export const prepareGame=(id:string,retry=false,signal?:AbortSignal)=>api<GameState>(`/api/v1/games/sessions/${encodeURIComponent(id)}/prepare`,retry?{retry:true}:{},signal);
export const getGame=(id:string,signal?:AbortSignal)=>api<GameState>(`/api/v1/games/sessions/${encodeURIComponent(id)}`,undefined,signal);
export const saveGame=(id:string,action:GameAction,body:unknown={})=>api<GameState>(`/api/v1/games/sessions/${encodeURIComponent(id)}/${action}`,body);
export const prepareGameAudio=(key:string)=>api<GameAudio>(`/api/v1/games/media/${encodeURIComponent(key)}/prepare`,{});
export const getGameAudio=(key:string,signal?:AbortSignal)=>api<GameAudio>(`/api/v1/games/media/${encodeURIComponent(key)}/status`,undefined,signal);
export const getGameWord=(id:string,word:string,signal?:AbortSignal)=>api<GameWordLookup>(`/api/v1/games/sessions/${encodeURIComponent(id)}/words?word=${encodeURIComponent(word)}`,undefined,signal);
export const addGameWord=(id:string,word:string,lemma:string,pos?:string)=>api<GameWordLookup>(`/api/v1/games/sessions/${encodeURIComponent(id)}/words`,{word,lemma,...(pos?{pos}:{})});

export const purchaseGame=(gameId:JourneyGameId,requestId:string,expectedPrice:number)=>api<GamePurchaseReceipt>(`/api/v1/games/${encodeURIComponent(gameId)}/purchase`,{request_id:requestId,expected_price:expectedPrice});
