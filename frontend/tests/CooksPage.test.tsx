import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CooksPage, legacyWeekDisplay } from '../src/pages/CooksPage'

const api = vi.hoisted(() => ({
  listCooks: vi.fn(),
  listTemplates: vi.fn(),
  calculateCookSelection: vi.fn(),
}))

vi.mock('../src/api', () => api)

const cooks = [
  {
    id: '11111111-1111-4111-8111-111111111111',
    cookDate: '2026-08-19',
    templateId: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    typeSnapshot: 'Шаурма',
    memberCount: 8,
    totalVoteWeight: 9.5,
    totalPrice: 1_240,
    rowVersion: 1,
  },
  {
    id: '22222222-2222-4222-8222-222222222222',
    cookDate: '2026-08-12',
    templateId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    typeSnapshot: 'Оливье',
    memberCount: 6,
    totalVoteWeight: 7,
    totalPrice: 980,
    rowVersion: 2,
  },
]

function page(items = cooks) {
  return {
    items,
    page: 1,
    pageSize: 25,
    totalItems: items.length,
    totalPages: items.length ? 2 : 0,
    ordering: { fields: [{ field: 'cookDate', direction: 'desc' }, { field: 'id', direction: 'asc' }] },
  }
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter><CooksPage /></MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  api.listTemplates.mockReset().mockResolvedValue([
    { id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', name: 'Шаурма', isMultivote: false },
    { id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', name: 'Оливье', isMultivote: false },
  ])
  api.listCooks.mockReset().mockResolvedValue(page())
  api.calculateCookSelection.mockReset().mockResolvedValue({
    cookIds: cooks.map(cook => cook.id),
    charges: [
      { userId: 'u-negative', userName: 'Скрытый долг', charge: -5 },
      { userId: 'u-positive', userName: 'Анна', charge: 1_225 },
    ],
    total: 1_220,
    positiveCharges: [{ userId: 'u-positive', userName: 'Анна', charge: 1_225 }],
    positiveTotal: 1_225,
  })
})

describe('CooksPage', () => {
  it('keeps the legacy Gregorian Monday week labels at year boundaries', () => {
    expect(legacyWeekDisplay('2023-01-01')).toBe('2023#1')
    expect(legacyWeekDisplay('2023-01-02')).toBe('2023#2')
    expect(legacyWeekDisplay('2012-12-31')).toBe('2012#54')
  })

  it('loads the broad current range and renders desktop rows, mobile cards and edit links', async () => {
    renderPage()

    expect(await screen.findByRole('heading', { level: 1, name: 'Готовки' })).toBeInTheDocument()
    await screen.findAllByText('Шаурма')
    expect(within(screen.getByRole('table')).getByText('Шаурма')).toBeInTheDocument()
    expect(within(screen.getByRole('table')).getByRole('columnheader', { name: 'Год' })).toBeInTheDocument()
    expect(within(screen.getByRole('table')).getByRole('columnheader', { name: 'Неделя' })).toBeInTheDocument()
    const tableRows = within(screen.getByRole('table')).getAllByRole('row')
    expect(tableRows[1]).toHaveClass('week-band--base')
    expect(tableRows[2]).toHaveClass('week-band--alternate')
    expect(within(screen.getByLabelText('Готовки')).getByText('Шаурма')).toBeInTheDocument()
    const links = screen.getAllByRole('link', { name: /Открыть/ })
    expect(links[0]).toHaveAttribute('href', `/cooks/${cooks[0].id}`)
    expect(api.listCooks).toHaveBeenCalledWith(expect.objectContaining({
      dateFrom: '2022-01-01',
      dateTo: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      page: 1,
      pageSize: 25,
    }))
  })

  it('applies the template filter and requests pages and page sizes from the server', async () => {
    renderPage()
    await screen.findAllByText('Шаурма')

    fireEvent.change(screen.getByLabelText('Блюдо'), {
      target: { value: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Показать' }))
    await waitFor(() => expect(api.listCooks).toHaveBeenLastCalledWith(expect.objectContaining({
      templateId: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
      page: 1,
    })))

    fireEvent.click(screen.getByRole('button', { name: 'Вперёд' }))
    await waitFor(() => expect(api.listCooks).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })))

    fireEvent.change(screen.getByLabelText('На странице'), { target: { value: '50' } })
    await waitFor(() => expect(api.listCooks).toHaveBeenLastCalledWith(expect.objectContaining({
      page: 1,
      pageSize: 50,
    })))
  })

  it('calculates multiple selected cooks and displays only positive charges', async () => {
    renderPage()
    await screen.findAllByText('Шаурма')

    fireEvent.click(screen.getByLabelText('Выбрать готовку 19.08.2026'))
    fireEvent.click(screen.getByLabelText('Выбрать готовку 12.08.2026'))
    expect(screen.getByText('Выбрано: 2')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Рассчитать' }))

    await waitFor(() => expect(api.calculateCookSelection).toHaveBeenCalledWith({
      cookIds: cooks.map(cook => cook.id),
    }))
    expect(await screen.findByLabelText('Таблица начислений')).toHaveTextContent('Анна 1225')
    expect(screen.getByLabelText('Таблица начислений')).not.toHaveTextContent(/1\s225/)
    expect(screen.queryByText('Скрытый долг')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Положительные суммы' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Копировать' })).toBeInTheDocument()
  })

  it('renders loading, error and empty states', async () => {
    let resolveRequest!: (value: ReturnType<typeof page>) => void
    api.listCooks.mockReturnValueOnce(new Promise(resolve => { resolveRequest = resolve }))
    const loading = renderPage()
    expect(screen.getByText('Загрузка готовок…')).toBeInTheDocument()
    resolveRequest(page())
    await screen.findAllByText('Шаурма')
    loading.unmount()

    api.listCooks.mockRejectedValueOnce(new Error('offline'))
    const failed = renderPage()
    expect(await screen.findByText('Не удалось загрузить список готовок.')).toBeInTheDocument()
    failed.unmount()

    api.listCooks.mockResolvedValueOnce(page([]))
    renderPage()
    expect(await screen.findByText('Готовки не найдены')).toBeInTheDocument()
  })
})
