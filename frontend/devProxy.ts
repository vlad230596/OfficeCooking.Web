import type { ProxyOptions } from 'vite'

export const defaultDevApiTarget = 'http://127.0.0.1:8000'

export function createApiProxy(target = defaultDevApiTarget): Record<string, ProxyOptions> {
  const url = new URL(target)
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error('DEV_API_PROXY_TARGET must use http or https')
  }

  return {
    '/api': {
      target: url.origin,
      changeOrigin: false,
    },
    '/version': {
      target: url.origin,
      changeOrigin: false,
    },
  }
}
