import { apiConfig } from './config'

export type ApiFieldError = {
  field: string
  code: string
  message: string
}

export type ApiErrorPayload = {
  code: string
  message: string
  fieldErrors: ApiFieldError[]
  details: Record<string, unknown>
  requestId: string
}

export type ApiErrorEnvelope = {
  error: ApiErrorPayload
}

export class ApiError extends Error {
  readonly code?: string
  readonly fieldErrors: ApiFieldError[]
  readonly details: Record<string, unknown>
  readonly requestId?: string

  constructor(
    message: string,
    readonly status: number,
    readonly body: unknown,
  ) {
    super(message)
    this.name = 'ApiError'

    const payload = getErrorPayload(body)
    this.code = payload?.code
    this.fieldErrors = payload?.fieldErrors ?? []
    this.details = payload?.details ?? {}
    this.requestId = payload?.requestId
  }
}

export type RequestOptions = Omit<RequestInit, 'body'> & {
  body?: unknown
}

export async function apiRequest<TResponse>(
  path: string,
  options: RequestOptions = {},
): Promise<TResponse> {
  const { body, headers, ...requestInit } = options
  const requestHeaders = new Headers(headers)
  requestHeaders.set('Accept', 'application/json')
  if (body !== undefined && !requestHeaders.has('Content-Type')) {
    requestHeaders.set('Content-Type', 'application/json')
  }
  const method = (requestInit.method ?? 'GET').toUpperCase()
  if (['POST', 'PUT', 'PATCH'].includes(method) && !requestHeaders.has('X-CSRF-Token')) {
    const csrfToken = readCookie('office_cook_csrf')
    if (csrfToken) requestHeaders.set('X-CSRF-Token', csrfToken)
  }

  const response = await fetch(`${apiConfig.baseUrl}/${path.replace(/^\//, '')}`, {
    ...requestInit,
    credentials: 'include',
    headers: requestHeaders,
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  const responseBody = await readResponseBody(response)
  if (!response.ok) {
    if (response.status === 401 && typeof window !== 'undefined') {
      window.dispatchEvent(new Event('office-cook:unauthorized'))
    }
    const payload = getErrorPayload(responseBody)
    throw new ApiError(
      payload?.message ?? `API request failed with status ${response.status}`,
      response.status,
      responseBody,
    )
  }

  return responseBody as TResponse
}

function readCookie(name: string): string | undefined {
  if (typeof document === 'undefined') return undefined
  const prefix = `${encodeURIComponent(name)}=`
  const item = document.cookie.split('; ').find((value) => value.startsWith(prefix))
  return item ? decodeURIComponent(item.slice(prefix.length)) : undefined
}

async function readResponseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined

  const contentType = response.headers.get('content-type') ?? ''
  const text = await response.text()
  if (!text) return undefined
  if (!contentType.includes('application/json')) return text

  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

function getErrorPayload(body: unknown): ApiErrorPayload | undefined {
  if (!isRecord(body) || !isRecord(body.error)) return undefined

  const error = body.error
  if (
    typeof error.code !== 'string'
    || typeof error.message !== 'string'
    || typeof error.requestId !== 'string'
    || !Array.isArray(error.fieldErrors)
    || !isRecord(error.details)
  ) return undefined

  const fieldErrors = error.fieldErrors.filter(isFieldError)
  if (fieldErrors.length !== error.fieldErrors.length) return undefined

  return {
    code: error.code,
    message: error.message,
    fieldErrors,
    details: error.details,
    requestId: error.requestId,
  }
}

function isFieldError(value: unknown): value is ApiFieldError {
  return isRecord(value)
    && typeof value.field === 'string'
    && typeof value.code === 'string'
    && typeof value.message === 'string'
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
