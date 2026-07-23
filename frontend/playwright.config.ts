import { defineConfig, devices } from '@playwright/test'

const LOCAL_APP_URL = 'http://127.0.0.1:4173'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  use: {
    baseURL: LOCAL_APP_URL,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command:
      'VITE_API_BASE_URL=http://127.0.0.1:4173 ./node_modules/.bin/vite --host 127.0.0.1 --port 4173',
    url: LOCAL_APP_URL,
    reuseExistingServer: true,
  },
})
