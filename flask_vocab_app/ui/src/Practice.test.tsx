import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/preact';
import { Practice } from './Practice';

const initial = { id: 's1', profile_id: 'p1', title: 'Food words', revision: 0, status: 'active', completed_items: 0, total_items: 1, attempts: [], item: { id: 'i1', prompt: 'Which word means apple?', choices: [{ id: 'apple', text: 'яблоко' }, { id: 'house', text: 'дом' }], has_hint: true } };
const complete = { ...initial, revision: 1, status: 'completed', completed_items: 1, item: null, attempts: [{ id: 'answer1', feedback: { outcome: 'incorrect', answer: 'яблоко means apple.', assisted: false } }] };
const response = (value: unknown, ok = true) => Promise.resolve({ ok, json: async () => value });
beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue();
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('retries an uncertain save with the identical command and keeps the correction after remount', async () => {
  let writes = 0;
  let saved = false;
  const fetch = vi.fn((_url: string, options?: RequestInit) => {
    if (options?.method === 'POST') {
      saved = true;
      if (++writes === 1) return Promise.reject(new TypeError('Network response lost'));
      return response(complete);
    }
    return response(saved ? complete : initial);
  });
  vi.stubGlobal('fetch', fetch);
  const view = render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}} />);
  fireEvent.click(await screen.findByRole('button', { name: 'дом' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Try saving again' }));
  await screen.findByRole('heading', { name: 'Let’s look at the answer.' });
  const commands = fetch.mock.calls.filter(([, options]) => options?.method === 'POST');
  expect(commands[0][1]?.body).toBe(commands[1][1]?.body);
  expect(screen.getByText('яблоко means apple.')).toBeTruthy();
  view.unmount();
  render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}} />);
  expect(await screen.findByRole('heading', { name: 'Let’s look at the answer.' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /Finish practice/ }));
  expect(screen.getByRole('heading', { name: 'You answered 1 question.' })).toBeTruthy();
});

it('records help before answering and preserves the updated revision', async () => {
  const fetch = vi.fn((url: string) => response(url.endsWith('/help') ? { ...initial, revision: 1, item: { ...initial.item, hint: 'Яблоко means apple.' } } : url.endsWith('/attempts') ? { ...complete, revision: 2, attempts: [{ id: 'answer1', feedback: { outcome: 'correct', answer: 'яблоко', assisted: true } }] } : initial));
  vi.stubGlobal('fetch', fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Show a hint' }));
  await screen.findByText('Яблоко means apple.');
  fireEvent.click(screen.getByRole('button', { name: 'яблоко' }));
  expect(await screen.findByText('You used a hint for this question.')).toBeTruthy();
});

it('uses the latest server revision after another tab answers instead of submitting again', async () => {
  vi.stubGlobal('fetch', vi.fn((_url: string, options?: RequestInit) => options?.method === 'POST'
    ? response({ error: { code: 'stale_revision', message: 'Changed', current_session: complete } }, false) : response(initial)));
  render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}} />);
  fireEvent.click(await screen.findByRole('button', { name: 'дом' }));
  expect(await screen.findByText(/Practice changed in another tab/)).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Try saving again' })).toBeNull();
  expect(screen.getByRole('heading', { name: 'Let’s look at the answer.' })).toBeTruthy();
});

it('clears the task when household access expires', async () => {
  vi.stubGlobal('fetch', vi.fn((_url: string, options?: RequestInit) => options?.method === 'POST'
    ? response({ error: { code: 'locked', message: 'Ask a grown-up to unlock this household.' } }, false) : response(initial)));
  render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}} />);
  fireEvent.click(await screen.findByRole('button', { name: 'дом' }));
  expect(await screen.findByText('Ask a grown-up to unlock this household.')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'яблоко' })).toBeNull();
});

