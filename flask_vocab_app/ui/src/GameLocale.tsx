import {createContext} from 'preact';
import {useContext} from 'preact/hooks';
import type {Language} from './review-types';
import {gameRussian} from './game-copy';

export const GameLanguage = createContext<Language>('en');
export const GameMedia = createContext(true);
export function useGameLanguage() { return useContext(GameLanguage); }
export function useGameText() {
  const language = useGameLanguage();
  return (text: string, values: Record<string, string | number> = {}) => {
    const copy = language === 'ru' ? gameRussian[text] ?? text : text;
    return copy.replace(/\{(\w+)\}/g, (match, key) => String(values[key] ?? match));
  };
}
