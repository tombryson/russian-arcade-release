import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/preact';
import { ActivitiesMenu } from './ActivitiesMenu';

const items = [
  {page:'native_flashcards', href:'/#flashcards', label:'Flashcards', boost:false},
  {page:'comprehension', href:'/comprehension', label:'Comprehension', boost:true},
  {page:'speaking', href:'/#speaking', label:'Speaking', boost:false},
  {page:'writing', href:'/writing', label:'Writing', boost:true},
  {page:'lessons', href:'/lessons', label:'Lessons', boost:true},
  {page:'word_jumble', href:'/word_jumble', label:'Word Jumble', boost:true},
  {page:'sentences', href:'/sentences', label:'Translate a sentence', boost:true},
];

describe('Top Activities menu', () => {
  it('opens in place and lists each activity before the All activities destination', () => {
    window.history.replaceState(null, '', '/#home');
    const {container} = render(<ActivitiesMenu items={items} language="en" active={false} activePage="home" />);
    expect(container.querySelector('details')!.open).toBe(false);
    fireEvent.click(screen.getByLabelText('Activities'));
    expect(window.location.hash).toBe('#home');
    const links = within(container.querySelector('.activities-menu-options')!).getAllByRole('link');
    expect(links.map(link => link.textContent?.replace('↗', '').trim())).toEqual([...items.map(item => item.label), 'Games', 'All activities']);
    expect(links.map(link => link.getAttribute('href'))).toEqual(['#flashcards','/comprehension','#speaking','/writing','/lessons','/word_jumble','/sentences','#games','#activities']);
    expect(links.every(link => !link.hasAttribute('aria-current'))).toBe(true);
  });

  it('closes after a selection, including selecting the current activity', () => {
    const {container} = render(<ActivitiesMenu items={items} language="en" active activePage="speaking" />);
    container.addEventListener('click', event => { if ((event.target as Element).closest('a')) event.preventDefault(); });
    const menu = container.querySelector('details')!;
    fireEvent.click(screen.getByLabelText('Activities'));
    const speaking = screen.getByRole('link', {name:'Speaking'});
    expect(speaking.getAttribute('aria-current')).toBe('page');
    fireEvent.click(speaking);
    expect(menu.open).toBe(false);
    fireEvent.click(screen.getByLabelText('Activities'));
    fireEvent.click(screen.getByRole('link', {name:'All activities'}));
    expect(menu.open).toBe(false);
  });

  it('supports Escape with focus return, outside clicks and route changes', () => {
    const {container} = render(<><ActivitiesMenu items={items} language="en" active activePage="activities" /><button>Outside</button></>);
    const trigger = screen.getByLabelText('Activities');
    const menu = container.querySelector('details')!;
    fireEvent.click(trigger);
    screen.getByRole('link', {name:'Flashcards'}).focus();
    fireEvent.keyDown(document.activeElement!, {key:'Escape'});
    expect(menu.open).toBe(false);
    expect(document.activeElement).toBe(trigger);
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole('button', {name:'Outside'}));
    expect(menu.open).toBe(false);
    fireEvent.click(trigger);
    fireEvent(window, new HashChangeEvent('hashchange'));
    expect(menu.open).toBe(false);
  });

  it('localizes the trigger and footer and keeps the active activity identifiable', () => {
    render(<ActivitiesMenu items={[{...items[2], label:'Разговорная практика'}]} language="ru" active activePage="games" />);
    const trigger = screen.getByLabelText('Занятия');
    expect(trigger.getAttribute('data-active')).toBe('true');
    fireEvent.click(trigger);
    expect(screen.getByRole('link', {name:'Игры'}).getAttribute('aria-current')).toBe('page');
    expect(screen.getByRole('link', {name:'Игры'}).getAttribute('href')).toBe('#games');
    expect(screen.getByRole('link', {name:'Все занятия'}).getAttribute('href')).toBe('#activities');
  });
});
