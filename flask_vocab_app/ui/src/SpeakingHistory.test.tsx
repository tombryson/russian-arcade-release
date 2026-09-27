import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/preact';
import { SpeakingHistory } from './SpeakingHistory';

const response = (value: unknown) => Promise.resolve({ok:true,json:async()=>value});
function openHistory() {
  const details = screen.getByText('Previous conversations').closest('details')!;
  details.open = true;
  fireEvent(details, new Event('toggle'));
  return details;
}
afterEach(() => vi.unstubAllGlobals());

describe('Speaking history', () => {
  it('loads all modes on demand, sorts by date and keeps speech tests in the lab', async () => {
    const fetch = vi.fn((url: string) => response({sessions:url.includes('step-conversations') ? [{id:'guided',created_at:250,title:'At the station'}] : url.includes('live-conversations')
      ? [{id:'recent',created_at:300},{id:'older',created_at:100}]
      : [{id:'recorded',mode:'conversation',created_at:200},{id:'lab',mode:'lab',created_at:400}]}));
    vi.stubGlobal('fetch',fetch);
    render(<SpeakingHistory language="en" />);
    expect(fetch).not.toHaveBeenCalled();
    openHistory();
    await screen.findByText(/Recorded practice/);
    expect(screen.getAllByRole('link').map(link => link.getAttribute('href'))).toEqual([
      '#speaking/recent', '#speaking/step/guided', '#speaking/recorded/recorded', '#speaking/older',
    ]);
    expect(fetch).toHaveBeenCalledTimes(3);
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/live-conversations/options', '/api/v1/conversations/options', '/api/v1/step-conversations/history',
    ]);
  });
  it('retains available history on a partial failure and can retry', async () => {
    let fail = true;
    vi.stubGlobal('fetch',vi.fn((url: string) => url.includes('/conversations/') && fail
      ? Promise.reject(new Error('Unavailable')) : response({sessions:url.includes('step-conversations') ? [] : [{id:url.includes('live-')?'live':'old',mode:'conversation',created_at:100}]})));
    render(<SpeakingHistory language="en" />);
    openHistory();
    await screen.findByText('Some conversations could not load.');
    expect(screen.getAllByRole('link')).toHaveLength(1);
    fail = false;
    fireEvent.click(screen.getByRole('button',{name:'Try again'}));
    await screen.findByText(/Recorded practice/);
    expect(screen.getAllByRole('link')).toHaveLength(2);
    expect(screen.queryByText('Some conversations could not load.')).toBeNull();
  });
  it('refreshes on reopening, so deleted sessions do not linger', async () => {
    let sessions = [{id:'live',created_at:100}];
    vi.stubGlobal('fetch',vi.fn((url: string) => response({sessions:url.includes('live-')?sessions:[]})));
    render(<SpeakingHistory language="en" />);
    const details = openHistory();
    await screen.findByRole('link');
    details.open = false;fireEvent(details,new Event('toggle'));
    sessions = [];
    details.open = true;fireEvent(details,new Event('toggle'));
    await screen.findByText('Your conversations will appear here.');
    expect(screen.queryByRole('link')).toBeNull();
  });
  it('shows the saved scenario title while preserving older café labels',async()=>{
    vi.stubGlobal('fetch',vi.fn((url:string)=>response({sessions:url.includes('live-') ? [{id:'seeded',created_at:200,title:'Time to warm up',title_ru:'Пора согреться'},{id:'old',created_at:100}] : []})));
    render(<SpeakingHistory language="en" />);openHistory();
    expect(await screen.findByRole('link',{name:/Time to warm up/})).toBeTruthy();
    expect(screen.getByRole('link',{name:/At the café/})).toBeTruthy();
  });
});
