import react from '@vitejs/plugin-react'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'
import { createApiProxy, defaultDevApiTarget } from './devProxy'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [react()],
    server: {
      host: '127.0.0.1',
      port: 5173,
      proxy: createApiProxy(env.DEV_API_PROXY_TARGET || defaultDevApiTarget),
    },
    preview: {
      host: '127.0.0.1',
      port: 4173,
    },
    test: {
      environment: 'jsdom',
      setupFiles: './tests/setup.ts',
      include: ['tests/**/*.test.{ts,tsx}'],
      css: true,
    },
  }
})
