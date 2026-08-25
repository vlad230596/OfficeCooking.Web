// @vitest-environment node

import { createServer as createHttpServer } from 'node:http'
import type { AddressInfo } from 'node:net'
import { createServer as createViteServer } from 'vite'
import { afterEach, describe, expect, it } from 'vitest'
import { createApiProxy, defaultDevApiTarget } from '../devProxy'

const closeCallbacks: Array<() => Promise<void>> = []

afterEach(async () => {
  await Promise.all(closeCallbacks.splice(0).map((close) => close()))
})

describe('development API proxy', () => {
  it('targets the local backend by default', () => {
    expect(createApiProxy()).toMatchObject({
      '/api': { target: defaultDevApiTarget, changeOrigin: false },
    })
  })

  it('forwards the versioned API path without a database', async () => {
    const upstream = createHttpServer((request, response) => {
      response.setHeader('Content-Type', 'application/json')
      response.end(JSON.stringify({ path: request.url }))
    })
    await new Promise<void>((resolve) => upstream.listen(0, '127.0.0.1', resolve))
    closeCallbacks.push(() => new Promise<void>((resolve, reject) => upstream.close((error) => error ? reject(error) : resolve())))
    const upstreamPort = (upstream.address() as AddressInfo).port

    const vite = await createViteServer({
      configFile: false,
      root: process.cwd(),
      logLevel: 'silent',
      server: {
        host: '127.0.0.1',
        port: 0,
        proxy: createApiProxy(`http://127.0.0.1:${upstreamPort}`),
      },
    })
    await vite.listen()
    closeCallbacks.push(() => vite.close())
    const vitePort = (vite.httpServer!.address() as AddressInfo).port

    const response = await fetch(`http://127.0.0.1:${vitePort}/api/v1/proxy-smoke`)
    expect(response.ok).toBe(true)
    await expect(response.json()).resolves.toEqual({ path: '/api/v1/proxy-smoke' })
  })
})