it('keeps the curriculum return route and the saved explanation after reloading a result', async () => {
  const origin = { href: '/curriculum/units/location-destination-v1', title: 'Where and where to' };
  const finished = { ...complete, origin, attempts: [{ id: 'answer1', prompt: 'Нина ждёт тебя …', feedback: {
    outcome: 'incorrect', answer: 'На почте.', assisted: false,
    explanation: 'На почте tells us where Nina is waiting.',
  } }] };
  vi.stubGlobal('fetch', vi.fn(() => response(finished)));
  const onFinish = vi.fn();
  render(<Practice sessionId="s1" profileId="p1" onFinish={onFinish} />);
  expect(await screen.findByText('На почте tells us where Nina is waiting.')).toBeTruthy();
  expect(screen.getByRole('link', { name: 'Where and where to' }).getAttribute('href')).toBe(origin.href);
  expect(screen.getByText('Нина ждёт тебя …')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /Finish practice/ }));
  expect(screen.getByRole('link', { name: /Continue learning/ }).getAttribute('href')).toBe(origin.href);
  expect(onFinish).not.toHaveBeenCalled();
});

it('clears an uncertain command when opening a different learner and session', async () => {
  const second = { ...initial, id: 's2', profile_id: 'p2', item: {
    ...initial.item, prompt: 'Where is the park?', choices: [{ id: 'park', text: 'парк' }],
  } };
  const fetch = vi.fn((url: string, options?: RequestInit) => options?.method === 'POST'
    ? Promise.reject(new TypeError('Network response lost'))
    : response(url.endsWith('/s2') ? second : initial));
  vi.stubGlobal('fetch', fetch);
  const view = render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}} />);
  fireEvent.click(await screen.findByRole('button', { name: 'дом' }));
  await screen.findByRole('button', { name: 'Try saving again' });
  view.rerender(<Practice sessionId="s2" profileId="p2" onFinish={() => {}} />);
  const choice = await screen.findByRole('button', { name: 'парк' });
  expect((choice as HTMLButtonElement).disabled).toBe(false);
  expect(screen.queryByText('Save not confirmed')).toBeNull();
});

it('saves exact typed text, retries the same command and restores the response on reload', async () => {
  const origin = {href: '/curriculum/units/location-destination-v1', title: 'Where and where to'};
  const forms = {...initial, origin, total_items: 3, item: {id: 'form1', type: 'controlled_text', prompt: 'Барсик идёт в ___. (школа)', has_hint: true}};
  const typed = '  В ШКОЛУ!  ';
  const checked = {...forms, revision: 1, completed_items: 1, item: {...forms.item, id: 'form2'}, attempts: [{id: 'answer1', feedback: {
    outcome: 'correct', answer: 'школу', response_text: typed, assisted: false, explanation: 'His destination uses школу.',
  }}]};
  let writes = 0;
  let saved = false;
  const fetch = vi.fn((_url: string, options?: RequestInit) => {
    if(options?.method === 'POST') {saved = true; return ++writes === 1 ? Promise.reject(new TypeError('Response lost')) : response(checked);}
    return response(saved ? checked : forms);
  });
  vi.stubGlobal('fetch', fetch);
  const view = render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}} />);
  const field = await screen.findByRole('textbox', {name: 'Your answer in Russian'});
  expect(screen.queryByText('Choose one answer.')).toBeNull();
  fireEvent.input(field, {target: {value: typed}});
  fireEvent.click(screen.getByRole('button', {name: 'Check answer'}));
  fireEvent.click(await screen.findByRole('button', {name: 'Try saving again'}));
  await screen.findByRole('heading', {name: 'That’s right.'});
  const commands = fetch.mock.calls.filter(([,options]) => options?.method === 'POST');
  expect(commands[0][1]?.body).toBe(commands[1][1]?.body);
  expect(JSON.parse(String(commands[0][1]?.body)).answer).toEqual({text: typed});
  expect(screen.getByText('1 of 3')).toBeTruthy();
  expect(screen.getByText('В ШКОЛУ!').textContent).toBe(typed);
  view.unmount();
  render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}} />);
  expect(await screen.findByText('His destination uses школу.')).toBeTruthy();
  expect(screen.getByText('1 of 3')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', {name: /Next question/}));
  expect(screen.getByText('2 of 3')).toBeTruthy();
  expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('');
});

