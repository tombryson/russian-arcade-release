import 'vite/modulepreload-polyfill';
import '@fontsource/golos-text/latin-400.css';
import '@fontsource/golos-text/latin-500.css';
import '@fontsource/golos-text/cyrillic-400.css';
import '@fontsource/golos-text/cyrillic-500.css';
import '@fontsource/unbounded/latin-500.css';
import '@fontsource/unbounded/cyrillic-500.css';
import './styles/tokens.generated.css';
import './styles/word-post.css';
import './styles/flashcards.css';
import './styles/activity-workspace.css';
import '../../static/css/activity_entry.css';
import { render, type ComponentChild } from 'preact';
import { App } from './App';
import '../../static/css/navigation_layout.css';
import { bindUserSession } from './learning-api';
import { installAppUrlVnodes } from './app-url-vnodes';

installAppUrlVnodes();
const root = document.getElementById('word-post');
if (root) {
  const mount = (view: ComponentChild) => {
    root.replaceChildren();
    render(view, root);
  };
  if (root.dataset.view === 'catalogue') {
    void import('./Catalogue').then(({ Catalogue }) => mount(<Catalogue />)).catch(() => {
      mount(<main class="page"><h1>The component guide could not open.</h1><p>Try reloading, or <a href="/">open Russian Arcade</a>.</p></main>);
    });
  } else {
    const profile=JSON.parse(root.dataset.profile ?? 'null');
    const accountMode=root.dataset.accountMode === 'demo' ? 'demo' : root.dataset.accountMode === 'hosted' ? 'hosted' : root.dataset.accountMode === 'preview' ? 'preview' : 'local';
    bindUserSession(root.dataset.household === 'true' ? undefined : profile?.id ?? '',root.dataset.csrf ?? '',root.dataset.sessionScope);
    mount(<App defaultCourseRelease={root.dataset.defaultCourseRelease} navigationLayout={root.dataset.navigationLayout === 'sidebar' ? 'sidebar' : 'top'} initialOnboarding={JSON.parse(root.dataset.onboarding ?? 'null') ?? undefined} initialProfile={profile} householdEnabled={root.dataset.household === 'true'} accountMode={accountMode} signInAvailable={root.dataset.signInAvailable === 'true'} demoAvailable={root.dataset.demoAvailable === 'true'} sessionScope={root.dataset.sessionScope} nativeEnabled={root.dataset.native !== 'false'} language={root.dataset.language === 'ru' ? 'ru' : 'en'} csrfToken={root.dataset.csrf ?? ''} navigation={JSON.parse(root.dataset.navigation ?? 'null')} />);
  }
}
