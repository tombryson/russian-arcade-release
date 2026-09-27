import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {beforeEach, describe, expect, it} from 'vitest';

const script = readFileSync('../static/js/curriculum.js', 'utf8');
const markup = `<form data-curriculum-setup>
  <select data-curriculum-topic><option value="any">Any</option><option value="food" data-level="A1">Food</option><option value="law" data-level="C1">Law</option><option value="grammar">Grammar</option></select>
  <select data-curriculum-level><option>A1</option><option>A2</option><option>C1</option><option>C2</option></select>
</form>`;
const change = (selector, value) => {
  const element = document.querySelector(selector);
  element.value = value;
  element.dispatchEvent(new Event('change', {bubbles:true}));
};

describe('Curriculum topic and level selection', () => {
  beforeEach(() => {
    document.body.innerHTML = markup;
    runInNewContext(script, {document, Symbol, Element});
  });
  it('suggests the primary course level until the learner selects a different one', () => {
    change('[data-curriculum-topic]', 'law');
    expect(document.querySelector('[data-curriculum-level]').value).toBe('C1');
    change('[data-curriculum-level]', 'C2');
    change('[data-curriculum-topic]', 'food');
    expect(document.querySelector('[data-curriculum-level]').value).toBe('C2');
  });
  it('preserves the level explicitly selected by a curriculum deep link', () => {
    document.querySelector('form').dataset.levelExplicit = 'true';
    document.querySelector('[data-curriculum-level]').value = 'C2';
    change('[data-curriculum-topic]', 'law');
    expect(document.querySelector('[data-curriculum-level]').value).toBe('C2');
  });
  it('supports numeric Translation storage and leaves cross-topic grammar unchanged', () => {
    document.querySelector('[data-curriculum-level]').innerHTML = '<option value="1" data-level="A1">A1</option><option value="5" data-level="C1">C1</option>';
    change('[data-curriculum-topic]', 'law');
    expect(document.querySelector('[data-curriculum-level]').value).toBe('5');
    change('[data-curriculum-topic]', 'grammar');
    expect(document.querySelector('[data-curriculum-level]').value).toBe('5');
  });
  it('works after an HTMX form replacement and repeated script evaluation', () => {
    change('[data-curriculum-level]', 'C2');
    document.body.innerHTML = markup;
    runInNewContext(script, {document, Symbol, Element});
    change('[data-curriculum-topic]', 'law');
    expect(document.querySelector('[data-curriculum-level]').value).toBe('C1');
  });
});
