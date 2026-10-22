# fronted_e2e

Playwright tests for Fronted, kept apart from the app.

`@playwright/test` in TypeScript. A real Chromium, every spec twice: at phone
width (`phone`, Pixel 7) and on a PC (`desktop`, Desktop Chrome 1280×720),
against fronted's API and Vite, which Playwright starts on their own ports
(8010, 8011) with their own database (`fronted_e2e`, rebuilt every run).
Nothing is sent: mail and SMS keys are blanked for the servers.

## Run

```bash
npm test                          # all specs
npx playwright test -g settles    # by title
npx playwright test --project=desktop   # one device
npm run test:ui                   # Playwright's UI mode
npm run report                    # last HTML report; traces kept on failure
FRONTED_ROOT=/path/to/fronted npm test
```

## Needs

- A fronted checkout at `FRONTED_ROOT` (default `/Volumes/Data/src/fronted`)
  with `api/.venv` and `web/node_modules` installed.
- Postgres on `localhost:5432` (user `fronted`), as fronted itself needs.
- `npm install && npx playwright install chromium` here.
- Ports 8010 and 8011 free, or set `E2E_API_PORT` / `E2E_WEB_PORT`.

## Signing in

No spec goes through Google. After OAuth, all fronted keeps is a
`fronted_session` cookie holding a person id, signed with `SECRET_KEY`; it
does not record which provider it was. `seed.py cookie <person-id>` signs one
with the same key (read from fronted's `.env`, as the API under test does),
and the `signInAs` fixture puts it in the browser:

```ts
test('...', async ({ page, bill, signInAs }) => {
  await signInAs(bill.managerId)
  await page.goto(`/c/${bill.campaignToken}`)
})
```

Per test rather than a saved `storageState`, because the database is emptied
after every test and a saved session would name somebody who is gone. The
OAuth handshake itself is tested in fronted's API suite.

## Layout

```
playwright.config.ts   servers, phone + desktop projects, reporters
support/env.ts         paths, ports, the environment the servers get
support/fixtures.ts    seeded data, emptied database, console-error check
seed/seed.py           test data, written through fronted's own services
tests/pay.spec.ts      the public pay page, signed out
tests/manager.spec.ts  the manager's screens, signed in by cookie
```

Why the data is made in Python: going through fronted's services means a
test bill is split by the same rule as a real one and lands in the ledger the
way a real one does. `seed.py` refuses any database whose name lacks `e2e`,
because `reset` drops what it is pointed at.