it('retains a typed draft while requesting a hint and displays a saved incorrect form', async () => {
  const forms = {...initial, item: {id: 'form1', type: 'controlled_text', prompt: 'Нина ждёт на ___. (почта)', has_hint: true}};
  const checked = {...complete, attempts: [{id: 'answer1', feedback: {outcome: 'incorrect', answer: 'почте', response_text: 'почта', assisted: true}}]};
  const fetch = vi.fn((url: string) => response(url.endsWith('/help') ? {...forms, revision: 1, item: {...forms.item, hint: 'Use the location ending -е.'}} : url.endsWith('/attempts') ? checked : forms));
  vi.stubGlobal('fetch', fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}} />);
  fireEvent.input(await screen.findByRole('textbox'), {target: {value: 'почта'}});
  fireEvent.click(screen.getByRole('button', {name: 'Show a hint'}));
  await screen.findByText('Use the location ending -е.');
  expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('почта');
  fireEvent.click(screen.getByRole('button', {name: 'Check answer'}));
  await screen.findByText('You used a hint for this question.');
  expect(screen.getByText('почта')).toBeTruthy();
  expect(screen.getByText('почте')).toBeTruthy();
});


const listening = {...initial, total_items: 2, item: {
  ...initial.item, type: 'listening_choice', prompt: 'Где сейчас Нина?',
  audio: {url: '/static/curriculum/nina.mp3', sha256: 'a'.repeat(64), duration_ms: 2400},
  listened: false, has_transcript: true, transcript: null,
}};
const heard = {...listening, revision: 1, item: {...listening.item, listened: true}};
const postCalls = (fetch: ReturnType<typeof vi.fn>) => fetch.mock.calls.filter(([,options]) => options?.method === 'POST');

it('waits for a saved listening receipt before enabling answers and keeps the transcript off the page', async () => {
  let finishReceipt!: (value: unknown) => void;
  const fetch = vi.fn((url: string) => url.endsWith('/listened')
    ? new Promise(resolve => { finishReceipt = resolve; })
    : response(url.endsWith('/attempts') ? complete : listening));
  vi.stubGlobal('fetch', fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}} />);
  const player = await screen.findByLabelText('Listen to the message');
  expect(player.getAttribute('preload')).toBe('none');
  expect(player.hasAttribute('autoplay')).toBe(false);
  expect(screen.queryByText('Transcript')).toBeNull();
  const choice = screen.getByRole('button', {name: 'дом'}) as HTMLButtonElement;
  expect(choice.disabled).toBe(true);
  fireEvent.click(choice);
  expect(postCalls(fetch)).toHaveLength(0);
  fireEvent.ended(player);
  await waitFor(() => expect(postCalls(fetch)).toHaveLength(1));
  expect(choice.disabled).toBe(true);
  finishReceipt({ok: true, json: async () => heard});
  await waitFor(() => expect(choice.disabled).toBe(false));
  fireEvent.click(choice);
  await screen.findByRole('heading', {name: 'Let’s look at the answer.'});
  expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();
  const answer = postCalls(fetch).at(-1)!;
  expect(answer[0]).toBe('/api/v1/learning-sessions/s1/attempts');
  expect(JSON.parse(String(answer[1].body)).expected_revision).toBe(1);
});

