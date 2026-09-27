import { useGameText } from "./GameLocale";
import type { GameOptions, GameSources } from './journey-games-api';
export function GameWordSource({
  sources,
  options,
  onChange,
  disabled,
  broadcast = false
}: {
  sources?: GameSources;
  options: GameOptions;
  onChange: (options: GameOptions) => void;
  disabled: boolean;
  broadcast?: boolean;
}) {
  const t = useGameText();
  const lesson = sources?.lessons.find(item => item.id === options.lesson_id);
  function chooseSource(value: string) {
    const {
      lesson_id: _,
      topic: __,
      difficulty: ___,
      ...rest
    } = options;
    onChange(value === 'vocabulary' ? {
      ...rest,
      source: 'vocabulary'
    } : {
      ...rest,
      source: 'lesson',
      lesson_id: value.slice(7)
    });
  }
  return <div class="game-word-source"><p class="game-source-summary">{options.source === 'lesson' ? lesson?.title ?? t("Selected lesson") : t("Build on familiar words")}{!broadcast && sources && <span> · {options.source === 'lesson' ? lesson?.count ?? 0 : sources.word_count}{" "}{t("words")}</span>}</p><p class="quiet">{broadcast ? t("A short programme with familiar language and a few new words.") : t("Practise familiar words and discover a few new ones along the way.")}</p><details><summary>{broadcast ? t("Customise the programme") : t("Choose words")}</summary><fieldset disabled={disabled}><legend class="sr-only">{t("Words for this game")}</legend><div class="game-source-controls">{!broadcast && <label>{t("Word source")}<select value={options.source === 'lesson' ? `lesson:${options.lesson_id}` : 'vocabulary'} onChange={event => chooseSource(event.currentTarget.value)}><option value="vocabulary">{t("Build on my vocabulary")}</option>{sources?.lessons.map(item => <option key={item.id} value={`lesson:${item.id}`}>{item.title}</option>)}</select></label>}{options.source === 'vocabulary' && <><label>{t("Topic")}<select value={options.topic ?? ''} onChange={event => {
                const {
                  topic: _,
                  ...rest
                } = options;
                onChange(event.currentTarget.value ? {
                  ...rest,
                  topic: event.currentTarget.value
                } : rest);
              }}><option value="">{t("Any topic")}</option>{sources?.topics.map(topic => <option key={topic} value={topic}>{topic.replaceAll('_', ' ')}</option>)}</select></label><label>{t("Vocabulary difficulty")}<select value={options.difficulty ?? ''} onChange={event => {
                const {
                  difficulty: _,
                  ...rest
                } = options;
                onChange(event.currentTarget.value ? {
                  ...rest,
                  difficulty: Number(event.currentTarget.value)
                } : rest);
              }}><option value="">{t("Any difficulty")}</option>{[1, 2, 3, 4, 5, 6, 7, 8].map(level => <option key={level} value={level}>{level}{level === 1 ? t(" · easiest") : ''}</option>)}</select></label></>}{!broadcast && <label>{t("Game length")}<select value={options.rounds} onChange={event => onChange({
              ...options,
              rounds: Number(event.currentTarget.value) as 5 | 10
            })}><option value="5">{t("5 rounds")}</option><option value="10">{t("10 rounds")}</option></select></label>}</div></fieldset><p class="quiet">{t("Vocabulary bands describe the words, not a TORFL level.")}</p></details></div>;
}
