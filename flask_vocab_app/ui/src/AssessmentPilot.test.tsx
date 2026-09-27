import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/preact';
import { AssessmentPilot } from './AssessmentPilot';
import { bindUserSession } from './learning-api';
import type { AssessmentDomain, PilotComponent, PilotOverview, PilotSession } from './assessment-api';

const domains: AssessmentDomain[] = ['language_use', 'reading', 'listening', 'writing', 'speaking'];
const component = (domain: AssessmentDomain): PilotComponent => ({
  id: `${domain}-one`, domain, title: `${domain} task`, prompt: `Try ${domain}.`, format: ['speaking', 'writing'].includes(domain) ? domain : 'choice_set',
  revision: 0, state: 'not_started', support: [], history: [], draft: domain === 'writing' ? { text: '' } : { answers: {} },
  ...(!['speaking', 'writing'].includes(domain) ? { questions: [{ id: 'where', prompt: 'Где Анна?', choices: [{ id: 'a', text: 'В школе.' }, { id: 'b', text: 'Дома.' }] }] } : {}),
  ...(domain === 'reading' ? { passage: 'Анна в школе.' } : {}),
  ...(domain === 'listening' ? { audio_url: '/listen.mp3', audio_available: true, listened: false, transcript_visible: false } : {}),
});
const session = (): PilotSession => ({ id: 'pilot-one', profile_id: 'p', blueprint_id: 'a1-pilot', status: 'active', diagnostic: true, limitations: [], created_at: 1, components: domains.map(component) });
const overview = (): PilotOverview => ({ profile_id: 'p', enabled: true, configured: { writing: true, speaking: true }, blueprint: { id: 'a1-pilot', title: 'A1', level: 'A1', domains: domains.map(id => ({id, title: id})), limitations: [] }, active_session: null, sessions: [] });
const response = (data: unknown, ok = true) => Promise.resolve({ ok, json: async () => data });
const body = (init?: RequestInit) => JSON.parse(String(init?.body ?? '{}'));
function setup(handler: (url: string, init?: RequestInit) => ReturnType<typeof response> = url => response(url.endsWith('/assessment-pilot') ? overview() : session())) {
  const fetch = vi.fn(handler); vi.stubGlobal('fetch', fetch); return fetch;
}
async function chooseSkill(name: string) { fireEvent.click(within(await screen.findByRole('navigation', { name: 'Skills' })).getByRole('button', { name: new RegExp('^' + name) })); }

