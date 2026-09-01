/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { mockScanApi } from './mock/scanApi.ts'

const backend = process.env.BACKEND_URL || 'http://127.0.0.1:8000'

export default defineConfig({
  /* MOCK_API=1 serves /api/scan/* from fixtures — the backend has no scan routes yet */
  plugins: [react(), tailwindcss(), ...(process.env.MOCK_API ? [mockScanApi()] : [])],
  server: {
    proxy: {
      '/api': backend,
      '/health': backend,
    },
  },
  test: {
    /* jsdom, not node: the role-aware controls are only testable by rendering
       them, and a DOM for the handful of logic suites costs nothing. */
    environment: 'jsdom',
    setupFiles: ['src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      /* The gate stays scoped to framework-free logic modules even though
         component tests exist now: widening it would pull in every component
         that has none, and the only way to keep the threshold green would be to
         lower it. Rendering tests earn their keep by asserting behaviour, not
         by moving this number. */
      include: [
        'src/features/scan/lib/**',
        'src/features/scan/api/client.ts',
        'src/shared/auth/roles.ts',
        'src/shared/auth/session.ts',
        'src/features/scan/styles.ts',
        'src/features/scan/constants.ts',
      ],
      thresholds: { lines: 90, functions: 90, branches: 90, statements: 90 },
    },
  },
})
