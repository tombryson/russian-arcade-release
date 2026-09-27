import { useRef, useState } from 'preact/hooks';
import { words, type CardMetadata, type CardAsset, type Language } from './review-types';

const labels: Record<string,[string,string]> = {
  NOUN:['Noun','Существительное'], VERB:['Verb','Глагол'], ADJ:['Adjective','Прилагательное'], ADJF:['Adjective','Прилагательное'], ADJS:['Short adjective','Краткое прилагательное'],
  INFN:['Infinitive','Инфинитив'], ADVB:['Adverb','Наречие'], NPRO:['Pronoun','Местоимение'], PREP:['Preposition','Предлог'], NUMR:['Number','Числительное'], CONJ:['Conjunction','Союз'], PRCL:['Particle','Частица'], INTJ:['Interjection','Междометие'], unknown:['Unclassified','Без категории'],
  PART:['Participle','Причастие'], COMP:['Comparative','Сравнительная степень'], PRED:['Predicative','Предикатив'],
  nomn:['Nominative','Именительный'], gent:['Genitive','Родительный'], datv:['Dative','Дательный'], accs:['Accusative','Винительный'], ablt:['Instrumental','Творительный'], loct:['Prepositional','Предложный'],
  sing:['Singular','Единственное число'], plur:['Plural','Множественное число'], masc:['Masculine','Мужской род'], femn:['Feminine','Женский род'], neut:['Neuter','Средний род'],
  anim:['Animate','Одушевлённое'], inan:['Inanimate','Неодушевлённое'], past:['Past tense','Прошедшее время'], pres:['Present tense','Настоящее время'], futr:['Future tense','Будущее время'],
  perf:['Perfective','Совершенный вид'], impf:['Imperfective','Несовершенный вид'], indc:['Indicative','Изъявительное наклонение'], impr:['Imperative','Повелительное наклонение'],
  '1per':['First person','Первое лицо'], '2per':['Second person','Второе лицо'], '3per':['Third person','Третье лицо'], actv:['Active voice','Действительный залог'], pssv:['Passive voice','Страдательный залог'],
};
export function cardLabel(value: string, language: Language) {
  return labels[value]?.[language==='ru' ? 1 : 0] ?? value.replaceAll('_',' ').replace(/^./,c => c.toUpperCase());
}
export function CardTags({ metadata, language }: { metadata?: CardMetadata; language: Language }) {
  if (!metadata) return null;
  const t=words(language), difficulty=metadata.form_difficulty ?? metadata.lemma_difficulty;
  const values=[metadata.pos,...Object.values(metadata.grammar ?? {}),...metadata.topics].filter(Boolean);
  return <ul class="card-tags" aria-label={t('Card details','Сведения о карточке')}>{[...new Set(values)].map(value => <li key={value}>{cardLabel(value,language)}</li>)}{difficulty && <li>{t('Difficulty','Сложность')} {difficulty}/8</li>}</ul>;
}
export function CardMedia({ asset, language }: { asset: CardAsset; language: Language }) {
  const [failed,setFailed]=useState(false), [speed,setSpeed]=useState(1), audio=useRef<HTMLAudioElement>(null), t=words(language);
  if (failed) return <p class="quiet">{t('This recording or picture could not load. Reload to try again.', 'Файл не загрузился. Обновите страницу, чтобы попробовать снова.')}</p>;
  if (!asset.media_type.startsWith('audio/')) return <img class="card-illustration" src={`/api/v1/assets/${asset.id}`} alt={t('Illustration of the example sentence', 'Иллюстрация к предложению')} onError={() => setFailed(true)} />;
  const label=asset.kind==='word_audio' ? t('Word','Слово') : asset.kind==='sentence_audio' ? t('Example','Пример') : t('Pronunciation','Произношение');
  return <div class="card-recording"><div class="card-recording-heading"><span>{label}</span><label>{t('Speed','Скорость')}<select aria-label={`${label}: ${t('playback speed','скорость воспроизведения')}`} value={speed} onChange={e => { const value=Number(e.currentTarget.value);setSpeed(value);if (audio.current) audio.current.playbackRate=value; }}><option value="0.75">0.75×</option><option value="1">1×</option><option value="1.25">1.25×</option></select></label></div><audio ref={audio} onLoadedMetadata={() => { if (audio.current) audio.current.playbackRate=speed; }} controls preload="metadata" aria-label={`${label}: ${t('Russian audio','аудио по-русски')}`} src={`/api/v1/assets/${asset.id}`} onError={() => setFailed(true)} /></div>;
}