it('retries an uncertain listened receipt without replaying or changing its submission ID', async () => {
  let writes = 0;
  const fetch = vi.fn((url: string) => url.endsWith('/listened')
    ? ++writes === 1 ? Promise.reject(new TypeError('Response lost')) : response(heard)
    : response(listening));
  vi.stubGlobal('fetch', fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}} />);
  const player = await screen.findByLabelText('Listen to the message');
  fireEvent.ended(player);
  await screen.findByText(/you do not need to replay the audio/);
  expect((screen.getByRole('button', {name: 'дом'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.ended(player);
  expect(postCalls(fetch)).toHaveLength(1);
  fireEvent.click(screen.getByRole('button', {name: 'Try saving again'}));
  await waitFor(() => expect((screen.getByRole('button', {name: 'дом'}) as HTMLButtonElement).disabled).toBe(false));
  expect(postCalls(fetch)).toHaveLength(2);
  expect(postCalls(fetch)[0][1].body).toBe(postCalls(fetch)[1][1].body);
});

it('offers audio retry and a saved transcript when playback fails, including retrying a failed transcript request', async () => {
  const transcript = 'Нина сейчас на почте.';
  const read = {...listening, revision: 1, item: {...listening.item, transcript}};
  let transcriptRequests = 0;
  const fetch = vi.fn((url: string) => url.endsWith('/transcript')
    ? ++transcriptRequests === 1 ? Promise.reject(new TypeError('Offline')) : response(read)
    : response(url.endsWith('/attempts') ? {...complete, attempts: [{id: 'answer1', feedback: {
      outcome: 'correct', answer: 'дом', assisted: true, support: ['transcript'], listened: false, transcript,
    }}]} : listening));
  vi.stubGlobal('fetch', fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}} />);
  const player = await screen.findByLabelText('Listen to the message');
  fireEvent.error(player);
  fireEvent.click(await screen.findByRole('button', {name: 'Retry audio'}));
  expect(HTMLMediaElement.prototype.load).toHaveBeenCalledTimes(1);
  expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button', {name: 'Show transcript'}));
  await screen.findByText('The transcript could not open. Try again.');
  expect(screen.queryByText(transcript)).toBeNull();
  expect((screen.getByRole('button', {name: 'дом'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button', {name: 'Try saving again'}));
  await screen.findByText(transcript);
  expect(postCalls(fetch)[0][1].body).toBe(postCalls(fetch)[1][1].body);
  fireEvent.click(screen.getByRole('button', {name: 'дом'}));
  expect(await screen.findByText('Transcript used')).toBeTruthy();
  expect(screen.getByText(transcript)).toBeTruthy();
  expect(postCalls(fetch).some(([url]) => url.endsWith('/listened'))).toBe(false);
});

it('ignores late playback events and a pending receipt response after switching profiles', async () => {
  const second = {...listening, id: 's2', profile_id: 'p2', item: {...listening.item, id: 'i2', prompt: 'Где школа?'}};
  let finishReceipt!: (value: unknown) => void;
  const fetch = vi.fn((url: string) => url.endsWith('/listened')
    ? new Promise(resolve => { finishReceipt = resolve; })
    : response(url.endsWith('/s2') ? second : listening));
  vi.stubGlobal('fetch', fetch);
  const view = render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}} />);
  const oldPlayer = await screen.findByLabelText('Listen to the message');
  fireEvent.ended(oldPlayer);
  await waitFor(() => expect(postCalls(fetch)).toHaveLength(1));
  view.rerender(<Practice sessionId="s2" profileId="p2" onFinish={() => {}} />);
  await screen.findByRole('heading', {name: 'Где школа?'});
  fireEvent.ended(oldPlayer);
  fireEvent.error(oldPlayer);
  finishReceipt({ok: true, json: async () => heard});
  await waitFor(() => expect(screen.queryByText('Saving…')).toBeNull());
  expect(postCalls(fetch)).toHaveLength(1);
  expect(screen.queryByText('The audio is unavailable.')).toBeNull();
  expect(screen.getByRole('heading', {name: 'Где школа?'})).toBeTruthy();
  expect((screen.getByRole('button', {name: 'дом'}) as HTMLButtonElement).disabled).toBe(true);
});

it('does not use the previous question’s audio to unlock the next question', async () => {
  const next = {...listening, revision: 2, completed_items: 1, item: {...listening.item, id: 'i2', prompt: 'Куда идёт Нина?'}, attempts: [{id: 'answer1', feedback: {
    outcome: 'correct', answer: 'дом', assisted: false, listened: true,
  }}]};
  const fetch = vi.fn((url: string) => response(url.endsWith('/listened') ? heard : url.endsWith('/attempts') ? next : listening));
  vi.stubGlobal('fetch', fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}} />);
  const oldPlayer = await screen.findByLabelText('Listen to the message');
  fireEvent.ended(oldPlayer);
  await waitFor(() => expect((screen.getByRole('button', {name: 'дом'}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole('button', {name: 'дом'}));
  fireEvent.click(await screen.findByRole('button', {name: /Next question/}));
  expect(await screen.findByRole('heading', {name: 'Куда идёт Нина?'})).toBeTruthy();
  fireEvent.ended(oldPlayer);
  fireEvent.error(oldPlayer);
  expect(screen.getByLabelText('Listen to the message')).not.toBe(oldPlayer);
  expect(postCalls(fetch)).toHaveLength(2);
  expect(screen.queryByText('The audio is unavailable.')).toBeNull();
  expect((screen.getByRole('button', {name: 'дом'}) as HTMLButtonElement).disabled).toBe(true);
});

it('saves a listen completed during a hint request against the resulting revision', async () => {
  let finishHint!: (value: unknown) => void;
  const fetch = vi.fn((url: string) => url.endsWith('/help')
    ? new Promise(resolve => {finishHint = resolve;})
    : response(url.endsWith('/listened') ? {...heard, revision: 2} : listening));
  vi.stubGlobal('fetch', fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}} />);
  const player = await screen.findByLabelText('Listen to the message');
  fireEvent.click(screen.getByRole('button', {name: 'Show a hint'}));
  fireEvent.ended(player);
  expect(postCalls(fetch)).toHaveLength(1);
  finishHint({ok: true, json: async () => ({...listening, revision: 1, item: {...listening.item, hint: 'Listen for сейчас.'}})});
  await waitFor(() => expect(postCalls(fetch)).toHaveLength(2));
  const receipt = postCalls(fetch)[1];
  expect(receipt[0]).toBe('/api/v1/learning-sessions/s1/listened');
  expect(JSON.parse(String(receipt[1].body)).expected_revision).toBe(1);
  await waitFor(() => expect((screen.getByRole('button', {name: 'дом'}) as HTMLButtonElement).disabled).toBe(false));
});

