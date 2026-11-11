import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createUserPayment, deleteUserPayment, getUserBalance, listBalances } from '../src/api'
import { BalancesPage } from '../src/pages/BalancesPage'

vi.mock('../src/api', () => ({ listBalances: vi.fn(), getUserBalance: vi.fn(), deleteUserPayment: vi.fn(), createUserPayment: vi.fn() }))
vi.mock('../src/auth', () => ({ useAuth: () => ({ user: { id: 'admin-1' }, hasRole: () => true }) }))
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
    window.localStorage.clear()
    mockedListBalances.mockReset()
    mockedGetUserBalance.mockReset()
    mockedDeleteUserPayment.mockReset()
    mockedCreateUserPayment.mockReset()
  })

  it('restores payment and adjustment drafts independently after refresh', async () => {
    mockedListBalances.mockResolvedValue({ dateFrom: '2023-06-05', dateTo: '2026-08-19', ordering: { fields: [] }, items: [{ userId: 'u1', userName: 'Анна', positive: 0, negative: 0, cooksCount: 0, cumulativeBalance: 0, adjustments: 0 }] })
    mockedGetUserBalance.mockResolvedValue({ userId: 'u1', userName: 'Анна', dateFrom: '2023-06-05', dateTo: '2026-08-19', ordering: { fields: [] }, paymentTypes: [{ id: 'type1', name: 'Alpha' }], weeks: [] })
    const first = renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Анна' }))
    await screen.findByText('Недельных данных нет')
    fireEvent.click(screen.getByRole('button', { name: 'Добавить платёж' }))
    fireEvent.change(screen.getByLabelText('Сумма'), { target: { value: '125' } })
    fireEvent.change(screen.getByLabelText('Комментарий'), { target: { value: 'Деньги за обед' } })
    fireEvent.click(screen.getByRole('button', { name: 'Корректировка' }))
    fireEvent.change(screen.getByLabelText('Сумма'), { target: { value: '-50' } })
    fireEvent.change(screen.getByLabelText('Причина'), { target: { value: 'Старая разница' } })
    first.unmount()

    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Анна' }))
    await screen.findByText('Недельных данных нет')
    fireEvent.click(screen.getByRole('button', { name: 'Добавить платёж' }))
    expect(screen.getByLabelText('Сумма')).toHaveValue(125)
    expect(screen.getByLabelText('Комментарий')).toHaveValue('Деньги за обед')
    fireEvent.click(screen.getByRole('button', { name: 'Корректировка' }))
    expect(screen.getByLabelText('Сумма')).toHaveValue(-50)
    expect(screen.getByLabelText('Причина')).toHaveValue('Старая разница')
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

  it('separates purchases and dated organizer reimbursements from received payments', async () => {
    mockedListBalances.mockResolvedValue({
      dateFrom: '2023-06-05', dateTo: '2026-08-19', ordering: { fields: [] },
      items: [{ userId: 'buyer', userName: 'Покупатель', positive: 0, negative: 600, cooksCount: 1, cumulativeBalance: -300, adjustments: 0, purchasesTotal: 500, reimbursementsTotal: 200, separateOwed: 300 }],
    })
    mockedGetUserBalance.mockResolvedValue({
      userId: 'buyer', userName: 'Покупатель', dateFrom: '2023-06-05', dateTo: '2026-08-19', ordering: { fields: [] }, paymentTypes: [],
      weeks: [
        { year: 2026, week: 33, display: 'Неделя покупки', positive: 0, negative: 600, cooksCount: 1, weeklyDelta: -100, cumulativeBalance: -100, adjustment: 0, payments: [], cooks: [], adjustments: [], purchasesTotal: 500, reimbursementsTotal: 0, separateOwed: 300, settlementEvents: [{ id: 'purchase', cookId: 'cook', eventDate: '2026-08-10', kind: 'purchase', amount: 500, description: 'Продукты для команды', mode: 'separate', separateOwed: 300 }] },
        { year: 2026, week: 34, display: 'Неделя возврата', positive: 0, negative: 0, cooksCount: 0, weeklyDelta: -200, cumulativeBalance: -300, adjustment: 0, payments: [], cooks: [], adjustments: [], purchasesTotal: 0, reimbursementsTotal: 200, separateOwed: 0, settlementEvents: [{ id: 'refund', cookId: 'cook', eventDate: '2026-08-17', kind: 'reimbursement', amount: 200, description: 'Частичный возврат покупки', mode: 'separate', separateOwed: null }] },
      ],
    })
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Покупатель' }))
    const purchaseHeading = await screen.findByRole('heading', { name: 'Неделя покупки' })
    const purchaseWeek = within(purchaseHeading.closest('article')!)
    const refundWeek = within(screen.getByRole('heading', { name: 'Неделя возврата' }).closest('article')!)
    expect(purchaseWeek.getByText('Продукты для команды')).toBeInTheDocument()
    expect(screen.getByText('К возврату: 300')).toBeInTheDocument()
    expect(purchaseWeek.getByText('Осталось вернуть отдельно')).toBeInTheDocument()
    expect(purchaseWeek.getByText('Осталось вернуть отдельно: 300')).toBeInTheDocument()
    expect(refundWeek.queryByText('Осталось вернуть отдельно')).not.toBeInTheDocument()
    expect(purchaseWeek.getAllByText('+500')).toHaveLength(2)
    expect(purchaseWeek.getByText('Платежей не было')).toBeInTheDocument()
    expect(refundWeek.getByText('Частичный возврат покупки')).toBeInTheDocument()
    expect(refundWeek.getByText('Организатор вернул')).toBeInTheDocument()
    expect(refundWeek.getByText('Вернули участнику')).toBeInTheDocument()
    expect(refundWeek.getAllByText('−200')).toHaveLength(2)
    expect(refundWeek.getByText('Платежей не было')).toBeInTheDocument()
    expect(refundWeek.queryByText('Продукты для команды')).not.toBeInTheDocument()
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
