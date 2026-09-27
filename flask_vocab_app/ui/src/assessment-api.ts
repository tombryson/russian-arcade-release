import { api, upload } from './learning-api';

export type AssessmentDomain = 'language_use' | 'reading' | 'listening' | 'writing' | 'speaking';
export type PilotResponse = { answers: Record<string, string> } | { text: string } | { unavailable: true };
export type PilotAttempt = {
  id?: string; submission_id?: string; review_status: string; outcome?: string; feedback?: string;
  criteria?: { label?: string; label_ru?: string; feedback: string; outcome?: string }[];
  response?: PilotResponse; recording_url?: string; support?: string[];
  production_feedback?: {
    strength?: string; next_step?: string; example?: string; transcript?: string; speech_status?: string;
    grammar?: { score: number | null; reason: string; evidence?: string[] };
    fluency?: { score: number | null; reason: string; evidence?: string[] };
    corrections?: { original: string; replacement: string; explanation: string; category?: string }[];
    uncertainty?: string | string[];
  };
};
export type PilotComponent = {
  id: string; domain: AssessmentDomain; title: string; title_ru?: string; prompt: string; prompt_ru?: string;
  format: string; revision: number; state: string;
  questions?: { id: string; prompt: string; choices: { id: string; text: string }[] }[];
  passage?: string; audio_url?: string; audio_available?: boolean; listened?: boolean; transcript_visible?: boolean;
  draft?: PilotResponse | null; support: string[]; hint?: string; attempt?: PilotAttempt | null;
  history: PilotAttempt[]; max_duration_seconds?: number;
};
export type PilotSession = {
  id: string; profile_id: string; blueprint_id: string; status: string; diagnostic: true;
  limitations: string[]; components: PilotComponent[]; created_at: number;
};
export type PilotOverview = {
  profile_id: string; enabled: boolean; recordings_ready?: boolean; configured: { writing: boolean; speaking: boolean };
  blueprint: { id: string; title: string; title_ru?: string; level: string; limitations: string[]; domains: { id: AssessmentDomain; title: string; title_ru?: string }[] };
  active_session: PilotSession | null;
  sessions: { id: string; status: string; created_at: number }[];
};
export const pilotPath = '/api/v1/assessment-pilot';
export type PilotCommand = { url: string; body: object | FormData; action: string };
export function sendPilot(command: PilotCommand, signal: AbortSignal) {
  return command.body instanceof FormData
    ? upload<PilotSession>(command.url, command.body, signal)
    : api<PilotSession>(command.url, command.body, signal);
}
