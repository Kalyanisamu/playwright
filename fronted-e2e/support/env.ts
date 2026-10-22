/**
 * Where the app under test is, and how its servers are told apart from yours.
 *
 * Its own ports, 8010 and 8011, not the 8000/8001 fronted pins. Those are
 * pinned for the OAuth callback, and nothing here signs in through a provider;
 * borrowing them would collide with a dev server, and a Vite that silently
 * proxied to somebody else's API would test their data, not ours.
 */
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export const HERE = resolve(fileURLToPath(new URL('..', import.meta.url)))

export const ROOT = resolve(process.env.FRONTED_ROOT ?? '/Volumes/Data/src/fronted')
export const API = resolve(ROOT, 'api')
export const WEB = resolve(ROOT, 'web')
/** fronted's venv: the seeder imports its models and services. */
export const PYTHON = resolve(API, '.venv/bin/python')
export const SEED = resolve(HERE, 'seed/seed.py')

export const API_PORT = Number(process.env.E2E_API_PORT ?? 8010)
export const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 8011)
export const BASE_URL = `http://localhost:${WEB_PORT}`

export const DATABASE_URL =
  process.env.E2E_DATABASE_URL ??
  'postgresql+psycopg://fronted:fronted@localhost:5432/fronted_e2e'

/** For the seeder, which reads these rather than fronted's .env. */
export const SEED_ENV = {
  ...process.env,
  FRONTED_ROOT: ROOT,
  E2E_DATABASE_URL: DATABASE_URL,
}

/**
 * For the API. Nothing leaves the machine: blank keys rather than trusting
 * the allowlists alone, because opening a campaign plans reminders and a .env
 * with real credentials in it is the normal state of a developer's laptop.
 */
export const SERVER_ENV = {
  ...SEED_ENV,
  DATABASE_URL,
  SITE_URL: `http://localhost:${API_PORT}`,
  WEB_URL: BASE_URL,
  DEBUG: 'true',
  RESEND_API_KEY: '',
  TWILIO_ACCOUNT_SID: '',
  TWILIO_AUTH_TOKEN: '',
  DEV_EMAIL_ALLOWLIST: '',
  DEV_SMS_ALLOWLIST: '',
  TURNSTILE_SITE_KEY: '',
  TURNSTILE_SECRET: '',
  MEDIA_BUCKET: '',
}
