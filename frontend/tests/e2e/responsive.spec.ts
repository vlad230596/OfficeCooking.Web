import { expect, test } from '@playwright/test'

test('navigation and four routes remain usable at the configured viewport', async ({ page }) => {
  await page.route('**/api/v1/**', route => route.fulfill({
    status: route.request().url().endsWith('/auth/me') ? 200 : 503,
    contentType: 'application/json',
    body: route.request().url().endsWith('/auth/me')
      ? JSON.stringify({ id: '11111111-1111-4111-8111-111111111111', name: 'Admin', username: 'admin', role: 'admin' })
      : JSON.stringify({ code: 'e2e_offline', message: 'Backend is intentionally offline in this UI smoke test.' }),
  }))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Балансы' })).toBeVisible()

  const navigationName = test.info().project.name.startsWith('mobile')
    ? 'Мобильная навигация'
    : 'Основная навигация'
  const navigation = page.getByRole('navigation', { name: navigationName })
  await expect(navigation).toBeVisible()

  await navigation.getByRole('link', { name: /Новая/ }).click()
  await expect(page.getByRole('heading', { name: 'Новая готовка' })).toBeVisible()
  await navigation.getByRole('link', { name: 'Готовки', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Готовки' })).toBeVisible()
  await navigation.getByRole('link', { name: /Справочники|Данные/ }).click()
  await expect(page.getByRole('heading', { name: 'Справочники' })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Блюда' })).toBeVisible()
  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  )
  expect(hasHorizontalOverflow).toBe(false)
})
