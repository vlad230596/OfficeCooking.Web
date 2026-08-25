import type { ReactNode } from 'react'

export function LoadingState({ label = 'Загрузка данных…' }: { label?: string }) {
  return (
    <div aria-live="polite" aria-busy="true" className="state-card">
      <span aria-hidden="true" className="spinner" />
      <p>{label}</p>
    </div>
  )
}

export function ErrorState({ message = 'Не удалось загрузить данные.', onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="state-card state-card--error">
      <span aria-hidden="true" className="state-card__symbol">!</span>
      <div>
        <strong>Что-то пошло не так</strong>
        <p>{message}</p>
        {onRetry && <button className="button button--secondary" onClick={onRetry}>Повторить</button>}
      </div>
    </div>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state-card state-card--empty">
      <span aria-hidden="true" className="state-card__symbol">○</span>
      <div>
        <strong>{title}</strong>
        {children && <div className="state-card__description">{children}</div>}
      </div>
    </div>
  )
}

