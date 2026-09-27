export type Household = { mode?: 'personal'; configured: boolean; adult: boolean; profile: { id: string; display_name: string } | null; csrf_token: string };
export type LearningHome = {
  profile: { id: string; display_name: string };
  content: { version_id: string; title: string; kind: 'deck' | 'activity' }[];
  sessions: { id: string; title: string; status: string; content_status: string }[];
};
export type Progress = { profile_id: string; evidence: { word_id: number; lemma: string }[] };
export type AnswerFeedback = { outcome: string; answer: string; assisted: boolean; explanation?: string; response_text?: string; support?: string[]; listened?: boolean; transcript?: string };
export type PracticeSession = {
  id: string; profile_id: string; title: string; revision: number; status: string;
  completed_items: number; total_items: number;
  origin?: {href: string; title: string};
  item: { id: string; type?: 'choice' | 'controlled_text' | 'listening_choice'; prompt: string; choices?: { id: string; text: string }[]; has_hint: boolean; hint?: string; asset_ids?: string[]; audio?: {url: string; sha256: string; duration_ms: number}; listened?: boolean; transcript?: string | null; has_transcript?: boolean } | null;
  attempts: { id: string; prompt?: string; feedback: AnswerFeedback }[];
};
export class ApiError extends Error {
  constructor(message: string, public code: string, public currentSession?: PracticeSession) { super(message); }
}
let csrf = '';
let pageProfile: string | undefined;
let pageScope: string | undefined;
export function bindUserSession(profileId: string | undefined, csrfToken: string, sessionScope?: string) {
  pageProfile = profileId;
  pageScope = sessionScope;
  csrf = csrfToken;
}
function identityHeaders(): Record<string,string> {
  return {...(pageProfile === undefined ? {} : {'X-Profile-ID':pageProfile}),
    ...(pageScope ? {'X-Account-Scope':pageScope} : {})};
}
export function endOnLeave(url: string) {
  void fetch(url,{method:'POST',credentials:'same-origin',keepalive:true,
    headers:{...identityHeaders(),'Content-Type':'application/json','X-CSRF-Token':csrf},body:'{}'}).catch(() => {});
}
export async function upload<T>(url: string, body: FormData, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, {method:'POST', body, signal, credentials:'same-origin', cache:'no-store',
    headers:{...identityHeaders(),Accept:'application/json', 'X-CSRF-Token':csrf}});
  const result = await response.json();
  if (!response.ok) throw new ApiError(result.error?.message ?? 'Your recording could not be sent. Please retry.', result.error?.code ?? 'request_failed');
  return result as T;
}
export async function api<T>(url: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store', signal,
    headers: body === undefined ? { ...identityHeaders(), Accept: 'application/json' } : { ...identityHeaders(), Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const result = await response.json();
  if (!response.ok) throw new ApiError(result.error?.message ?? 'Your practice could not be saved. Please try again.', result.error?.code ?? 'request_failed', result.error?.current_session);
  if (result.csrf_token) csrf = result.csrf_token;
  if (body!==undefined && !/\/(?:heartbeat|connect|draft)$/.test(url)) window.dispatchEvent(new Event('lingo:progression'));
  return result as T;
}
