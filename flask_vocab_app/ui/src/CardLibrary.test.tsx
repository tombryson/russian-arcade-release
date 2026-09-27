import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/preact';
import { Flashcards } from './Flashcards';
import type { CardOverview, LibraryCard } from './review-types';

// jsdom does not implement the native dialog methods used by the browser.
const nativeShowModal = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal');
const nativeClose = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close');
beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {configurable: true, value: function(this: HTMLDialogElement) {this.open = true;}});
  Object.defineProperty(HTMLDialogElement.prototype, 'close', {configurable: true, value: function(this: HTMLDialogElement) {
    if (!this.open) return;
    this.open = false;
    this.dispatchEvent(new Event('close'));
  }});
});
afterAll(() => {
  if (nativeShowModal) Object.defineProperty(HTMLDialogElement.prototype, 'showModal', nativeShowModal);
  else delete (HTMLDialogElement.prototype as Partial<HTMLDialogElement>).showModal;
  if (nativeClose) Object.defineProperty(HTMLDialogElement.prototype, 'close', nativeClose);
  else delete (HTMLDialogElement.prototype as Partial<HTMLDialogElement>).close;
});

const response = (value: unknown) => Promise.resolve({ok: true, json: async () => value});
const cards: LibraryCard[] = [
  {
    id: 'map-card', version_id: 'map-version', lemma: 'карта', title: 'What’s in the bag?',
    direction: 'ru-cloze', prompt: 'Это [[blank]].', answer: 'карта', context: 'Это карта.',
    cue_en: 'a map', context_meaning: 'This is a map.', explanation: 'Use the nominative here.',
    dictionary_url: 'https://en.openrussian.org/ru/карта', decks: [],
    status: 'new', due: false, buried: false, due_at: null, revision: 0,
    assets: [{id: 'map-picture', role: 'prompt', kind: 'image', media_type: 'image/png'},
      {id: 'map-audio', role: 'answer', kind: 'sentence_audio', media_type: 'audio/mpeg'}],
  },
  {
    id: 'letter-card', version_id: 'letter-version', lemma: 'письмо', title: 'A letter for you',
    direction: 'ru-cloze', prompt: 'Вот [[blank]] для тебя.', answer: 'письмо', context: 'Вот письмо для тебя.',
    cue_en: 'a letter', context_meaning: 'Here is a letter for you.', explanation: 'The letter is for the person you are speaking to.',
    dictionary_url: 'https://en.openrussian.org/ru/письмо', decks: [],
    status: 'learning', due: true, buried: false, due_at: 900, revision: 3,
    assets: [{id: 'letter-picture', role: 'prompt', kind: 'image', media_type: 'image/png'}],
  },
];
const overview: CardOverview = {
  profile_id: 'learner', profile_name: 'Me', cards, active_session_id: null, server_now: 1000, new_limit: 5,
  counts: {cards: 2, words: 2, due: 1, new: 1, new_allowance: 5, ready: 2, learning: 1, reviewing: 0,
    suspended: 0, buried: 0, practised_today: 0, answers_today: 0, next_due_at: null},
};

