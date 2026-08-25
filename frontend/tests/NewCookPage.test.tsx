import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../src/api'
import type { CookDetail, TemplateDetail, User } from '../src/api'
import * as api from '../src/api/officeCookApi'
import { NewCookPage } from '../src/pages/NewCookPage'

vi.mock('../src/api/officeCookApi')

const users: User[] = [
  { id: 'user-1', legacyId: 1, name: 'Алиса', permanentSale: 1, enabled: true, contacts: [] },
  { id: 'user-2', legacyId: 2, name: 'Борис', permanentSale: 1, enabled: true, contacts: [] },
]
const template: TemplateDetail = {
  id: 'template-1',
  name: 'Купаты',
  isMultivote: false,
  voteVariants: [
    { id: 'vote-1', position: 0, name: 'Много', value: 1.5 },
    { id: 'vote-2', position: 1, name: 'Немного', value: 1 },
  ],
  ingredients: [
    { id: 'ingredient-1', position: 0, name: 'Купаты', enabled: true },
    { id: 'ingredient-2', position: 1, name: 'Старый соус', enabled: false },
  ],
}
const cook: CookDetail = {
  id: 'cook-1', cookDate: '2026-08-18', templateId: 'template-1', typeSnapshot: 'Купаты', sale: 0.6,
  totalPrice: 200, calculationVersion: 1, rowVersion: 7,
  voteVariants: [
    { id: 'snapshot-vote-1', position: 0, name: 'Много', value: 1.5 },
    { id: 'snapshot-vote-2', position: 1, name: 'Немного', value: 1 },
  ],
  members: [{
    id: 'member-1', position: 0, userId: 'user-1', userName: 'Алиса', active: true,
    permanentSaleSnapshot: 1,
    cookVoteVariantIds: ['snapshot-vote-1'], voteWeight: 1.5, effectiveWeight: 0.9, charge: 200,
  }],
  productPrices: [{
    id: 'product-1', position: 0, productName: 'Купаты', expression: '2*100', computedValue: 200,
    calculationStatus: 'valid', calculationError: null, calculationVersion: 1,
  }],
}

function renderPage(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/cooks/new" element={<NewCookPage />} />
          <Route path="/cooks/:cookId" element={<NewCookPage />} />
          <Route path="/cooks" element={<div>Список готовок</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.mocked(api.listUsers).mockResolvedValue(users)
  vi.mocked(api.listTemplates).mockResolvedValue([{ id: template.id, name: template.name, isMultivote: false }])
  vi.mocked(api.getTemplate).mockResolvedValue(template)
  vi.mocked(api.getCook).mockResolvedValue(cook)
  vi.mocked(api.previewExpression).mockImplementation(async ({ expression }) => ({
    expression: expression ?? null,
    status: expression ? 'valid' : 'empty',
    computedValue: expression === '2*100' ? 200 : 0,
    error: null,
    calculationVersion: 1,
  }))
  vi.mocked(api.previewCook).mockImplementation(async (request) => ({
    totalPrice: request.productPrices.some(item => item.expression === '2*100') ? 200 : 0,
    members: request.members.map(member => ({
      userId: member.userId,
      userName: users.find(user => user.id === member.userId)?.name ?? member.userId,
      charge: member.userId === 'user-1' ? 125 : 75,
    })),
    calculationVersion: 1,
  }))
  vi.mocked(api.createCook).mockResolvedValue(cook)
  vi.mocked(api.updateCook).mockResolvedValue(cook)
})

describe('NewCookPage', () => {
  it('uses dish ingredients as an editable starting point and permits multiple votes', async () => {
    renderPage('/cooks/new')
    expect(await screen.findByDisplayValue('Старый соус')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Новая готовка' })).toBeInTheDocument()
    expect(screen.getByText('Отключён в блюде, сохранён для Legacy')).toBeInTheDocument()

    const alice = screen.getByRole('group', { name: 'Алиса' })
    fireEvent.click(within(alice).getByRole('checkbox', { name: 'Много' }))
    fireEvent.click(within(alice).getByRole('checkbox', { name: 'Немного' }))
    const expense = screen.getAllByRole('textbox', { name: 'Выражение' })[0]
    fireEvent.change(expense, { target: { value: '2*100' } })
    fireEvent.click(screen.getByRole('button', { name: 'Удалить расход Старый соус' }))
    fireEvent.click(screen.getByRole('button', { name: /Добавить строку/ }))
    const names = screen.getAllByRole('textbox', { name: 'Название расхода' })
    fireEvent.change(names[1], { target: { value: 'Доставка' } })

    await waitFor(() => expect(api.previewExpression).toHaveBeenCalledWith(
      { expression: '2*100' }, expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))
    await waitFor(() => expect(within(alice).getByText('125')).toBeInTheDocument())
    const submit = await screen.findByRole('button', { name: 'Сохранить готовку' })
    await waitFor(() => expect(submit).toBeEnabled())
    fireEvent.click(submit)

    await waitFor(() => expect(api.createCook).toHaveBeenCalledOnce())
    expect(vi.mocked(api.createCook).mock.calls[0][0]).toMatchObject({
      templateId: 'template-1',
      members: [{ position: 0, userId: 'user-1', active: false, voteVariantPositions: [0, 1] }],
      productPrices: [
        { position: 0, productName: 'Купаты', expression: '2*100' },
        { position: 1, productName: 'Доставка', expression: '' },
      ],
    })
    expect(screen.getByText('Список готовок')).toBeInTheDocument()
  })

  it('preserves snapshot ids and expectedVersion during edit', async () => {
    renderPage('/cooks/cook-1')
    expect(await screen.findByRole('heading', { name: 'Редактирование готовки' })).toBeInTheDocument()
    expect(await screen.findByText(/Сохранённая общая сумма: 200/)).toBeInTheDocument()
    const submit = await screen.findByRole('button', { name: 'Сохранить готовку' })
    await waitFor(() => expect(submit).toBeEnabled())
    fireEvent.click(submit)
    await waitFor(() => expect(api.updateCook).toHaveBeenCalledOnce())
    expect(vi.mocked(api.updateCook).mock.calls[0]).toEqual([
      'cook-1',
      {
        expectedVersion: 7,
        cookDate: '2026-08-18',
        voteVariants: cook.voteVariants,
        members: [{
          id: 'member-1', position: 0, userId: 'user-1', active: true,
          cookVoteVariantIds: ['snapshot-vote-1'],
        }],
        productPrices: [{
          id: 'product-1', position: 0, productName: 'Купаты', expression: '2*100',
        }],
      },
    ])
  })

  it('shows a structured version-conflict message', async () => {
    vi.mocked(api.updateCook).mockRejectedValue(new ApiError('Version conflict', 409, {
      error: {
        code: 'version_conflict', message: 'Version conflict', fieldErrors: [],
        details: { currentVersion: 8 }, requestId: 'request-8',
      },
    }))
    renderPage('/cooks/cook-1')
    const submit = await screen.findByRole('button', { name: 'Сохранить готовку' })
    await waitFor(() => expect(submit).toBeEnabled())
    fireEvent.click(submit)
    expect(await screen.findByRole('alert')).toHaveTextContent('Текущая версия: 8')
  })

  it('shows saved member charges when draft preview is temporarily unavailable', async () => {
    vi.mocked(api.previewCook).mockRejectedValue(new Error('preview unavailable'))
    renderPage('/cooks/cook-1')

    const alice = await screen.findByRole('group', { name: 'Алиса' })
    expect(within(alice).getByText('200')).toBeInTheDocument()
    expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось рассчитать стоимость участников')
  })
})
