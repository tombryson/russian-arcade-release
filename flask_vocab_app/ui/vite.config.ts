import { defineConfig } from 'vitest/config';
import preact from '@preact/preset-vite';

export default defineConfig({
  plugins: [preact()],
  base: '/post/',
  build: {
    outDir: 'dist',
    manifest: true,
    assetsInlineLimit: 0,
    sourcemap: false,
    rolldownOptions: { input: ['src/main.tsx', 'src/legacy.ts'] },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['src/test-setup.ts'],
    clearMocks: true,
  },
});
