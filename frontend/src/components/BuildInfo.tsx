import { useEffect, useState } from 'react'

type BackendBuildInfo = {
  component: 'backend'
  version: string
  buildDate: string
}

const frontendVersion = import.meta.env.VITE_APP_VERSION || 'dev'
const frontendBuildDate = import.meta.env.VITE_BUILD_DATE || 'unknown'

export function formatBuildDate(value: string): string {
  const parsed = new Date(value)
  if (value === 'unknown' || Number.isNaN(parsed.getTime())) return 'дата неизвестна'
  const [date, time] = parsed.toISOString().split('T')
  const [year, month, day] = date.split('-')
  return `${day}.${month}.${year} ${time.slice(0, 5)} UTC`
}

export function BuildInfo() {
  const [backend, setBackend] = useState<BackendBuildInfo | null>(null)

  useEffect(() => {
    if (typeof fetch !== 'function') return
    const controller = new AbortController()
    fetch('/version', {
      cache: 'no-store',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Version request failed: ${response.status}`)
        return await response.json() as BackendBuildInfo
      })
      .then(setBackend)
      .catch(() => undefined)
    return () => controller.abort()
  }, [])

  return (
    <aside className="build-info" aria-label="Версии сборки" aria-live="polite">
      <span>Frontend <strong>{frontendVersion}</strong> · {formatBuildDate(frontendBuildDate)}</span>
      <span>Backend <strong>{backend?.version ?? 'недоступен'}</strong> · {backend ? formatBuildDate(backend.buildDate) : 'дата неизвестна'}</span>
    </aside>
  )
}
