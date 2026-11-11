import { expect, test } from '@playwright/test'

test('visual cooking plan and settlements remain usable and preserve input after refresh', async ({ page }) => {
  let version = 1
  const cookId = '11111111-1111-4111-8111-111111111111'
  const userId = '22222222-2222-4222-8222-222222222222'
  const templateId = '33333333-3333-4333-8333-333333333333'
  const voteId = '44444444-4444-4444-8444-444444444444'
  const users = [{ id: userId, legacyId: 1, name: 'Тестовый участник', permanentSale: 1, enabled: true, contacts: [] }]
  let purchases = [{ id: '55555555-5555-4555-8555-555555555555', userId, userName: users[0].name, amount: 500, description: 'Продукты', mode: 'offset', repayments: [] }]
  let plan = {
    options: [{ key: 'tomato', name: 'Помидоры', values: ['С помидорами', 'Без помидоров'], batchSize: 1 }, { key: 'doneness', name: 'Прожарка', values: ['Medium', 'Well done'], batchSize: 5 }],
    groups: [{ userId, quantity: 1, choices: { tomato: 'Без помидоров', doneness: 'Medium' } }, { userId, quantity: 1, choices: { tomato: 'Без помидоров', doneness: 'Well done' } }],
  }
  await page.route('**/api/v1/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/v1/', '')
    let body: unknown = null
    if (path === 'auth/me') body = { id: 'admin', name: 'Администратор', username: 'admin', role: 'admin' }
    else if (path === 'users') body = users
    else if (path === 'templates') body = [{ id: templateId, name: 'Бургеры', isMultivote: true }]
    else if (path === `templates/${templateId}`) body = { id: templateId, name: 'Бургеры', isMultivote: true, voteVariants: [{ id: voteId, position: 0, name: 'Два бургера', value: 1 }], ingredients: [{ id: 'ingredient', position: 0, name: 'Ингредиенты', enabled: true }] }
    else if (path === `cooks/${cookId}/settlements`) {
      if (request.method() === 'PUT') { purchases = request.postDataJSON().purchases; version++ }
      body = { cookId, rowVersion: version, purchases }
    } else if (path === `cooks/${cookId}/preparation`) {
      if (request.method() === 'PUT') { const input = request.postDataJSON(); plan = { options: input.options, groups: input.groups }; version++ }
      body = { ...plan, rowVersion: version, warnings: [] }
    } else if (path === `cooks/${cookId}`) body = {
      id: cookId, cookDate: '2026-11-10', templateId, typeSnapshot: 'Бургеры', sale: 0.6, totalPrice: 300, calculationVersion: 1, rowVersion: version,
      voteVariants: [{ id: voteId, position: 0, name: 'Два бургера', value: 1 }],
      members: [{ id: 'member', position: 0, userId, userName: users[0].name, active: true, permanentSaleSnapshot: 1, cookVoteVariantIds: [voteId], voteWeight: 1, effectiveWeight: 1, charge: 300 }],
      productPrices: [{ id: 'product', position: 0, productName: 'Ингредиенты', expression: '300', computedValue: 300, calculationStatus: 'valid', calculationError: null, calculationVersion: 1 }],
    }
    else if (path === 'cooks') body = { items: [], page: 1, pageSize: 2, totalItems: 0, totalPages: 0, ordering: { fields: [] } }
    else if (path === 'cooks/preview') body = { totalPrice: 300, members: [{ userId, userName: users[0].name, charge: 300 }], calculationVersion: 1 }
    else if (path.includes('expression')) body = { expression: '300', status: 'valid', computedValue: 300, error: null, calculationVersion: 1 }
    await route.fulfill({ status: body ? 200 : 404, contentType: 'application/json', body: JSON.stringify(body ?? {}) })
  })
  await page.route('**/version', route => route.fulfill({ json: { component: 'backend', version: 'test', buildDate: '2026-11-11T00:00:00Z' } }))
  await page.goto(`/cooks/${cookId}`)
  await expect(page.getByRole('heading', { name: 'Купили за свои' })).toBeVisible()
  const preparation = page.getByRole('region', { name: 'План приготовления' })
  await expect(preparation.locator('.preparation__card')).toHaveCount(2)
  await expect(preparation.locator('.preparation__batch--warning')).toHaveCount(2)
  await preparation.scrollIntoViewIfNeeded()
  const captureStyle = '.app-header,.mobile-nav { visibility: hidden; }'
  await preparation.locator('.preparation__summary').screenshot({ path: test.info().outputPath('preparation.png'), style: captureStyle })
  const settlements = page.locator('.settlement-editor')
  await settlements.scrollIntoViewIfNeeded()
  await settlements.screenshot({ path: test.info().outputPath('settlements.png'), style: captureStyle })
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false)
  await page.getByLabel('Сумма, ₽', { exact: true }).fill('700')
  await page.reload()
  await expect(page.getByLabel('Сумма, ₽', { exact: true })).toHaveValue('700')
  await page.getByRole('button', { name: 'Сохранить взаиморасчёты', exact: true }).click()
  await expect(page.getByText('Взаиморасчёты сохранены.', { exact: true })).toBeVisible()
  await expect(page.getByText(/Сохранённая версия готовки изменилась/)).toHaveCount(0)
  await preparation.getByRole('spinbutton', { name: 'Количество' }).first().fill('5')
  await preparation.getByRole('button', { name: 'Сохранить пожелания' }).click()
  await expect(preparation.getByText('Пожелания сохранены.', { exact: true })).toBeVisible()
  await page.getByLabel('Выражение', { exact: true }).fill('301')
  await expect(page.getByRole('button', { name: 'Сохранить', exact: true })).toBeEnabled()
})