it('recovers a stale listening receipt without writing against the next question', async () => {
  const advanced = {...listening, revision: 2, completed_items: 1, item: {...listening.item, id: 'i2'}, attempts: [{id: 'answer1', feedback: {
    outcome: 'correct', answer: 'дом', assisted: false,
  }}]};
  const fetch = vi.fn((_url: string, options?: RequestInit) => options?.method === 'POST'
    ? response({error: {code: 'stale_revision', current_session: advanced}}, false)
    : response(listening));
  vi.stubGlobal('fetch', fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}} />);
  fireEvent.ended(await screen.findByLabelText('Listen to the message'));
  await screen.findByText(/Practice changed in another tab/);
  fireEvent.click(screen.getByRole('button', {name: /Next question/}));
  expect((screen.getByRole('button', {name: 'дом'}) as HTMLButtonElement).disabled).toBe(true);
  expect(postCalls(fetch)).toHaveLength(1);
  expect(screen.queryByRole('button', {name: 'Try saving again'})).toBeNull();
});


it('keeps transcript assistance when recording a later listen', async () => {
  const transcript = 'Нина сейчас на почте.';
  const read = {...listening, revision: 1, item: {...listening.item, transcript}};
  const fetch = vi.fn((url: string) => response(url.endsWith('/listened')
    ? {...read, revision: 2, item: {...read.item, listened: true}}
    : url.endsWith('/transcript') ? read : listening));
  vi.stubGlobal('fetch', fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}} />);
  fireEvent.click(await screen.findByRole('button', {name: 'Show transcript'}));
  await screen.findByText(transcript);
  fireEvent.ended(screen.getByLabelText('Listen to the message'));
  await waitFor(() => expect(postCalls(fetch)).toHaveLength(2));
  expect(postCalls(fetch)[1][0]).toBe('/api/v1/learning-sessions/s1/listened');
  expect(JSON.parse(String(postCalls(fetch)[1][1].body)).expected_revision).toBe(1);
  expect(screen.getByText(transcript)).toBeTruthy();
});

