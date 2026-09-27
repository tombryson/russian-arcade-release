import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/preact';
vi.mock('../../static/js/preact_deps.js', async () => ({...await import('preact'),...await import('preact/hooks')}));
import { VocabTable } from '../../static/js/VocabTable.js';
import { Flashcards } from './Flashcards';

const words = [
 {id:1,lemma:'ёж',pos:'NOUN',topic:['animals'],lemma_difficulty:2,mnemonic:'A memory hint',date_added:'2025-07-27',count:9,anki_exports:9,native_count:2,native_total:3,form_count:2,forms_search:'ежами,ежах'},
 {id:2,lemma:'вместе',pos:'ADVB',topic:['daily_activities'],lemma_difficulty:3,mnemonic:'Together',date_added:'2025-07-28',count:0,anki_exports:0,native_count:0,native_total:0,form_count:0,forms_search:''},
];
beforeEach(() => {
 document.documentElement.lang='en';
 window.history.replaceState(null,'','/vocab');
 vi.stubGlobal('fetch',vi.fn().mockImplementation(async url => ({ok:true,json:async () => String(url).startsWith('/vocab/words/') ? {forms:[{id:11,form:'ежами',tags:{case:'ablt',number:'plur'},native_count:2}]} : {words}})));
});
afterEach(() => { vi.unstubAllGlobals(); document.documentElement.lang='en'; });
it('finds inflected forms and treats Russian case, stress and ё consistently',async () => {
 render(<VocabTable />);
 await screen.findByRole('button',{name:'ёж'});
 fireEvent.input(screen.getByRole('searchbox'),{target:{value:'ЕЖА́МИ'}});
 expect(screen.getByRole('button',{name:'ёж'})).toBeTruthy();
 expect(screen.queryByRole('button',{name:'вместе'})).toBeNull();
 fireEvent.input(screen.getByRole('searchbox'),{target:{value:'ЕЖ'}});
 expect(screen.getByRole('button',{name:'ёж'})).toBeTruthy();
});
it('uses real POS codes and keeps filters separate from the word rows',async () => {
 render(<VocabTable />);
 await screen.findByRole('button',{name:'вместе'});
 fireEvent.click(screen.getByText('Filter words'));
 fireEvent.change(screen.getByLabelText('Part of speech'),{target:{value:'ADVB'}});
 expect(screen.getByRole('button',{name:'вместе'})).toBeTruthy();
 expect(screen.queryByRole('button',{name:'ёж'})).toBeNull();
 expect(screen.getAllByText('Adverb').length).toBeGreaterThan(0);
});
it('shows current native counts, labels export history and opens exact form details',async () => {
 render(<VocabTable />);
 const word = await screen.findByRole('button',{name:'ёж'});
 expect(screen.getByRole('link',{name:'ёж: 2 in-app cards'}).getAttribute('href')).toBe('/#flashcards?word_id=1');
 expect(screen.getByText('Anki exports: 9')).toBeTruthy();
 expect(screen.queryByText('A memory hint')).toBeNull();
 fireEvent.click(word);
 expect(screen.getByText('A memory hint')).toBeTruthy();
 expect(screen.getByRole('link',{name:'Make flashcards →'}).getAttribute('href')).toBe('/#generate?word_id=1');
 await screen.findByText('Word forms · 1');
 expect(fetch).toHaveBeenCalledWith('/vocab/words/1',expect.objectContaining({signal:expect.anything()}));
 fireEvent.click(screen.getByText('Word forms · 1'));
 expect(screen.getByText('Instrumental · Plural')).toBeTruthy();
});
it('makes native card coverage filterable without treating Anki exports as native cards',async () => {
 render(<VocabTable />);
 await screen.findByRole('button',{name:'ёж'});
 fireEvent.click(screen.getByText('Filter words'));
 fireEvent.change(screen.getByLabelText('In-app cards'),{target:{value:'without'}});
 expect(screen.queryByRole('button',{name:'ёж'})).toBeNull();
 expect(screen.getByRole('button',{name:'вместе'})).toBeTruthy();
});
it('keeps Russian labels and readable topic names',async () => {
 document.documentElement.lang='ru';
 render(<VocabTable />);
 await screen.findByRole('button',{name:'ёж'});
 expect(within(screen.getByRole('table')).getByText('Животные')).toBeTruthy();
 expect(within(screen.getByRole('table')).getByText('Повседневная жизнь')).toBeTruthy();
 expect(screen.getByRole('searchbox',{name:'Найти слово или его форму'})).toBeTruthy();
});
it('passes the selected word into the card browser and retains it when applying filters',async () => {
 fetch.mockResolvedValue({ok:true,json:async () => ({profile_id:'p',scope:{word_id:'1'},server_now:0,active_session_id:null,
  counts:{cards:0,words:0,ready:0,new:0,due:0,new_allowance:5,practised_today:0},facets:{decks:[],topics:[],pos:[],cases:[]},cards:[]})});
 render(<Flashcards profileId="p" personal wordId={1} />);
 await screen.findByRole('heading',{name:/Your cards/});
 expect(fetch.mock.calls[0][0]).toBe('/api/v1/flashcards?word_id=1');
 fireEvent.click(screen.getByRole('button',{name:/^Filters/}));
 expect(document.querySelector('input[name="word_id"]').value).toBe('1');
 fireEvent.click(screen.getByRole('button',{name:'Show all cards'}));
 await waitFor(() => expect(fetch.mock.calls.at(-1)[0]).toBe('/api/v1/flashcards'));
});
