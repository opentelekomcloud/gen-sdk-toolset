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
    environment: 'node',
    include: ['src/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      /* Coverage gate currently scoped to framework-free logic modules.
         Widen as component tests (jsdom + testing-library) land. */
      include: [
        'src/features/scan/lib/**',
        'src/features/scan/api/client.ts',
        'src/features/scan/styles.ts',
        'src/features/scan/constants.ts',
      ],
      thresholds: { lines: 90, functions: 90, branches: 90, statements: 90 },
    },
  },
})
