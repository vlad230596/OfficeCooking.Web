import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createUserPayment, deleteUserPayment, getUserBalance, listBalances } from '../src/api'
import { BalancesPage } from '../src/pages/BalancesPage'

vi.mock('../src/api', () => ({ listBalances: vi.fn(), getUserBalance: vi.fn(), deleteUserPayment: vi.fn(), createUserPayment: vi.fn() }))
vi.mock('../src/auth', () => ({ useAuth: () => ({ hasRole: () => true }) }))
const mockedListBalances = vi.mocked(listBalances)
const mockedGetUserBalance = vi.mocked(getUserBalance)
const mockedDeleteUserPayment = vi.mocked(deleteUserPayment)
const mockedCreateUserPayment = vi.mocked(createUserPayment)

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><BalancesPage /></QueryClientProvider>)
}

describe('BalancesPage', () => {
  beforeEach(() => {
    mockedListBalances.mockReset()
    mockedGetUserBalance.mockReset()
    mockedDeleteUserPayment.mockReset()
    mockedCreateUserPayment.mockReset()
  })

  it('loads the default range and applies controlled filters', async () => {
    mockedListBalances.mockResolvedValue({ dateFrom: '2023-06-05', dateTo: '2026-08-19', items: [], ordering: { fields: [] } })
    renderPage()
    expect(screen.getByLabelText('С даты')).toHaveValue('2023-06-05')
    await waitFor(() => expect(mockedListBalances).toHaveBeenCalled())
    expect(mockedListBalances.mock.calls[0][0]).toMatchObject({ dateFrom: '2023-06-05', nonZeroOnly: false })
    fireEvent.click(screen.getByLabelText('Только ненулевые'))
    await waitFor(() => expect(mockedListBalances).toHaveBeenLastCalledWith(expect.objectContaining({ nonZeroOnly: true })))
    expect(screen.getByText('За выбранный период балансов нет')).toBeInTheDocument()
  })

  it('loads weekly aggregate after selecting a user', async () => {
    const userId = '00000000-0000-0000-0000-000000000001'
    mockedListBalances.mockResolvedValue({
      dateFrom: '2023-06-05', dateTo: '2026-08-19', ordering: { fields: [] },
      items: [{ userId, userName: 'Анна', positive: 1500, negative: -900, cooksCount: 3, cumulativeBalance: 600, adjustments: 0 }],
    })
    mockedGetUserBalance.mockResolvedValue({
      userId, userName: 'Анна', dateFrom: '2023-06-05', dateTo: '2026-08-19', ordering: { fields: [] }, paymentTypes: [{ id: '00000000-0000-0000-0000-000000000002', name: 'Alpha' }],
      weeks: [{ year: 2026, week: 34, display: '17–23 августа', positive: 500, negative: 300, cooksCount: 1, weeklyDelta: 200, cumulativeBalance: 600, adjustment: 0, payments: [], cooks: [], adjustments: [] }],
    })
    renderPage()
    fireEvent.click((await screen.findAllByRole('button', { name: 'Анна' }))[0])
    await waitFor(() => expect(mockedGetUserBalance).toHaveBeenCalledWith(userId, expect.objectContaining({ dateFrom: '2023-06-05' })))
    expect(await screen.findByText('17–23 августа')).toBeInTheDocument()
    expect(screen.getByText('На конец')).toBeInTheDocument()
    expect(screen.getByText('Платежи по дате получения')).toBeInTheDocument()
  })

  it('shows retry and validates an inverted range', async () => {
    mockedListBalances.mockRejectedValueOnce(new Error('network')).mockResolvedValue({ dateFrom: '2023-06-05', dateTo: '2026-08-19', items: [], ordering: { fields: [] } })
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось загрузить балансы')
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }))
    await waitFor(() => expect(mockedListBalances).toHaveBeenCalledTimes(2))
    fireEvent.change(screen.getByLabelText('С даты'), { target: { value: '2026-09-01' } })
    fireEvent.change(screen.getByLabelText('По дату'), { target: { value: '2026-08-01' } })
    expect(screen.getByRole('alert')).toHaveTextContent('Начальная дата')
  })
})
