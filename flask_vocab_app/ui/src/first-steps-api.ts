import {api} from './learning-api';
import type {ProgressionData} from './Progression';

export type FirstStepsSummary={id:string;position:number;title:string;description:string;status:'locked'|'available'|'active'|'completed';href:string};
export type FirstStepsChapter={profile_id:string|null;lessons:FirstStepsSummary[];next_lesson:FirstStepsSummary|null;completed_count:number;complete:boolean;pending_reward?:number};
export type FirstStepsTeaching={id:string;title:string;word:string;meaning:string;explanation:string;example?:string;translation?:string;visual?:string};
export type FirstStepsQuestion={id:string;prompt:string;passage?:string;choices:{id:string;text:string}[];hint?:string;visual?:string};
export type FirstStepsAnswer={question_id:string;answer:string;answer_text:string;correct:boolean;correct_answer:string;feedback:string;hint_used:boolean;acknowledged:boolean};
export type FirstStepsAttempt={id:string;version:string;phase:'learn'|'question'|'feedback'|'ready'|'completed';teaching_index:number;total_teaching:number;question_index:number;total_questions:number;teaching:FirstStepsTeaching|null;question:FirstStepsQuestion|null;answers:FirstStepsAnswer[];completed_at:number|null};
export type FirstStepsLesson={profile_id:string|null;lesson:{id:string;position:number;title:string;description:string;href:string;total_lessons:number};attempt:FirstStepsAttempt|null;teaching_cards:FirstStepsTeaching[];resolution?:string|null;reward:null|{amount:number;status:'credited'|'pending';awarded_now:boolean};pending_reward:number;next_lesson:FirstStepsSummary|null;chapter_complete:boolean;progression?:ProgressionData};
export type FirstStepsAction='start'|'learn'|'hint'|'answer'|'continue'|'complete';
export const getFirstSteps=(signal?:AbortSignal)=>api<FirstStepsChapter>('/api/v1/first-steps',undefined,signal);
export const getFirstStepsLesson=(lessonId:string,signal?:AbortSignal)=>api<FirstStepsLesson>(`/api/v1/first-steps/${encodeURIComponent(lessonId)}`,undefined,signal);
export const saveFirstSteps=(lessonId:string,action:FirstStepsAction,body:unknown={})=>api<FirstStepsLesson>(`/api/v1/first-steps/${encodeURIComponent(lessonId)}/${action}`,body);
