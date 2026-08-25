import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import * as api from '../src/api'
import { CatalogPage } from '../src/pages/CatalogPage'

vi.mock('../src/api', async (loadOriginal) => ({
  ...await loadOriginal<typeof import('../src/api')>(),
  listUsers: vi.fn(), listTemplates: vi.fn(), getTemplate: vi.fn(),
  createUser: vi.fn(), updateUser: vi.fn(), createTemplate: vi.fn(), updateTemplate: vi.fn(),
}))

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><CatalogPage /></QueryClientProvider>)
}

describe('CatalogPage', () => {
  it('adds a user with ordered contacts', async () => {
    vi.mocked(api.listUsers).mockResolvedValue([])
    vi.mocked(api.listTemplates).mockResolvedValue([])
    vi.mocked(api.createUser).mockResolvedValue({ id: 'u1', legacyId: 48, name: 'Анна', permanentSale: 0.8, enabled: true, contacts: [{ position: 0, value: '@anna' }] })
    renderPage()

    fireEvent.change(await screen.findByLabelText('Имя'), { target: { value: 'Анна' } })
    fireEvent.change(screen.getByLabelText('Постоянный коэффициент'), { target: { value: '0.8' } })
    fireEvent.click(screen.getByRole('button', { name: /Добавить строку/ }))
    fireEvent.change(screen.getByLabelText('Контакт 1'), { target: { value: '@anna' } })
    fireEvent.click(screen.getByRole('button', { name: 'Добавить пользователя' }))

    await waitFor(() => expect(api.createUser).toHaveBeenCalledWith({ name: 'Анна', permanentSale: 0.8, enabled: true, contacts: [{ value: '@anna' }] }))
  })

  it('edits a dish using food-facing labels', async () => {
    vi.mocked(api.listUsers).mockResolvedValue([])
    vi.mocked(api.listTemplates).mockResolvedValue([{ id: 'd1', name: 'Салат', isMultivote: false }])
    vi.mocked(api.getTemplate).mockResolvedValue({ id: 'd1', name: 'Салат', isMultivote: false, voteVariants: [{ id: 'v1', position: 0, name: 'Обычный', value: 1 }], ingredients: [] })
    vi.mocked(api.updateTemplate).mockResolvedValue({ id: 'd1', name: 'Салат', isMultivote: false, voteVariants: [{ id: 'v1', position: 0, name: 'Обычный', value: 1 }], ingredients: [] })
    renderPage()

    fireEvent.click(screen.getByRole('tab', { name: 'Блюда' }))
    fireEvent.click(await screen.findByRole('button', { name: /Салат/ }))
    expect(await screen.findByRole('heading', { name: 'Редактирование блюда' })).toBeInTheDocument()
    expect(screen.queryByText(/шаблон/i)).not.toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: 'Сохранить изменения' }))

    await waitFor(() => expect(api.updateTemplate).toHaveBeenCalledWith('d1', expect.objectContaining({ name: 'Салат', voteVariants: [{ name: 'Обычный', value: 1 }] })))
  })
})
