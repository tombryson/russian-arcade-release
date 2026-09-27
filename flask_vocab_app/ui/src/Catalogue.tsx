import { useState } from 'preact/hooks';
import { ActivityLink, Feedback, Sheet, Art } from './components';

export function Catalogue() {
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  return <div data-theme={theme} class="catalogue"><div class="catalogue-toolbar"><a href="/">Open Russian Arcade</a>
    {(['light', 'dark'] as const).map(value => <button key={value} aria-pressed={theme === value} onClick={() => setTheme(value)}>{value} theme</button>)}<span>Component samples</span></div>
    <main class="page"><p class="kicker">Russian Arcade</p><h1>Design components</h1><p>Sample states for the shared learning interface. These examples do not save answers.</p>
      <section class="catalogue-sample"><h2>Activity entry</h2><ActivityLink title="Comprehension" description="Read or listen, then answer questions about the story." detail="Reading & listening" mark="Аа" href="/comprehension" /></section>
      <section class="catalogue-sample"><h2>Russian text and feedback</h2><Sheet><h3 class="practice-prompt" lang="ru">Я беру я́блоко.</h3><p>Choose the Russian word for apple.</p><div class="options"><button class="word" lang="ru">яблоко</button><button class="word" lang="ru">путешествие</button></div><Feedback>Яблоко means apple.</Feedback></Sheet></section>
      <section class="catalogue-sample"><h2>Save and recovery</h2><Feedback>Saving your answer…</Feedback><Sheet><h3>Save not confirmed</h3><p>Your answer is still here. Try saving again.</p><button class="cta" disabled>Try saving again (sample)</button></Sheet></section>
      <section class="catalogue-sample"><h2>Empty state</h2><Sheet><h3>No learning material yet.</h3><p>A grown-up can review an activity for you to practise.</p></Sheet></section>
      <section class="catalogue-sample"><h2>Barsik</h2><figure class="art"><Art /><figcaption>Barsik · Барсик</figcaption></figure></section>
    </main></div>;
}
