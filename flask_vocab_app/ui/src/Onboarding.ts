import {useCallback,useEffect,useRef,useState} from 'preact/hooks';
import {api,ApiError} from './learning-api';

export type Introduction = 'coins'|'progress';
export type OnboardingState = {profile_id:string|null;coins_introduced:boolean;progress_introduced:boolean};
export const NEW_ONBOARDING:OnboardingState={profile_id:null,coins_introduced:false,progress_introduced:false};

export function useOnboarding(initial:OnboardingState=NEW_ONBOARDING) {
  const [state,setState]=useState(initial);
  const [error,setError]=useState('');
  const desired=useRef(initial);
  const saved=useRef(initial);
  const busy=useRef(false);
  const mounted=useRef(true);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);

  const persist=useCallback(async()=>{
    if (busy.current) return;
    busy.current=true;
    if (mounted.current) setError('');
    try {
      // Fast Next clicks still save the coin introduction before the progress introduction.
      for (const milestone of ['coins','progress'] as const) {
        const field=milestone==='coins' ? 'coins_introduced' : 'progress_introduced';
        if (!desired.current[field] || saved.current[field]) continue;
        const result=await api<OnboardingState>('/api/v1/onboarding',{milestone});
        if (result.profile_id!==initial.profile_id) throw new ApiError('Your profile changed. Reload before continuing.','profile_changed');
        saved.current=result;
      }
    } catch (cause) {
      if (mounted.current) setError(cause instanceof Error ? cause.message : 'Your introduction could not be saved.');
    } finally {busy.current=false;}
  },[initial.profile_id]);
  const introduce=useCallback((milestone:Introduction)=>{
    // Reveal the real header controls as their explanation appears. Persistence
    // never earns coins, changes a rating or hides an already introduced control.
    desired.current={...desired.current,coins_introduced:true,
      progress_introduced:desired.current.progress_introduced || milestone==='progress'};
    setState(desired.current);
    void persist();
  },[persist]);
  return {state,introduce,error,retry:persist};
}