it.each(['profile_changed', 'account_changed'])('clears the player and stops saving after %s during a listening receipt', async (code) => {
  const fetch = vi.fn((_url: string, options?: RequestInit) => options?.method === 'POST'
    ? response({error: {code, message: 'Choose your profile again.'}}, false)
    : response(listening));
  vi.stubGlobal('fetch', fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}} />);
  const oldPlayer = await screen.findByLabelText('Listen to the message');
  fireEvent.ended(oldPlayer);
  await screen.findByText('Choose your profile again.');
  expect(screen.queryByLabelText('Listen to the message')).toBeNull();
  expect(screen.queryByRole('button', {name: 'Try saving again'})).toBeNull();
  expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();
  fireEvent.ended(oldPlayer);
  expect(postCalls(fetch)).toHaveLength(1);
});


it('allows transcript recovery when the server cannot verify the audio receipt', async () => {
  const transcript = 'Нина сейчас на почте.';
  const read = {...listening, revision: 1, item: {...listening.item, transcript}};
  const fetch = vi.fn((url: string) => url.endsWith('/listened')
    ? response({error: {code: 'audio_unavailable', message: 'The recording is unavailable.'}}, false)
    : response(url.endsWith('/transcript') ? read : listening));
  vi.stubGlobal('fetch', fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}} />);
  fireEvent.ended(await screen.findByLabelText('Listen to the message'));
  await screen.findByText('The audio is unavailable.');
  expect(screen.queryByText('Save not confirmed')).toBeNull();
  expect(screen.queryByRole('button', {name: 'Try saving again'})).toBeNull();
  expect((screen.getByRole('button', {name: 'Retry audio'}) as HTMLButtonElement).disabled).toBe(false);
  expect((screen.getByRole('button', {name: 'Show transcript'}) as HTMLButtonElement).disabled).toBe(false);
  expect((screen.getByRole('button', {name: 'дом'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button', {name: 'Show transcript'}));
  await screen.findByText(transcript);
  expect((screen.getByRole('button', {name: 'дом'}) as HTMLButtonElement).disabled).toBe(false);
  const requests = postCalls(fetch);
  expect(requests.map(([url]) => url)).toEqual(['/api/v1/learning-sessions/s1/listened', '/api/v1/learning-sessions/s1/transcript']);
  expect(JSON.parse(String(requests[1][1].body)).expected_revision).toBe(0);
  expect(JSON.parse(String(requests[1][1].body)).submission_id).not.toBe(JSON.parse(String(requests[0][1].body)).submission_id);
});

it('can replay and save a new receipt after a definitive audio-unavailable response', async () => {
  let receipts = 0;
  const fetch = vi.fn((url: string) => url.endsWith('/listened')
    ? ++receipts === 1
      ? response({error: {code: 'audio_unavailable', message: 'The recording is unavailable.'}}, false)
      : response(heard)
    : response(listening));
  vi.stubGlobal('fetch', fetch);
  render(<Practice sessionId="s1" profileId="p1" onFinish={() => {}} />);
  const player = await screen.findByLabelText('Listen to the message');
  fireEvent.ended(player);
  fireEvent.click(await screen.findByRole('button', {name: 'Retry audio'}));
  expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
  fireEvent.ended(player);
  await waitFor(() => expect((screen.getByRole('button', {name: 'дом'}) as HTMLButtonElement).disabled).toBe(false));
  const requests = postCalls(fetch);
  expect(requests).toHaveLength(2);
  expect(JSON.parse(String(requests[1][1].body)).submission_id).not.toBe(JSON.parse(String(requests[0][1].body)).submission_id);
});
