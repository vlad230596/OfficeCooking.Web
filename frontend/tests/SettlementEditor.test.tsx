import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SettlementEditor } from '../src/components/SettlementEditor'
import * as settlements from '../src/api/settlements'
import * as api from '../src/api/officeCookApi'
import type { CookDetail } from '../src/api'

vi.mock('../src/api/settlements')
vi.mock('../src/api/officeCookApi')
vi.mock('../src/auth', () => ({ useAuth: () => ({ user: { id: 'admin' }, hasRole: () => true }) }))
const cook = { id: 'cook', rowVersion: 1, members: [{ userId: 'alice', charge: 300 }] } as CookDetail
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><SettlementEditor cook={cook} /></QueryClientProvider>)
}
beforeEach(() => {
  window.localStorage.clear(); vi.clearAllMocks()
  vi.mocked(api.listUsers).mockResolvedValue([{ id: 'alice', name: 'Алиса' }] as Awaited<ReturnType<typeof api.listUsers>>)
  vi.mocked(settlements.getSettlements).mockResolvedValue({ cookId: 'cook', rowVersion: 1, purchases: [{ id: 'purchase', userId: 'alice', userName: 'Алиса', amount: 500, description: 'Овощи', mode: 'offset', repayments: [] }] })
})
describe('purchases and refunds', () => {
  it('shows offset overflow and records a real repayment without losing draft after error', async () => {
    vi.mocked(settlements.saveSettlements).mockRejectedValue(new Error('Сеть недоступна'))
    setup()
    expect(await screen.findByText(/вернуть 200 сверх зачёта/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Записать выполненный перевод'))
    fireEvent.change(screen.getByLabelText('Уже вернули, ₽'), { target: { value: '200' } })
    expect(screen.getByText(/к оплате 0/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Сохранить взаиморасчёты'))
    await screen.findByText(/Не удалось сохранить: Сеть недоступна/)
    expect(settlements.saveSettlements).toHaveBeenCalledWith('cook', 1, [expect.objectContaining({ amount: 500, repayments: [expect.objectContaining({ amount: 200 })] })])
    expect(window.localStorage.length).toBe(1)
  })
  it('keeps meal charge unchanged for separate refunds and clears successful draft', async () => {
    vi.mocked(settlements.saveSettlements).mockResolvedValue({ cookId: 'cook', rowVersion: 2, purchases: [{ id: 'purchase', userId: 'alice', amount: 500, description: 'Овощи', mode: 'separate', repayments: [] }] })
    setup()
    await screen.findByText(/вернуть 200 сверх зачёта/)
    fireEvent.change(screen.getByLabelText('Как компенсировать'), { target: { value: 'separate' } })
    expect(screen.getByText(/к оплате 300/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Сохранить взаиморасчёты'))
    await screen.findByText('Взаиморасчёты сохранены.')
    await waitFor(() => expect(window.localStorage.length).toBe(0))
  })
  it('restores a draft and blocks stale overwrite', async () => {
    window.localStorage.setItem('office-cook:draft:v1:admin:settlements:cook', JSON.stringify({ baseVersion: 1, purchases: [{ userId: 'alice', amount: '700', description: 'Несохранённое', mode: 'offset', repayments: [] }] }))
    vi.mocked(settlements.getSettlements).mockResolvedValue({ cookId: 'cook', rowVersion: 2, purchases: [] })
    setup()
    await screen.findByText(/Готовка изменилась/)
    expect(screen.getByLabelText('Сумма, ₽')).toHaveValue(700)
    expect(screen.getByText('Сохранить взаиморасчёты')).toBeDisabled()
  })
})
