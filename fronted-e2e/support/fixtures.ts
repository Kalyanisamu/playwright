/**
 * The fixtures every spec gets: seeded data, a way to be signed in, an
 * emptied database afterwards, and a failure on any console error.
 */
import { execFileSync } from 'node:child_process'

import { expect, test as base } from '@playwright/test'

import { BASE_URL, PYTHON, SEED, SEED_ENV } from './env'

function seed(...args: string[]): string {
  return execFileSync(PYTHON, [SEED, ...args], {
    env: SEED_ENV,
    encoding: 'utf8',
  })
}

/** What `seed.py bill` made, for the test to assert against. */
export type Bill = {
  managerId: string
  campaignToken: string
  obligationId: string
  payToken: string
  amountCents: number
  fronterName: string
  label: string
}

/**
 * Read a bill's status back from the database, in a process that shared
 * nothing with the request that changed it. That is what makes "it was
 * saved" a claim about the database rather than about a session.
 */
export function statusOf(bill: Bill): string {
  return (JSON.parse(seed('status', bill.obligationId)) as { status: string })
    .status
}

/** Cents to the string the app shows, formatted the way `lib/money.ts` does. */
export function money(cents: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
    .format(cents / 100)
}

type Fixtures = {
  bill: Bill
  /** Somebody signed in who is on no campaign at all. */
  stranger: { personId: string }
  /** Sign this browser in as a person. See `seed.py cookie` for how. */
  signInAs: (personId: string) => Promise<void>
  consoleErrors: string[]
  emptyDatabase: void
}

export const test = base.extend<Fixtures>({
  // eslint-disable-next-line no-empty-pattern
  bill: async ({}, use) => {
    await use(JSON.parse(seed('bill')) as Bill)
  },

  // eslint-disable-next-line no-empty-pattern
  stranger: async ({}, use) => {
    await use(JSON.parse(seed('stranger')) as { personId: string })
  },

  /**
   * Per test, not a saved storageState from a setup project — the usual
   * Playwright pattern, and the wrong one here. The database is emptied after
   * every test, so a session saved once would name a person who no longer
   * exists by the second test, and the screen would quietly be the sign-in
   * page. Signing a cookie costs one Python call.
   *
   * `url` rather than `domain` + `path`: on localhost the cookie must be
   * host-only, and a domain-scoped one is accepted by addCookies and then
   * silently never sent.
   */
  signInAs: async ({ context }, use) => {
    await use(async (personId) => {
      const value = seed('cookie', personId).trim()
      await context.addCookies([{ name: 'fronted_session', value, url: BASE_URL }])
    })
  },

  /**
   * Every console error and uncaught exception the page produced, asserted
   * empty after the test. A page that threw while rendering usually still
   * renders SOMETHING, and that something passes a text check. A test that
   * expects an error (a 404 logs one) removes it from this list itself.
   */
  consoleErrors: [
    async ({ page }, use) => {
      const errors: string[] = []
      page.on('console', (m) => {
        if (m.type() === 'error') errors.push(m.text())
      })
      page.on('pageerror', (e) => errors.push(e.message))
      await use(errors)
      expect(errors, 'console errors').toEqual([])
    },
    { auto: true },
  ],

  emptyDatabase: [
    // eslint-disable-next-line no-empty-pattern
    async ({}, use) => {
      await use()
      seed('truncate')
    },
    { auto: true },
  ],
})

export { expect }
