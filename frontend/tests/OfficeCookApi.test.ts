import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../src/api/client'
import {
  calculateCookSelection,
  createTemplate,
  createUser,
  createCook,
  getCook,
  getTemplate,
  getUserBalance,
  listBalances,
  listCooks,
  listTemplates,
  listUsers,
  previewExpression,
  previewCook,
  updateCook,
  updateTemplate,
  updateUser,
} from '../src/api/officeCookApi'
import type { CreateCookRequest, UpdateCookRequest } from '../src/api/contracts'

const jsonResponse = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: { 'Content-Type': 'application/json' },
})

describe('OfficeCook API', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('builds catalog paths and forwards AbortSignal', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse([])))
    vi.stubGlobal('fetch', fetchMock)
    const controller = new AbortController()

    await listUsers({ enabled: 'true', signal: controller.signal })
    await listTemplates({ signal: controller.signal })
    await getTemplate('template/id', { signal: controller.signal })
    const userRequest = { name: 'Ирина', permanentSale: 1, enabled: true, contacts: [] }
    const dishRequest = { name: 'Салат', isMultivote: false, voteVariants: [], ingredients: [] }
    await createUser(userRequest, { signal: controller.signal })
    await updateUser('user/id', userRequest, { signal: controller.signal })
    await createTemplate(dishRequest, { signal: controller.signal })
    await updateTemplate('dish/id', dishRequest, { signal: controller.signal })

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/users?enabled=true',
      '/api/v1/templates',
      '/api/v1/templates/template%2Fid',
      '/api/v1/users',
      '/api/v1/users/user%2Fid',
      '/api/v1/templates',
      '/api/v1/templates/dish%2Fid',
    ])
    expect(fetchMock.mock.calls.every(([, init]) => init.signal === controller.signal)).toBe(true)
    expect(fetchMock.mock.calls.slice(3).map(([, init]) => init.method)).toEqual(['POST', 'PUT', 'POST', 'PUT'])
  })

  it('serializes cook filters with public camelCase query names', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ items: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await listCooks({
      dateFrom: '2026-01-02',
      dateTo: '2026-03-04',
      templateId: 'template-id',
      page: 2,
      pageSize: 25,
    })

    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/cooks?dateFrom=2026-01-02&dateTo=2026-03-04&templateId=template-id&page=2&pageSize=25')
  })

  it('uses the complete cook mutation and calculation route surface', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse({})))
    vi.stubGlobal('fetch', fetchMock)
    const createRequest: CreateCookRequest = {
      cookDate: '2026-08-19',
      templateId: 'template-id',
      members: [{ position: 0, userId: 'user-id', active: true, voteVariantPositions: [0] }],
      productPrices: [{ position: 0, productName: 'Рис', expression: '100*2' }],
    }
    const updateRequest: UpdateCookRequest = {
      expectedVersion: 3,
      cookDate: '2026-08-19',
      voteVariants: [{ id: 'variant-id', position: 0, name: 'Порция', value: 1 }],
      members: [{ position: 0, userId: 'user-id', active: true, cookVoteVariantIds: ['variant-id'] }],
      productPrices: [{ position: 0, productName: 'Рис', expression: '100*2' }],
    }

    await getCook('cook-id')
    await createCook(createRequest)
    await updateCook('cook-id', updateRequest)
    await calculateCookSelection({ cookIds: ['cook-id'] })
    await previewCook({
      cookId: null,
      voteVariants: [{ id: 'variant-id', position: 0, value: 1 }],
      members: [{ position: 0, userId: 'user-id', active: true, cookVoteVariantIds: ['variant-id'] }],
      productPrices: [{ position: 0, productName: 'Рис', expression: '100*2' }],
    })
    await previewExpression({ expression: '100*2' })

    expect(fetchMock.mock.calls.map(([url, init]) => [url, init.method])).toEqual([
      ['/api/v1/cooks/cook-id', undefined],
      ['/api/v1/cooks', 'POST'],
      ['/api/v1/cooks/cook-id', 'PUT'],
      ['/api/v1/cooks/calculate-selection', 'POST'],
      ['/api/v1/cooks/preview', 'POST'],
      ['/api/v1/calculations/expressions/preview', 'POST'],
    ])
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual(createRequest)
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual(updateRequest)
  })

  it('builds both balance queries and includes explicit false', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse({ items: [] })))
    vi.stubGlobal('fetch', fetchMock)

    await listBalances({ dateFrom: '2026-01-01', dateTo: '2026-01-31' })
    await getUserBalance('user/id', { dateFrom: '2026-01-01', dateTo: '2026-01-31' })

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/balances?dateFrom=2026-01-01&dateTo=2026-01-31&nonZeroOnly=false',
      '/api/v1/balances/users/user%2Fid?dateFrom=2026-01-01&dateTo=2026-01-31',
    ])
  })

  it('parses the structured backend error envelope', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      error: {
        code: 'invalid_snapshot',
        message: 'Snapshot is invalid.',
        fieldErrors: [{ field: 'cookDate', code: 'invalid', message: 'Bad date.' }],
        details: { reason: 'date' },
        requestId: 'request-42',
      },
    }, 422)))

    const error = await listTemplates().catch((reason: unknown) => reason)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      message: 'Snapshot is invalid.',
      status: 422,
      code: 'invalid_snapshot',
      requestId: 'request-42',
      details: { reason: 'date' },
      fieldErrors: [{ field: 'cookDate', code: 'invalid', message: 'Bad date.' }],
    })
  })
})
