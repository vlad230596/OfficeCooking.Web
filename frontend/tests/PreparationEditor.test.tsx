import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CookPreparationEditor, PreparationSummary } from '../src/components/PreparationEditor'
import * as api from '../src/api/preparation'
import type { PreparationPlan } from '../src/api/preparation'

vi.mock('../src/auth', () => ({ useAuth: () => ({ user: { id: 'admin' }, hasRole: () => true }) }))
vi.mock('../src/api/preparation')
const members = [{ userId: 'u1', userName: 'Анна' }, { userId: 'u2', userName: 'Борис' }]
const plan: PreparationPlan = {
  options: [
    { key: 'doneness', name: 'Прожарка', values: ['Medium', 'Well'], batchSize: 5 },
    { key: 'tomato', name: 'Помидоры', values: ['С помидорами', 'Без помидоров'], batchSize: 1 },
  ],
  groups: [
    { userId: 'u1', quantity: 2, choices: { doneness: 'Medium', tomato: 'Без помидоров' } },
    { userId: 'u2', quantity: 3, choices: { doneness: 'Medium', tomato: 'С помидорами' } },
  ],
}
beforeEach(() => { vi.clearAllMocks(); localStorage.clear() })
describe('preparation', () => {
  it('keeps combination cards separate while combining batch quantities', () => {
    render(<PreparationSummary plan={plan} members={members} />)
    expect(screen.getByText('Анна · 2')).toBeInTheDocument()
    expect(screen.getByText('Борис · 3')).toBeInTheDocument()
    expect(screen.getByText('1 полных партий по 5')).toBeInTheDocument()
    expect(screen.queryByText(/До полной партии/)).not.toBeInTheDocument()
    expect(screen.getByText('Помидоры: Без помидоров')).toBeInTheDocument()
  })
  it('warns for incomplete batches without hiding the plan', () => {
    render(<PreparationSummary plan={{ ...plan, groups: [plan.groups[0]] }} members={members} />)
    expect(screen.getByText(/2 шт. — нужно кратно 5/)).toBeInTheDocument()
    expect(screen.getByText('Анна · 2')).toBeInTheDocument()
  })
  it('preserves failed-save drafts and original expected version after refresh', async () => {
    vi.mocked(api.getCookPreparation).mockResolvedValue({ ...plan, rowVersion: 7, warnings: [] })
    vi.mocked(api.saveCookPreparation).mockRejectedValue(new Error('Конфликт версии'))
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    const element = <QueryClientProvider client={client}><CookPreparationEditor cookId="c1" rowVersion={7} members={members} /></QueryClientProvider>
    const view = render(element)
    await waitFor(() => expect(screen.getAllByLabelText('Количество')).toHaveLength(2))
    fireEvent.change(screen.getAllByLabelText('Количество')[0], { target: { value: '4' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить пожелания' }))
    await screen.findByRole('alert')
    expect(api.saveCookPreparation).toHaveBeenCalledWith('c1', expect.objectContaining({ groups: expect.arrayContaining([expect.objectContaining({ quantity: 4 })]) }), 7)
    view.unmount()
    vi.mocked(api.getCookPreparation).mockResolvedValue({ ...plan, rowVersion: 8, warnings: [] })
    client.clear()
    render(element)
    await screen.findByText('Восстановлен черновик пожеланий.')
    expect(screen.getAllByLabelText('Количество')[0]).toHaveValue(4)
    expect(screen.getByRole('button', { name: 'Сохранить пожелания' })).toBeDisabled()
    expect(screen.getByText(/Данные на сервере изменились/)).toBeInTheDocument()
  })
})
