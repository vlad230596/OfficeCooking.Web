const defaultApiBaseUrl = '/api/v1'

export const apiConfig = Object.freeze({
  baseUrl: (import.meta.env.VITE_API_BASE_URL || defaultApiBaseUrl).replace(/\/$/, ''),
})

