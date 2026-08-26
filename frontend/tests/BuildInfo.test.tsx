import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BuildInfo, formatBuildDate } from '../src/components/BuildInfo'

afterEach(() => vi.unstubAllGlobals())

describe('BuildInfo', () => {
  it('formats build timestamps explicitly as UTC', () => {
    expect(formatBuildDate('2026-08-26T18:30:00Z')).toBe('26.08.2026 18:30 UTC')
    expect(formatBuildDate('unknown')).toBe('дата неизвестна')
  })

  it('shows frontend and backend build information', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      component: 'backend',
      version: '1.0.0',
      buildDate: '2026-08-26T18:30:00Z',
    }), { headers: { 'Content-Type': 'application/json' } })))

    render(<BuildInfo />)

    expect(screen.getByText(/Frontend/)).toHaveTextContent('Frontend dev · дата неизвестна')
    expect(await screen.findByText(/Backend/)).toHaveTextContent('Backend 1.0.0 · 26.08.2026 18:30 UTC')
  })
})
