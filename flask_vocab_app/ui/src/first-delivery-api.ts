import {api} from './learning-api';
import type {ProgressionData} from './Progression';

export type FirstDeliveryAnswer={question_id:string;answer:string;answer_text:string;correct:boolean;correct_answer:string;feedback:string;hint_used:boolean;acknowledged:boolean};
export type FirstDeliveryAttempt={
  id:string;version:string;phase:'learn'|'question'|'feedback'|'ready'|'completed';question_index:number;total_questions:number;
  question:null|{id:string;title?:string;passage?:string;prompt:string;lesson?:{word:string;meaning:string;explanation:string};choices:{id:string;text:string}[];hint?:string};
  answers:FirstDeliveryAnswer[];completed_at:number|null;
};
export type FirstDeliveryState={profile_id:string|null;attempt:FirstDeliveryAttempt|null;teaching_cards?:{id:string;title:string;word:string;meaning:string;explanation:string}[];progression?:ProgressionData;pending_reward:number;previous_attempt?:{version:string;answers:FirstDeliveryAnswer[]}|null;reward:null|{amount:number;status:'credited'|'pending';awarded_now:boolean}};
export type FirstDeliveryAction='start'|'learn'|'hint'|'answer'|'continue'|'complete';
export const firstDeliveryState=(signal?:AbortSignal)=>api<FirstDeliveryState>('/api/v1/onboarding/practice',undefined,signal);
export const saveFirstDelivery=(action:FirstDeliveryAction,body:unknown={})=>api<FirstDeliveryState>(`/api/v1/onboarding/practice/${action}`,body);
