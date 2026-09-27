import { readFileSync, writeFileSync } from 'node:fs';

const root = new URL('../src/styles/', import.meta.url);
const tokens = JSON.parse(readFileSync(new URL('tokens.json', root), 'utf8'));
const properties = (values) => Object.entries(values)
  .map(([key, value]) => `  --wp-${key.replaceAll('.', '-')}: ${value};`).join('\n');
const theme = (name) => properties(tokens.themes[name]);
const fontStack = (values) => values.map(value => ['system-ui', 'sans-serif', 'serif', 'monospace'].includes(value) ? value : JSON.stringify(value)).join(', ');
const shared = {
  ...tokens.shared,
  'font.display': fontStack(tokens.font.display),
  'font.reading': fontStack(tokens.font.reading),
  'target': `${tokens.interaction.childTargetMinPx}px`,
  'motion': `${tokens.interaction.smallMotionMs}ms`,
};
writeFileSync(new URL('tokens.generated.css', root), `/* Generated from tokens.json by npm run tokens. */
:root {\n${properties(shared)}\n${theme('light')}\n  color-scheme: light;\n}
@media (prefers-color-scheme: dark) { :root {\n${theme('dark')}\n  color-scheme: dark;\n} }
[data-theme="light"] {\n${theme('light')}\n  color-scheme: light;\n}
[data-theme="dark"] {\n${theme('dark')}\n  color-scheme: dark;\n}
@media (prefers-reduced-motion: reduce) { :root { --wp-motion: 0ms; } }
`);
