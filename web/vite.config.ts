import { defineConfig } from 'vite';

export default defineConfig({
  base: '/workbench/',
  server: {
    proxy: Object.fromEntries(['/identity', '/operations', '/audit-events', '/runs', '/threads', '/traces', '/experiences', '/evaluations', '/evaluation-comparison', '/recordings', '/scenarios', '/run-comparison'].map(
      path => [path, 'http://127.0.0.1:8000'],
    )),
  },
});
