/**
 * The manager's side, signed in without going through a provider.
 *
 * `signInAs` puts the session cookie fronted would have set after OAuth into
 * the browser (see `seed.py cookie`), so these start where a real manager is
 * once Google has handed them back. The first test is the control: without
 * the cookie the same screen is not reachable, so a pass below means the
 * cookie did it rather than the screen being open to anybody.
 */
import { expect, money, test } from '../support/fixtures'

test('signed out, the campaigns screen is not shown', async ({ page, bill }) => {
  await page.goto('/campaigns')

  await expect(page).not.toHaveURL(/\/campaigns$/)
  await expect(page.getByText(bill.label)).toHaveCount(0)
})

test('a signed-in manager sees their campaign in the list', async ({
  page,
  bill,
  signInAs,
}) => {
  await signInAs(bill.managerId)
  await page.goto('/campaigns')

  await expect(page.getByRole('heading', { name: 'Campaigns' })).toBeVisible()
  await expect(page.getByText(bill.label).first()).toBeVisible()
})

test('the manager can open the campaign and see who owes', async ({
  page,
  bill,
  signInAs,
}) => {
  await signInAs(bill.managerId)
  await page.goto(`/c/${bill.campaignToken}`)

  await expect(page.getByRole('heading', { level: 1, name: bill.label }))
    .toBeVisible()
  // By the row's name cell. Not bare text: each name also sits in a hidden
  // <option> in a picker above the grid, and that one matches first. Not the
  // email either: the phone layout drops that column.
  for (const name of ['Maria', 'Devi', 'Tomas']) {
    const row = page
      .getByRole('row')
      .filter({ has: page.getByRole('gridcell', { name, exact: true }) })
    await expect(row).toBeVisible()
    await expect(row).toContainText(money(bill.amountCents))
  }
})

test("somebody else's campaign is not found, not forbidden", async ({
  page,
  bill,
  stranger,
  signInAs,
  consoleErrors,
}) => {
  // Manager surfaces 404 rather than 403 for a stranger: whether a campaign
  // exists at a token is itself information. Signed in, so this is the
  // ownership check and not the sign-in check.
  await signInAs(stranger.personId)
  await page.goto(`/c/${bill.campaignToken}`)

  await expect(page.getByText(bill.label)).toHaveCount(0)
  await expect(page.getByText('Maria')).toHaveCount(0)
  // The browser logs the 404 itself; that one is expected.
  const others = consoleErrors.filter((e) => !e.includes('404'))
  consoleErrors.splice(0, consoleErrors.length, ...others)
})