beforeEach(() => {
  bindUserSession('p', 'csrf'); window.location.hash = '';
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {});
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('Assessment pilot', () => {
  it('is opt-in, shows five domains and offers a saved check without starting another', async () => {
    const fetch = setup(() => response({ ...overview(), active_session: session() }));
    render(<AssessmentPilot profileId="p" />);
    expect(await screen.findByRole('heading', { name: 'Check your A1 skills' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Continue your check →' }).getAttribute('href')).toBe('#assessment/pilot-one');
    expect(screen.getByText(/does not award a level/)).toBeTruthy();
    expect(fetch.mock.calls.every(([, init]) => init?.method === 'GET')).toBe(true);
  });

  it('retries an uncertain start with the same command and suppresses duplicate clicks', async () => {
    let starts = 0;
    const fetch = setup((url, init) => response(url.endsWith('/assessment-pilot') ? overview() : ++starts === 1 ? { error: { code: 'request_failed', message: 'Connection interrupted.' } } : session(), !init?.body || starts !== 1));
    render(<AssessmentPilot profileId="p" />);
    const start = await screen.findByRole('button', { name: 'Start the skills check →' });
    fireEvent.click(start); fireEvent.click(start);
    fireEvent.click(await screen.findByRole('button', { name: 'Try saving again' }));
    await vi.waitFor(() => expect(window.location.hash).toBe('#assessment/pilot-one'));
    const calls = fetch.mock.calls.filter(([, init]) => init?.method === 'POST');
    expect(calls).toHaveLength(2); expect(body(calls[0][1])).toEqual(body(calls[1][1]));
  });

  it('keeps reading text separate and never embeds the unrevealed listening transcript', async () => {
    setup(); render(<AssessmentPilot sessionId="pilot-one" profileId="p" />);
    await chooseSkill('Reading'); expect(await screen.findByText('Анна в школе.')).toBeTruthy();
    await chooseSkill('Listening');
    expect(screen.queryByText('Анна в школе.')).toBeNull();
    expect(screen.getByRole('radio', { name: 'В школе.' }).closest('fieldset')?.disabled).toBe(true);
    expect(screen.getByRole('button', { name: 'Check my reply' }).hasAttribute('disabled')).toBe(true);
    expect(screen.getByLabelText('Listen to the message').getAttribute('preload')).toBe('none');
  });

  it('saves listening before enabling answers and retries its receipt without replay', async () => {
    const saved = session(); let receipts = 0;
    const fetch = setup((url) => {
      if (url.endsWith('/assessment-pilot')) return response(overview());
      if (url.endsWith('/support')) {
        if (++receipts === 1) return response({ error: { code: 'request_failed', message: 'Connection interrupted.' } }, false);
        saved.components[2].listened = true; saved.components[2].revision = 1;
      }
      return response(structuredClone(saved));
    });
    render(<AssessmentPilot sessionId="pilot-one" profileId="p" />); await chooseSkill('Listening');
    fireEvent.ended(screen.getByLabelText('Listen to the message'));
    const retry = await screen.findByRole('button', { name: 'Try saving again' });
    expect(screen.getByRole('radio', { name: 'В школе.' }).closest('fieldset')?.disabled).toBe(true);
    fireEvent.click(retry);
    await vi.waitFor(() => expect(screen.getByRole('radio', { name: 'В школе.' }).closest('fieldset')?.disabled).toBe(false));
    const calls = fetch.mock.calls.filter(([url]) => url.endsWith('/support'));
    expect(calls).toHaveLength(2); expect(body(calls[0][1])).toEqual(body(calls[1][1]));
    expect(body(calls[0][1]).kind).toBe('listened');
  });

  it('recovers missing audio through explicit transcript support', async () => {
    const saved = session();
    const fetch = setup((url, init) => {
      if (url.endsWith('/assessment-pilot')) return response(overview());
      if (url.endsWith('/support')) {
        if (body(init).kind === 'listened') return response({ error: { code: 'audio_unavailable', message: 'Recording unavailable.' } }, false);
        Object.assign(saved.components[2], { passage: 'Анна в школе.', transcript_visible: true, support: ['transcript'], revision: 1 });
      }
      return response(structuredClone(saved));
    });
    render(<AssessmentPilot sessionId="pilot-one" profileId="p" />); await chooseSkill('Listening');
    fireEvent.ended(screen.getByLabelText('Listen to the message'));
    await screen.findByText('Recording unavailable.');
    const reveal = screen.getByRole('button', { name: 'Show transcript' }); expect(reveal.hasAttribute('disabled')).toBe(false); fireEvent.click(reveal);
    expect(await screen.findByText('Анна в школе.')).toBeTruthy();
    expect(screen.getByText('Transcript used')).toBeTruthy();
    expect(fetch.mock.calls.filter(([url]) => url.endsWith('/support')).map(([, init]) => body(init).kind)).toEqual(['listened', 'transcript']);
  });

  it('ignores late audio events after changing component', async () => {
    const fetch = setup(); render(<AssessmentPilot sessionId="pilot-one" profileId="p" />); await chooseSkill('Listening');
    const old = screen.getByLabelText('Listen to the message'); await chooseSkill('Writing'); fireEvent.ended(old);
    await act(async () => {});
    expect(fetch.mock.calls.some(([url]) => url.endsWith('/support'))).toBe(false);
    expect(screen.getByLabelText('Your message in Russian')).toBeTruthy();
  });

  it.each(['missing', 'playback failed'])('records %s listening without guessing answers or claiming a listen', async status => {
    const saved = session();
    if (status === 'missing') Object.assign(saved.components[2], { audio_available: false, audio_url: null });
    const fetch = setup(url => response(url.endsWith('/assessment-pilot') ? overview() : structuredClone(saved)));
    render(<AssessmentPilot sessionId="pilot-one" profileId="p" />); await chooseSkill('Listening');
    if (status === 'missing') expect(screen.queryByText('Listen to the recording before choosing your answers.')).toBeNull();
    else fireEvent.error(screen.getByLabelText('Listen to the message'));
    fireEvent.click(screen.getByRole('button', { name: 'Continue without listening' }));
    await vi.waitFor(() => expect(fetch.mock.calls.some(([url]) => url.endsWith('/attempts'))).toBe(true));
    const attempt = fetch.mock.calls.find(([url]) => url.endsWith('/attempts'));
    expect(body(attempt?.[1]).response).toEqual({ unavailable: true });
    expect(fetch.mock.calls.some(([url]) => url.endsWith('/support'))).toBe(false);
  });

  it('saves a writing draft when moving to another skill and resumes exact text', async () => {
    const saved = session();
    const fetch = setup((url, init) => {
      if (url.endsWith('/assessment-pilot')) return response(overview());
      if (url.endsWith('/draft')) { saved.components[3].draft = body(init).response; saved.components[3].revision++; }
      return response(structuredClone(saved));
    });
    render(<AssessmentPilot sessionId="pilot-one" profileId="p" />); await chooseSkill('Writing');
    fireEvent.input(screen.getByLabelText('Your message in Russian'), { target: { value: '  Привет! Я дома.\n' } });
    await chooseSkill('Reading'); await screen.findByRole('heading', { name: 'reading task' });
    await chooseSkill('Writing');
    expect((screen.getByLabelText('Your message in Russian') as HTMLTextAreaElement).value).toBe('  Привет! Я дома.\n');
    expect(body(fetch.mock.calls.find(([url]) => url.endsWith('/draft'))![1])).toMatchObject({ expected_revision: 0, response: { text: '  Привет! Я дома.\n' } });
  });

  it('keeps feedback readable and marks transcript assistance without a pass score', async () => {
    const saved = session(); saved.components[2].attempt = { submission_id: 's', review_status: 'ready', outcome: 'practise_and_retry', feedback: 'Listen for the meeting time.', criteria: [{ label: 'Meeting time', feedback: 'Half past nine comes before the lesson.' }], support: ['transcript'] };
    setup(url => response(url.endsWith('/assessment-pilot') ? overview() : saved));
    render(<AssessmentPilot sessionId="pilot-one" profileId="p" />); await chooseSkill('Listening');
    expect(screen.getByText('Listen for the meeting time.')).toBeTruthy();
    expect(screen.getByText('You used the transcript for this reply.')).toBeTruthy();
    expect(screen.queryByRole('progressbar')).toBeNull(); expect(screen.queryByText(/Passed|unlocked|coins/i)).toBeNull();
  });

  it.each(['failed', 'review_unavailable', 'expired'])('never retries a %s provider review on GET and retries only after an explicit click', async review_status => {
    const saved = session(); saved.components[3].attempt = { submission_id: 's', review_status, response: { text: 'Привет!' } };
    const fetch = setup(url => response(url.endsWith('/assessment-pilot') ? overview() : saved));
    render(<AssessmentPilot sessionId="pilot-one" profileId="p" />); await chooseSkill('Writing');
    const retry = screen.getByRole('button', { name: 'Try feedback again' });
    expect(fetch.mock.calls.every(([, init]) => init?.method === 'GET')).toBe(true); fireEvent.click(retry);
    await vi.waitFor(() => expect(fetch.mock.calls.some(([url]) => url.endsWith('/review'))).toBe(true));
    expect(body(fetch.mock.calls.find(([url]) => url.endsWith('/review'))![1])).toEqual({ submission_id: expect.any(String), component_id: 'writing-one' });
  });

  it('releases a rejected retake when another tab is reviewing the saved reply', async () => {
    const saved = session(); saved.components[3].attempt = { submission_id: 's', review_status: 'review_unavailable', response: { text: 'Привет!' } };
    const fetch = setup(url => url.endsWith('/retry') ? response({ error: { code: 'component_busy', message: 'The review is still running.' } }, false) : response(url.endsWith('/assessment-pilot') ? overview() : saved));
    render(<AssessmentPilot sessionId="pilot-one" profileId="p" />); await chooseSkill('Writing');
    fireEvent.click(screen.getByRole('button', { name: 'Try this skill again' }));
    expect(await screen.findByText('The review is still running.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Try saving again' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Try feedback again' }).hasAttribute('disabled')).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: 'Reload saved check' }));
    await screen.findByRole('heading', { name: 'language_use task' });
    expect(fetch.mock.calls.filter(([url]) => url.endsWith('/retry'))).toHaveLength(1);
  });

  it.each(['Listening', 'Speaking'])('shows one clear unmeasured message for skipped %s and keeps retry available', async skill => {
    const saved = session(); const row = saved.components[skill === 'Listening' ? 2 : 4];
    const message = 'This component was not measured. Your other results remain available.';
    row.attempt = { submission_id: 'skipped', review_status: 'ready', outcome: 'more_evidence_needed', response: { unavailable: true }, feedback: message,
      criteria: [1, 2, 3].map(() => ({ feedback: message })) };
    setup(url => response(url.endsWith('/assessment-pilot') ? overview() : saved));
    render(<AssessmentPilot sessionId="pilot-one" profileId="p" />); await chooseSkill(skill);
    expect(screen.getByRole('heading', { name: `${skill} was not measured.` })).toBeTruthy();
    expect(screen.queryByText(row.prompt)).toBeNull();
    expect(screen.getAllByText(message)).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Try this skill again' }).hasAttribute('disabled')).toBe(false);
  });

  it('discards another profile’s snapshot rather than displaying their drafts', async () => {
    const saved = session(); saved.profile_id = 'other'; saved.components[0].title = 'Private task';
    setup(url => response(url.endsWith('/assessment-pilot') ? overview() : saved));
    render(<AssessmentPilot sessionId="pilot-one" profileId="p" />);
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.queryByText('Private task')).toBeNull(); expect(screen.getByRole('link', { name: 'Choose a profile' })).toBeTruthy();
  });
  it('lets the other skills start while listening recordings are unavailable', async () => {
    setup(() => response({ ...overview(), recordings_ready: false }));
    const view = render(<AssessmentPilot profileId="p" />);
    expect(await screen.findByText('Listening is unavailable. You can check the other skills now.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Start the skills check →' }).hasAttribute('disabled')).toBe(false);
    view.unmount();
    setup(() => response({ ...overview(), recordings_ready: false, active_session: session() }));
    render(<AssessmentPilot profileId="p" />);
    expect(await screen.findByRole('link', { name: 'Continue your check →' })).toBeTruthy();
  });

  it('saves original writing when feedback is unavailable and includes the exact component identity', async () => {
    const saved = session();
    const fetch = setup((url, init) => {
      if (url.endsWith('/assessment-pilot')) return response({ ...overview(), configured: { writing: false, speaking: false } });
      if (url.endsWith('/attempts')) saved.components[3].attempt = { review_status: 'review_unavailable', response: body(init).response };
      return response(structuredClone(saved));
    });
    render(<AssessmentPilot sessionId="pilot-one" profileId="p" />); await chooseSkill('Writing');
    fireEvent.input(screen.getByLabelText('Your message in Russian'), { target: { value: 'Привет! Я дома.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save my reply' }));
    expect(await screen.findByRole('button', { name: 'Try feedback again' })).toBeTruthy();
    expect(body(fetch.mock.calls.find(([url]) => url.endsWith('/attempts'))![1])).toMatchObject({ component_id: 'writing-one', expected_revision: 0, response: { text: 'Привет! Я дома.' } });
  });

  it('requires reload after a retry form changes in another tab', async () => {
    const fetch = setup((url) => url.endsWith('/support') ? response({ error: { code: 'stale_component', message: 'Changed.' } }, false) : response(url.endsWith('/assessment-pilot') ? overview() : session()));
    render(<AssessmentPilot sessionId="pilot-one" profileId="p" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Show a hint' }));
    expect(await screen.findByText(/changed in another tab/)).toBeTruthy();
    expect(screen.getByRole('radio', { name: 'В школе.' }).closest('fieldset')?.disabled).toBe(true);
    expect(screen.queryByRole('button', { name: 'Try saving again' })).toBeNull();
    expect(body(fetch.mock.calls.find(([url]) => url.endsWith('/support'))![1]).component_id).toBe('language_use-one');
  });

  it('shows optional speaking corrections alongside the original recording without a proficiency score', async () => {
    const saved = session(); saved.components[4].attempt = { review_status: 'ready', outcome: 'practise_and_retry', feedback: 'Your plan is clear.', recording_url: '/private/original', production_feedback: { transcript: 'Я идти домой.', grammar: { score: 1, reason: 'Use the verb form for я.' }, fluency: { score: null, reason: 'The clip is too short to judge pace.' }, corrections: [{ original: 'Я идти', replacement: 'Я иду', explanation: 'Иду matches я.' }], uncertainty: ['One word was unclear.'] } };
    setup(url => response(url.endsWith('/assessment-pilot') ? overview() : saved));
    render(<AssessmentPilot sessionId="pilot-one" profileId="p" />); await chooseSkill('Speaking');
    const disclosure = screen.getByText('Speaking feedback').closest('details');
    expect(disclosure?.open).toBe(false);
    expect(screen.getByText('Я иду')).toBeTruthy();
    expect(screen.getByText('The transcript may contain recognition errors.')).toBeTruthy();
    expect(screen.getByLabelText('Your saved recording').getAttribute('src')).toBe('/private/original');
    expect(screen.queryByText(/Grammar score|Passed|Elo/)).toBeNull();
  });

});
