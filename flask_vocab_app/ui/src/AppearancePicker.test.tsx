import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/preact';
import { AppearancePicker } from './AppearancePicker';

describe('Appearance picker', () => {
  it.each(['top', 'sidebar'] as const)('marks the current %s layout and submits a choice directly to the current route', layout => {
    window.history.replaceState(null, '', '/?source=library#flashcards?word_id=4');
    const {container} = render(<AppearancePicker language="en" navigationLayout={layout} csrfToken="test-token" />);
    const picker = container.querySelector('details')!;
    expect(picker.open).toBe(false);
    fireEvent.click(screen.getByLabelText('Appearance'));
    expect(picker.open).toBe(true);
    const form = container.querySelector('form')!;
    expect(form.getAttribute('action')).toBe('/ui-navigation');
    expect(form.getAttribute('method')).toBe('post');
    expect(form.querySelector<HTMLInputElement>('input[name="csrf_token"]')?.value).toBe('test-token');
    expect(form.querySelector<HTMLInputElement>('input[name="next"]')?.value).toBe('/?source=library#flashcards?word_id=4');
    const top = screen.getByRole('button', {name:'Top navigation'});
    const sidebar = screen.getByRole('button', {name:'Sidebar'});
    for (const [button, value] of [[top, 'top'], [sidebar, 'sidebar']] as const) {
      expect(button.getAttribute('name')).toBe('layout');
      expect(button.getAttribute('value')).toBe(value);
      expect(button.getAttribute('type')).toBe('submit');
      expect(button.getAttribute('aria-pressed')).toBe(String(layout === value));
      expect(button.querySelector('[aria-hidden="true"]')?.textContent).toBe(layout === value ? '✓' : '');
    }
    window.history.replaceState(null, '', '/?source=recent#review/session-12');
    fireEvent.submit(form);
    expect(new FormData(form).get('next')).toBe('/?source=recent#review/session-12');
    expect(container.querySelector('a[href="/appearance"]')).toBeNull();
    expect(screen.queryByRole('button', {name:/save/i})).toBeNull();
  });

  it('closes on outside click and returns focus to the icon on Escape', () => {
    const {container} = render(<><AppearancePicker language="en" navigationLayout="top" csrfToken="" /><button>Outside</button></>);
    const picker = container.querySelector('details')!;
    const summary = screen.getByLabelText('Appearance');
    fireEvent.click(summary);
    fireEvent.click(container.querySelector('form')!);
    expect(picker.open).toBe(true);
    fireEvent.click(screen.getByRole('button', {name:'Outside'}));
    expect(picker.open).toBe(false);
    fireEvent.click(summary);
    screen.getByRole('button', {name:'Sidebar'}).focus();
    fireEvent.keyDown(document.activeElement!, {key:'Escape'});
    expect(picker.open).toBe(false);
    expect(document.activeElement).toBe(summary);
  });

  it('localizes the icon and layout choices in Russian', () => {
    render(<AppearancePicker language="ru" navigationLayout="sidebar" csrfToken="" />);
    fireEvent.click(screen.getByLabelText('Внешний вид'));
    expect(screen.getByRole('button', {name:'Верхнее меню'})).toBeTruthy();
    expect(screen.getByRole('button', {name:'Боковая панель'}).getAttribute('aria-pressed')).toBe('true');
  });
});
