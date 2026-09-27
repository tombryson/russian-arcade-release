export type Language = 'en' | 'ru';
export type Rating = 'again' | 'hard' | 'good' | 'easy';
export const ratings: Rating[] = ['again', 'hard', 'good', 'easy'];
export function ratingLabel(rating: string, language: Language) {
  const labels: Record<Rating, [string, string]> = { again: ['Again', 'Снова'], hard: ['Hard', 'Трудно'], good: ['Good', 'Хорошо'], easy: ['Easy', 'Легко'] };
  return labels[rating as Rating]?.[language === 'ru' ? 1 : 0] ?? rating;
}
export type LessonSource = { lesson_id: string; title: string; url: string; page?: number; origin?: "source" | "example" };
export type CardScope = { q?: string; deck?: string; direction?: string; state?: string; topic?: string; pos?: string; case?: string; difficulty?: string; sort?: string; word_id?: string; lesson_id?: string };
export type CardMetadata = { pos: string; grammar: Record<string,string>; topics: string[]; lemma_difficulty?: number; form_difficulty?: number };
export type CardAsset = { id: string; role: string; media_type: string; kind?: 'image' | 'word_audio' | 'sentence_audio' };
export type MediaJob = { kind: string; status: string; error?: string };
export type LibraryCard = { sources?: LessonSource[]; media_ready?: boolean; id: string; version_id: string; lemma: string | null; title: string; title_ru?: string; direction: string;
  metadata?: CardMetadata; context_meaning?: string; cue_en?: string; dictionary_url?: string; assets?: CardAsset[]; media_jobs?: MediaJob[]; media_supported?: boolean; prompt: string; answer: string; context: string; explanation?: string; explanation_ru?: string;
  decks: { content_id: string; title: string; title_ru?: string }[]; topic?: string; status: string; due: boolean; buried: boolean; due_at: number | null; revision: number };
export type CardOverview = { lesson?: LessonSource | null; profile_id: string; profile_name: string; cards: LibraryCard[]; active_session_id: string | null; server_now: number; new_limit: number;
  facets?: { decks: LibraryCard['decks']; topics: string[]; pos?: string[]; cases?: string[] };
  counts: { media_pending?: number; cards: number; words: number; due: number; new: number; new_allowance: number; ready: number; learning: number; reviewing: number; suspended: number; buried: number; practised_today: number; answers_today: number; next_due_at: number | null } };
export type ReviewItem = { sources?: LessonSource[]; id: string; card_id: string; type: string; direction: string; title?: string; title_ru?: string; prompt: string;
  context?: string; context_meaning?: string; cue_en?: string; dictionary_url?: string; has_hint: boolean; hint?: string; assisted: boolean; answer?: string; explanation?: string; explanation_ru?: string;
  metadata?: CardMetadata; assets: CardAsset[] };
export type ReviewSession = { lesson?: LessonSource | null; id: string; profile_id: string; revision: number; status: string; phase: 'front' | 'revealed' | 'feedback' | 'completed';
  total_cards: number; practised_cards: number; skipped_cards: number; item: ReviewItem | null;
  feedback: { rating: string; assisted: boolean; answer: string; due_at: number; prompt: string } | null; can_undo: boolean; notice?: string; server_now: number };
export type CardHistory = { profile_id: string; card_id: string; events: { rating: string; at: number; due_at: number; assisted: boolean; undone: boolean }[] };
export const words = (language: Language) => (en: string, ru: string) => language === 'ru' ? ru : en;
export function isReviewSession(value: unknown): value is ReviewSession {
  return !!value && typeof value === 'object' && 'phase' in value && 'profile_id' in value && 'revision' in value;
}
export function nextTime(due: number, now: number, language: Language) {
  const t = words(language), minutes = Math.ceil(Math.max(0, due - now) / 60);
  if (!minutes) return t('Ready now', 'Уже пора повторить');
  if (minutes < 60) return new Intl.RelativeTimeFormat(language, { numeric: 'always' }).format(minutes, 'minute');
  if (minutes < 1440) return new Intl.RelativeTimeFormat(language, { numeric: 'always' }).format(Math.ceil(minutes / 60), 'hour');
  return new Intl.DateTimeFormat(language, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(due * 1000);
}
