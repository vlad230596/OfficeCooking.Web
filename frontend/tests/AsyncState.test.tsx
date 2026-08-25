import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { EmptyState, ErrorState, LoadingState } from '../src/components/AsyncState'

describe('async states', () => {
  it('announces loading', () => {
    render(<LoadingState />)
    expect(screen.getByText('Загрузка данных…').parentElement).toHaveAttribute('aria-busy', 'true')
  })

  it('offers error retry', () => {
    const retry = vi.fn()
    render(<ErrorState onRetry={retry} />)
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }))
    expect(retry).toHaveBeenCalledOnce()
  })

  it('renders empty content', () => {
    render(<EmptyState title="Нет записей">Измените фильтры.</EmptyState>)
    expect(screen.getByText('Нет записей')).toBeInTheDocument()
    expect(screen.getByText('Измените фильтры.')).toBeInTheDocument()
  })
})

