import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const API_PROXY_TARGET = 'http://127.0.0.1:8001'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Proxy API calls through Vite to avoid CORS and port clashes with other local apps on 8000.
    proxy: {
      '/api': API_PROXY_TARGET,
      '/health': API_PROXY_TARGET,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: true,
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
