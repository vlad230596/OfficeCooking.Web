import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { App } from '../src/App'
import { getCurrentUser } from '../src/api'

vi.mock('../src/api', async (loadOriginal) => {
  const original = await loadOriginal<typeof import('../src/api')>()
  return {
    ...original,
    getCurrentUser: vi.fn().mockResolvedValue({ id: '11111111-1111-4111-8111-111111111111', name: 'Admin', username: 'admin', role: 'admin' }),
    listUsers: vi.fn().mockResolvedValue([]),
    listTemplates: vi.fn().mockResolvedValue([]),
    getTemplate: vi.fn(),
    listCooks: vi.fn().mockResolvedValue({
      items: [], page: 1, pageSize: 25, totalItems: 0, totalPages: 0,
      ordering: { fields: [{ field: 'cookDate', direction: 'desc' }, { field: 'id', direction: 'asc' }] },
    }),
    listBalances: vi.fn().mockResolvedValue({
      dateFrom: '2023-06-05', dateTo: '2026-08-19', items: [],
      ordering: { fields: [{ field: 'userName', direction: 'asc' }] },
    }),
  }
})

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}><App /></MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('application routes', () => {
  it.each([
    ['/balances', 'Балансы'],
    ['/cooks/new', 'Новая готовка'],
    ['/cooks', 'Готовки'],
    ['/catalog', 'Справочники'],
  ])('renders %s route', async (path, heading) => {
    renderAt(path)
    expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeInTheDocument()
  })

  it('exposes desktop and mobile navigation without a payments route', async () => {
    renderAt('/balances')
    expect(await screen.findByRole('navigation', { name: 'Основная навигация' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Мобильная навигация' })).toBeInTheDocument()
    expect(screen.queryByText('Платежи')).not.toBeInTheDocument()
  })

  it('shows the login form without a valid session', async () => {
    vi.mocked(getCurrentUser).mockRejectedValueOnce(new Error('unauthorized'))
    renderAt('/balances')
    expect(await screen.findByRole('heading', { name: 'Офисная кухня' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Войти' })).toBeInTheDocument()
  })
})
