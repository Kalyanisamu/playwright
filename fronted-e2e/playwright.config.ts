/**
 * A real Chromium, at phone and at desktop width, against fronted's API and Vite started on
 * their own ports with their own database.
 *
 * Both servers refuse to start if their port is taken (`reuseExistingServer:
 * false`, Vite's --strictPort): attaching to whatever already answers there
 * would test somebody else's checkout.
 */
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'

import { defineConfig, devices } from '@playwright/test'

import {
  API, API_PORT, BASE_URL, PYTHON, SEED, SERVER_ENV, WEB, WEB_PORT,
} from './support/env'

for (const needed of [PYTHON, resolve(WEB, 'node_modules/.bin/vite')]) {
  if (!existsSync(needed)) {
    throw new Error(
      `${needed} is missing. Point FRONTED_ROOT at a fronted checkout ` +
        'with api/.venv and web/node_modules installed.',
    )
  }
}

export default defineConfig({
  testDir: './tests',
  // One database, emptied after every test, so one test at a time.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  // Every spec runs on both. The pay link is mostly opened from an email on a
  // phone, but the manager who sends it works at a desk, and a layout fixed
  // for one width is easily broken at the other.
  projects: [
    { name: 'phone', use: { ...devices['Pixel 7'] } },
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: [
    {
      // The database is rebuilt as the API starts, not in globalSetup:
      // Playwright starts web servers BEFORE global setup, and /_health
      // checks Postgres, so the database has to exist first.
      command:
        `"${PYTHON}" "${SEED}" reset && ` +
        `"${API}/.venv/bin/uvicorn" app.main:app --port ${API_PORT}`,
      cwd: API,
      env: SERVER_ENV,
      url: `http://localhost:${API_PORT}/_health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `"${WEB}/node_modules/.bin/vite" --port ${WEB_PORT} --strictPort`,
      cwd: WEB,
      env: { ...process.env, API_PORT: String(API_PORT) } as Record<string, string>,
      url: BASE_URL,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
})
