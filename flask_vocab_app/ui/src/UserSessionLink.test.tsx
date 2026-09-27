import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/preact';
import { UserSessionLink, type UserProfile } from './UserSessionLink';

describe('User profile link', () => {
  it.each(['en','ru'] as const)('offers a visible %s sign-in link instead of the preview avatar', language => {
    render(<UserSessionLink profile={{id:'demo-preview',display_name:'Demo'}} language={language} accountMode="preview" signInAvailable />);
    const label=language==='ru' ? 'Войти' : 'Sign in';
    const link=screen.getByRole('link',{name:label});
    expect(link.textContent).toBe(label);
    expect(link.getAttribute('href')).toBe('/trial/account');
    expect(link.hasAttribute('data-user-session')).toBe(true);
    expect(link.getAttribute('data-profile-id')).toBe('demo-preview');
    expect(link.querySelector('.user-session-initial')).toBeNull();
  });
  it.each(['en','ru'] as const)('uses a truthful %s account link when preview sign-in is unavailable', language => {
    render(<UserSessionLink profile={{id:'demo-preview',display_name:'Demo'}} language={language} accountMode="preview" />);
    const label=language==='ru' ? 'Аккаунт' : 'Account';
    const link=screen.getByRole('link',{name:label});
    expect(link.textContent).toBe(label);
    expect(link.getAttribute('href')).toBe('/trial/account');
    expect(link.hasAttribute('data-user-session')).toBe(true);
    expect(screen.queryByRole('link',{name:/Sign in|Войти/})).toBeNull();
  });
  it.each(['en','ru'] as const)('offers direct %s demo entry without forcing sign-in', language => {
    render(<UserSessionLink profile={null} language={language} accountMode="preview" signInAvailable demoAvailable />);
    const label=language==='ru' ? 'Попробовать демо' : 'Try demo';
    expect(screen.getByRole('link',{name:label}).getAttribute('href')).toBe('/demo/');
    expect(screen.queryByRole('link',{name:/Sign in|Войти/})).toBeNull();
  });
  it.each(['en','ru'] as const)('identifies the active %s demo without implying a personal sign-in', language => {
    render(<UserSessionLink profile={{id:'guest',display_name:'Demo'}} language={language} accountMode="demo" signInAvailable demoAvailable />);
    const label=language==='ru' ? 'Демо-аккаунт' : 'Demo account';
    const link=screen.getByRole('link',{name:label});
    expect(link.textContent).toBe(label);
    expect(link.getAttribute('href')).toBe('/trial/account');
    expect(link.querySelector('.user-session-initial')).toBeNull();
  });
  it.each(['en','ru'] as const)('takes the hosted %s avatar directly to the account', language => {
    render(<UserSessionLink profile={{id:'hosted-personal',display_name:'Tom'}} language={language} accountMode="hosted" signInAvailable sessionScope="hosted:opaque-account" />);
    const link=screen.getByRole('link',{name:language==='ru' ? 'Аккаунт: Tom' : 'Account: Tom'});
    expect(link.getAttribute('href')).toBe('/trial/account');
    expect(link.hasAttribute('data-user-session')).toBe(true);
    expect(link.getAttribute('data-profile-id')).toBe('hosted-personal');
    expect(link.getAttribute('data-session-scope')).toBe('hosted:opaque-account');
    expect(link.textContent).toBe('T');
  });
  it('keeps local household selection separate from personal session monitoring', () => {
    render(<UserSessionLink profile={null} household />);
    const link=screen.getByRole('link',{name:'Household profiles'});
    expect(link.getAttribute('href')).toBe('/post/household');
    expect(link.hasAttribute('data-user-session')).toBe(false);
  });
  it.each([undefined, '   '])('keeps the profile picker usable when a response has no display name: %s', displayName => {
    const profile={id:'tom',display_name:displayName} as UserProfile;
    render(<UserSessionLink profile={profile} />);
    const link=screen.getByRole('link',{name:'Your profile'});
    expect(link.getAttribute('href')).toBe('/post/profiles');
    expect(link.getAttribute('data-profile-id')).toBe('tom');
    expect(link.textContent).toBe('●');
  });
});
