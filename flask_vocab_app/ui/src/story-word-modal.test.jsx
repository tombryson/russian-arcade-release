import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/preact';
vi.mock('../../static/js/preact_deps.js', async () => ({ ...await import('preact'), ...await import('preact/hooks') }));
import { WordModal } from '../../static/js/WordModal.js';
import { StoryText } from '../../static/js/StoryText.js';

const word = { word: 'аптекой', lemma: 'аптека', pos: 'NOUN', can_add: true, in_vocabulary: false, dictionary_url: 'https://en.openrussian.org/ru/аптека', choices: [] };
const source = { story_id: 4, story_key: 'server-snapshot' };
const response = (body, ok = true) => ({ ok, json: async () => body });
function mount(value = word, onSaved = vi.fn()) {
  render(<WordModal word={value} position={{ x: 12, y: 12 }} source={source} onSaved={onSaved} onClose={vi.fn()} />);
  return onSaved;
}
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); document.documentElement.lang = 'en'; localStorage.clear(); });

describe('story word capture', () => {
  it('shows the actual lemma and part of speech without fake translation or empty metadata', () => {
    mount();
    expect(screen.getByText('Noun')).toBeTruthy();
    expect(screen.getByText('аптека')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Open dictionary ↗' }).href).toContain('openrussian.org');
    expect(document.body.textContent).not.toMatch(/Translation disabled|unknown|N\/A|Status/);
  });
  it('sends the selected surface and owned story with the real lemma, then marks saved only on success', async () => {
    const saved = { ...word, can_add: false, in_vocabulary: true, mnemonic: 'A helpful memory cue' };
    const fetch = vi.fn().mockResolvedValue(response(saved)); vi.stubGlobal('fetch', fetch);
    const onSaved = mount();
    fireEvent.click(screen.getByRole('button', { name: 'Add to my words' }));
    expect(screen.getByRole('button', { name: 'Adding word…' }).disabled).toBe(true);
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved));
    expect(fetch.mock.calls[0][0]).toBe('/add-vocab/%D0%B0%D0%BF%D1%82%D0%B5%D0%BA%D0%B0');
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ ...source, word: 'аптекой', pos: 'NOUN' });
    expect(localStorage.getItem('vocabCache')).toBeNull();
  });
  it('keeps failures visible and allows retry instead of claiming success or injecting HTML', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(response({ error: { message: '<img src=x onerror=alert(1)>', saved: true, enrichment_pending: true } }, false))
      .mockResolvedValueOnce(response({ ...word, in_vocabulary: true, can_add: false, mnemonic: 'Memory hint' }));
    vi.stubGlobal('fetch', fetch);
    const saved = mount();
    fireEvent.click(screen.getByRole('button', { name: 'Add to my words' }));
    await screen.findByRole('alert');
    expect(saved).not.toHaveBeenCalled();
    expect(document.querySelector('img')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Prepare memory hint' }));
    await waitFor(() => expect(saved).toHaveBeenCalledOnce());
  });
  it('requires the learner to choose a homograph rather than silently picking a noun or verb', async () => {
    const fetch = vi.fn().mockResolvedValue(response({ ...word, word: 'печь' })); vi.stubGlobal('fetch', fetch);
    mount({ word: 'печь', choices: [
      { lemma: 'печь', pos: 'NOUN', can_add: true }, { lemma: 'печь', pos: 'INFN', can_add: true },
    ] });
    expect(screen.queryByRole('button', { name: 'Add to my words' })).toBeNull();
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'печь:INFN' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add to my words' }));
    await waitFor(() => expect(fetch).toHaveBeenCalledOnce());
    expect(JSON.parse(fetch.mock.calls[0][1].body).pos).toBe('INFN');
  });
  it('shows an existing mnemonic without an add action', () => {
    mount({ ...word, can_add: false, in_vocabulary: true, mnemonic: 'A useful memory hint' });
    expect(screen.getByText('A useful memory hint')).toBeTruthy();
    expect(screen.getByText('Already in vocabulary list')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Add to my words' })).toBeNull();
  });
  it('never trusts an old browser vocabulary cache and looks up the inflected surface again', async () => {
    localStorage.setItem('vocabCache', JSON.stringify(['аптека']));
    const fetch = vi.fn().mockResolvedValue(response(word)); vi.stubGlobal('fetch', fetch);
    render(<StoryText words={[{ word: 'аптекой', lemma: 'аптека' }]} source={source} />);
    fireEvent.click(screen.getByRole('button', { name: 'аптекой' }));
    await screen.findByRole('button', { name: 'Add to my words' });
    expect(fetch.mock.calls[0][0]).toContain('/word-details/%D0%B0%D0%BF%D1%82%D0%B5%D0%BA%D0%BE%D0%B9?');
    fireEvent.click(screen.getByRole('button', { name: 'Close word card' }));
    fireEvent.click(screen.getByRole('button', { name: 'аптекой' }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  });
  it('keeps a retry available after reopening a word with a hint but missing topics', () => {
    mount({ ...word, can_add: false, in_vocabulary: true, mnemonic: 'Existing memory hint', enrichment_pending: true });
    expect(screen.getByRole('button', { name: 'Prepare memory hint' })).toBeTruthy();
  });
  it('shows a readable reload message for an expired session returning HTML', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => { throw new SyntaxError('Unexpected token <'); } }));
    const saved = mount();
    fireEvent.click(screen.getByRole('button', { name: 'Add to my words' }));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Could not load this word. Reload the page and try again.');
    expect(saved).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toContain('Unexpected token');
  });
  it('does not reopen an old word when its save finishes after another word was selected', async () => {
    let finishSave;
    const saveResponse = new Promise(resolve => { finishSave = resolve; });
    const cat = { ...word, word: 'кот', lemma: 'кот' };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response(word)).mockReturnValueOnce(saveResponse).mockResolvedValueOnce(response(cat)));
    render(<StoryText words={[{ word: 'аптекой', lemma: 'аптека' }, { word: 'кот', lemma: 'кот' }]} source={source} />);
    fireEvent.click(screen.getByRole('button', { name: 'аптекой' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Add to my words' }));
    fireEvent.click(screen.getByRole('button', { name: 'Close word card' }));
    fireEvent.click(screen.getByRole('button', { name: 'кот' }));
    await screen.findByRole('button', { name: 'Add to my words' });
    await act(async () => { finishSave(response({ ...word, in_vocabulary: true, mnemonic: 'Hint' })); });
    expect(screen.getByRole('dialog', { name: 'кот' })).toBeTruthy();
    expect(screen.queryByRole('dialog', { name: 'аптекой' })).toBeNull();
  });
  it('shows a failed lookup without an add button', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ error: { message: 'Reopen this story.' } }, false)));
    render(<StoryText words={[{ word: 'аптекой', lemma: 'аптека' }]} source={source} />);
    fireEvent.click(screen.getByRole('button', { name: 'аптекой' }));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Reopen this story.');
    expect(screen.queryByRole('button', { name: 'Add to my words' })).toBeNull();
  });
});