async function openLibrary() {
  render(<Flashcards profileId="learner" personal />);
  return screen.findAllByRole('button', {name: /^Open card:/});
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('Compact card library', () => {
  it('shows every card row immediately without mounting its answer, media or management controls', async () => {
    const fetch = vi.fn((_url: string, _options?: RequestInit) => response(overview));
    vi.stubGlobal('fetch', fetch);
    const rows = await openLibrary();

    expect(screen.getByRole('heading', {name: /Your cards/})).toBeTruthy();
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain('карта');
    expect(rows[0].textContent).toContain('Это [...].');
    expect(rows[0].textContent).toContain('Missing word');
    expect(rows[0].textContent).toContain('New');
    expect(rows[1].textContent).toContain('письмо');
    expect(rows[1].textContent).toContain('Вот [...] для тебя.');
    expect(rows[1].textContent).toContain('Ready now');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByText('This is a map.')).toBeNull();
    expect(screen.queryByText('Here is a letter for you.')).toBeNull();
    expect(screen.queryByRole('link', {name: 'Edit card'})).toBeNull();
    for (const name of ['Delete card', 'Set aside', 'History', 'Add audio & picture']) {
      expect(screen.queryByRole('button', {name})).toBeNull();
    }
    expect(document.querySelector('audio, img[src*="/api/v1/assets/"]')).toBeNull();
    expect(fetch.mock.calls).toHaveLength(1);
    expect(fetch.mock.calls[0][1]?.method).toBe('GET');
  });

  it('opens only the selected card, keeps browsing read-only, and returns focus when closed', async () => {
    const fetch = vi.fn((_url: string, _options?: RequestInit) => response(overview));
    vi.stubGlobal('fetch', fetch);
    await openLibrary();
    const opener = screen.getByRole('button', {name: 'Open card: письмо'});
    opener.focus();
    fireEvent.click(opener);

    const dialog = await screen.findByRole('dialog', {name: 'Card details'});
    expect(within(dialog).getByText('Here is a letter for you.')).toBeTruthy();
    expect(within(dialog).queryByText('This is a map.')).toBeNull();
    expect(within(dialog).getByRole('link', {name: 'Edit card'}).getAttribute('href')).toBe('/post/flashcards/manage?edit=letter-version');
    expect(within(dialog).getByRole('button', {name: 'Delete card'})).toBeTruthy();
    expect(within(dialog).getByRole('button', {name: 'Set aside'})).toBeTruthy();
    expect(within(dialog).getByRole('button', {name: 'History'})).toBeTruthy();
    expect(within(dialog).getByRole('img', {name: 'Illustration of the example sentence'}).getAttribute('src')).toBe('/api/v1/assets/letter-picture');
    expect(document.querySelector('img[src="/api/v1/assets/map-picture"]')).toBeNull();

    fireEvent.click(within(dialog).getByRole('button', {name: 'Close card details'}));
    await vi.waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await vi.waitFor(() => expect(document.activeElement).toBe(opener));
    expect(screen.queryByText('Here is a letter for you.')).toBeNull();
    expect(fetch.mock.calls).toHaveLength(1);
    expect(fetch.mock.calls.every(([, options]) => options?.method === 'GET')).toBe(true);
  });

  it('handles the native Escape cancel event and leaves the library ready for another card', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response(overview)));
    await openLibrary();
    const opener = screen.getByRole('button', {name: 'Open card: карта'});
    opener.focus();
    fireEvent.click(opener);
    const dialog = await screen.findByRole('dialog', {name: 'Card details'});
    fireEvent(dialog, new Event('cancel', {bubbles: false, cancelable: true}));
    await vi.waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await vi.waitFor(() => expect(document.activeElement).toBe(opener));
    fireEvent.click(screen.getByRole('button', {name: 'Open card: письмо'}));
    expect(await screen.findByText('Here is a letter for you.')).toBeTruthy();
  });

  it('deletes the selected card without sending a review or changing the neighbouring card', async () => {
    let deleted = false;
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const fetch = vi.fn((url: string, _options?: RequestInit) => {
      if (url === '/api/v1/cards/letter-card/delete') {
        deleted = true;
        return response({deleted: true});
      }
      return response(deleted ? {...overview, cards: [cards[0]], counts: {...overview.counts, cards: 1, words: 1}} : overview);
    });
    vi.stubGlobal('fetch', fetch);
    await openLibrary();
    fireEvent.click(screen.getByRole('button', {name: 'Open card: письмо'}));
    const dialog = await screen.findByRole('dialog', {name: 'Card details'});
    fireEvent.click(within(dialog).getByRole('button', {name: 'Delete card'}));

    await vi.waitFor(() => expect(fetch.mock.calls.some(([url]) => url === '/api/v1/cards/letter-card/delete')).toBe(true));
    await vi.waitFor(() => expect(screen.queryByRole('button', {name: 'Open card: письмо'})).toBeNull());
    const remaining = await screen.findByRole('button', {name: 'Open card: карта'});
    await vi.waitFor(() => expect(document.activeElement).toBe(remaining));
    expect(screen.queryByRole('dialog')).toBeNull();
    const writes = fetch.mock.calls.filter(([, options]) => options?.method !== 'GET');
    expect(writes).toHaveLength(1);
    expect(writes[0][0]).toBe('/api/v1/cards/letter-card/delete');
    expect(writes[0][1]?.method).toBe('POST');
    expect(fetch.mock.calls.some(([url]) => /\/reviews$|\/suspension$|\/review-sessions/.test(url))).toBe(false);
  });

  it('returns focus to the same card after setting it aside, even when the refreshed list is reordered', async () => {
    let suspended = false;
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.endsWith('/letter-card/suspension')) {
        suspended = true;
        return response({suspended: true});
      }
      return response(suspended ? {...overview, cards: [{...cards[1], status: 'suspended', due: false}, cards[0]]} : overview);
    }));
    const focus = vi.spyOn(HTMLElement.prototype, 'focus');
    await openLibrary();
    fireEvent.click(screen.getByRole('button', {name: 'Open card: письмо'}));
    const dialog = await screen.findByRole('dialog', {name: 'Card details'});
    fireEvent.click(within(dialog).getByRole('button', {name: 'Set aside'}));

    await vi.waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    const restored = await screen.findByRole('button', {name: 'Open card: письмо'});
    await vi.waitFor(() => expect(document.activeElement).toBe(restored));
    expect(restored.textContent).toContain('Set aside');
    expect(focus).toHaveBeenLastCalledWith({preventScroll: true});
  });

  it('returns focus to the library heading after deleting the last card', async () => {
    let deleted = false;
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.endsWith('/letter-card/delete')) {
        deleted = true;
        return response({deleted: true});
      }
      return response({...overview, cards: deleted ? [] : [cards[1]], counts: {...overview.counts, cards: deleted ? 0 : 1}});
    }));
    await openLibrary();
    fireEvent.click(screen.getByRole('button', {name: 'Open card: письмо'}));
    const dialog = await screen.findByRole('dialog', {name: 'Card details'});
    fireEvent.click(within(dialog).getByRole('button', {name: 'Delete card'}));

    await screen.findByText('No flashcards yet.');
    const heading = screen.getByRole('heading', {name: /Your cards/});
    await vi.waitFor(() => expect(document.activeElement).toBe(heading));
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
