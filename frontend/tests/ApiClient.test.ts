import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiRequest } from '../src/api/client'

describe('apiRequest', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('normalizes a path and parses a JSON response', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok' }), {
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiRequest<{ status: string }>('/cooks')).resolves.toEqual({ status: 'ok' })
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/cooks', expect.objectContaining({ headers: expect.any(Headers) }))
  })

  it('keeps the response body on an API error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ code: 'unavailable' }), {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
      }),
    ))

    const request = apiRequest<never>('cooks')
    await expect(request).rejects.toBeInstanceOf(ApiError)
    await expect(request).rejects.toMatchObject({ status: 503, body: { code: 'unavailable' } })
  })
})
