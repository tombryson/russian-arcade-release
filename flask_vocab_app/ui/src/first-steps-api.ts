import {api} from './learning-api';
import type {ProgressionData} from './Progression';

export type FirstStepsSummary={id:string;position:number;title:string;description:string;status:'locked'|'available'|'active'|'completed';href:string};
export type FirstStepsChapter={version?:string;chapter_id?:string;profile_id:string|null;lessons:FirstStepsSummary[];next_lesson:FirstStepsSummary|null;completed_count:number;complete:boolean;pending_reward?:number;previous_chapter?:{title:string;href:string;completed_count:number};updated_chapter_href?:string};
export type FirstStepsTeaching={id:string;title:string;word:string;word_display?:string;meaning:string;explanation:string;example?:string;translation?:string;examples?:{ru:string;en:string}[];visual?:string;audio_url?:string;audio_text?:string;reading_help?:string;name_slot?:boolean};
export type FirstStepsQuestion={id:string;prompt:string;passage?:string;choices:{id:string;text:string;audio_url?:string}[];choices_language?:'ru'|'en';hint?:string;visual?:string;audio_url?:string;transcript?:string;review_available?:boolean};
export type FirstStepsAnswer={question_id:string;answer:string;answer_text:string;correct:boolean;correct_answer:string;feedback:string;hint_used:boolean;acknowledged:boolean;choices_language?:'ru'|'en'};
export type FirstStepsAttempt={id:string;version:string;phase:'learn'|'question'|'feedback'|'ready'|'completed';teaching_index:number;total_teaching:number;question_index:number;total_questions:number;teaching:FirstStepsTeaching|null;question:FirstStepsQuestion|null;answers:FirstStepsAnswer[];completed_at:number|null};
export type FirstStepsLesson={version?:string;chapter_id?:string;profile_id:string|null;lesson:{id:string;position:number;title:string;description:string;href:string;total_lessons:number};attempt:FirstStepsAttempt|null;teaching_cards:FirstStepsTeaching[];resolution?:string|null;reward:null|{amount:number;status:'credited'|'pending';awarded_now:boolean};pending_reward:number;next_lesson:FirstStepsSummary|null;chapter_complete:boolean;progression?:ProgressionData;previous_lesson?:{title:string;href:string};updated_lesson_href?:string};
export type FirstStepsAction='start'|'learn'|'hint'|'review'|'answer'|'continue'|'complete';
export const firstStepsEndpoint=(path='',version?:string)=>`/api/v1/first-steps${path}${version?`?version=${encodeURIComponent(version)}`:''}`;
export const firstStepsHref=(version?:string)=>`#first-steps${version?`?version=${encodeURIComponent(version)}`:''}`;
export const getFirstSteps=(signal?:AbortSignal,version?:string)=>api<FirstStepsChapter>(firstStepsEndpoint('',version),undefined,signal);
export const getFirstStepsLesson=(lessonId:string,signal?:AbortSignal,version?:string)=>api<FirstStepsLesson>(firstStepsEndpoint(`/${encodeURIComponent(lessonId)}`,version),undefined,signal);
export const saveFirstSteps=(lessonId:string,action:FirstStepsAction,body:unknown={},version?:string)=>api<FirstStepsLesson>(firstStepsEndpoint(`/${encodeURIComponent(lessonId)}/${action}`,version),body);
