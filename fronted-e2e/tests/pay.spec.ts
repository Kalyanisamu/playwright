/**
 * The pay page, as a stranger gets it from an email — on a phone or a PC.
 *
 * This is the highest-traffic screen and the only one most people ever see.
 * fronted's API suite already covers what the endpoint returns; these cover
 * what only a real browser and separate processes can show — that the page
 * lays out at both widths, and that tapping a button leaves something behind
 * in the database once the request is over.
 */
import { expect, money, statusOf, test } from '../support/fixtures'

test('a stranger sees what they owe and to whom', async ({ page, bill }) => {
  await page.goto(`/pay/${bill.payToken}`)

  await expect(page.getByText(`You owe ${bill.fronterName}`)).toBeVisible()
  await expect(page.getByText(money(bill.amountCents))).toBeVisible()
  await expect(page.getByText(`for ${bill.label}`)).toBeVisible()
  await expect(page.getByRole('button', { name: "I've sent it" })).toBeVisible()
})

test('the page does not scroll sideways', async ({ page, bill }) => {
  // A layout fact, so only a browser can catch it: jsdom never lays out.
  await page.goto(`/pay/${bill.payToken}`)
  await expect(page.getByText(`You owe ${bill.fronterName}`)).toBeVisible()

  const overflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  )
  expect(overflow, `the page is ${overflow}px wider than the screen`)
    .toBeLessThanOrEqual(0)
})

test('saying it was sent settles it, and it stays settled', async ({
  page,
  bill,
}) => {
  // The write has to outlive the request. fronted's API tests cannot show
  // this: their requests share one session, so a flushed-but-uncommitted row
  // is still visible to the next call. Here the reload is a new request, and
  // the database is read from another process altogether.
  await page.goto(`/pay/${bill.payToken}`)
  await page.getByRole('button', { name: "I've sent it" }).click()

  await expect(page.getByText('Settled. Nothing more to do.')).toBeVisible()
  expect(statusOf(bill)).toBe('paid')

  await page.reload()
  await expect(page.getByText(`Settled with ${bill.fronterName}`)).toBeVisible()
})

test('taking it back reopens the bill', async ({ page, bill }) => {
  await page.goto(`/pay/${bill.payToken}`)
  await page.getByRole('button', { name: "I've sent it" }).click()
  await page.getByRole('button', { name: /Didn't mean to/ }).click()

  await expect(page.getByRole('button', { name: "I've sent it" })).toBeVisible()
  expect(statusOf(bill)).toBe('open')

  await page.reload()
  await expect(page.getByText(`You owe ${bill.fronterName}`)).toBeVisible()
})

test('the link from an old email still lands', async ({ page, bill }) => {
  // `/p/` is what the Django app mailed, and a link in an email is forever.
  await page.goto(`/p/${bill.payToken}`)

  await expect(page).toHaveURL(new RegExp(`/pay/${bill.payToken}$`))
  await expect(page.getByText(`You owe ${bill.fronterName}`)).toBeVisible()
})

test('a dead link says so', async ({ page, consoleErrors }) => {
  await page.goto('/pay/not-a-real-token')

  await expect(page.getByText('This link does not work')).toBeVisible()
  // The browser logs the 404 itself; that one is expected.
  const others = consoleErrors.filter((e) => !e.includes('404'))
  consoleErrors.splice(0, consoleErrors.length, ...others)
})
