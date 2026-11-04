import { describe, expect, it } from 'vitest'
import { BrowserDiagnostics } from '../../e2e/helpers'

const controlledUrl = 'http://frontend/api/v1/etf-holdings/OIH/acquire'
const controlledRequestId = '17814d8d-f8e4-4128-9d5c-1786aaf47b0d'
const console503 = 'Failed to load resource: the server responded with a status of 503 (Service Unavailable)'

function diagnosticHarness() {
  const listeners = new Map<string, Array<(event: unknown) => void>>()
  const page = {
    on(name: string, listener: (event: unknown) => void) {
      const registered = listeners.get(name) ?? []
      registered.push(listener)
      listeners.set(name, registered)
      return this
    },
    waitForTimeout: async () => undefined,
  }
  const emit = (name: string, event: unknown) => {
    for (const listener of listeners.get(name) ?? []) listener(event)
  }
  const diagnostics = new BrowserDiagnostics()
  diagnostics.attach(page as never)
  return { diagnostics, emit }
}

function responseEvent(url = controlledUrl, requestId = controlledRequestId, status = 503) {
  return {
    url: () => url,
    status: () => status,
    request: () => ({ method: () => 'POST', postDataJSON: () => ({ request_id: requestId }) }),
  }
}

function consoleEvent(url = controlledUrl, text = console503) {
  return { type: () => 'error', text: () => text, location: () => ({ url }) }
}

describe('BrowserDiagnostics controlled API faults', () => {
  it('attributes one exact armed POST response and its matching resource-console entry', async () => {
    const { diagnostics, emit } = diagnosticHarness()
    diagnostics.allowExpectedControlledApiFault(controlledUrl, controlledRequestId, 503)

    emit('response', responseEvent())
    emit('console', consoleEvent())

    await expect(diagnostics.expectNoCriticalIssues()).resolves.toBeUndefined()
    expect(diagnostics.consoleErrors).toEqual([console503])
    expect(diagnostics.unexpectedApi503s).toEqual([])
  })

  it('attributes one matching console entry that arrives before its exact response', async () => {
    const { diagnostics, emit } = diagnosticHarness()
    diagnostics.allowExpectedControlledApiFault(controlledUrl, controlledRequestId, 503)

    emit('console', consoleEvent())
    emit('response', responseEvent())

    await expect(diagnostics.expectNoCriticalIssues()).resolves.toBeUndefined()
    expect(diagnostics.consoleErrors).toEqual([console503])
  })

  it('does not retroactively allow a matching console error that occurred before arming', async () => {
    const { diagnostics, emit } = diagnosticHarness()
    emit('console', consoleEvent())
    diagnostics.allowExpectedControlledApiFault(controlledUrl, controlledRequestId, 503)
    emit('response', responseEvent())

    await expect(diagnostics.expectNoCriticalIssues()).rejects.toThrow('unexpected browser console/page/request failures')
    expect(diagnostics.unexpectedApi503s).toEqual([])
  })

  it.each([
    ['wrong request ID', responseEvent(controlledUrl, 'another-request')],
    ['wrong URL', responseEvent('http://frontend/api/v1/etf-holdings/IGV/acquire')],
    ['wrong method', { ...responseEvent(), request: () => ({ method: () => 'GET', postDataJSON: () => ({ request_id: controlledRequestId }) }) }],
  ])('keeps a %s 503 response fatal', async (_caseName, response) => {
    const { diagnostics, emit } = diagnosticHarness()
    diagnostics.allowExpectedControlledApiFault(controlledUrl, controlledRequestId, 503)
    emit('response', response)
    emit('console', consoleEvent())

    await expect(diagnostics.expectNoCriticalIssues()).rejects.toThrow('unexpected browser console/page/request failures')
    expect(diagnostics.unexpectedApi503s).toHaveLength(1)
  })

  it('allows no more than one matching console entry and rejects a console entry from another URL', async () => {
    const duplicate = diagnosticHarness()
    duplicate.diagnostics.allowExpectedControlledApiFault(controlledUrl, controlledRequestId, 503)
    duplicate.emit('response', responseEvent())
    duplicate.emit('console', consoleEvent())
    duplicate.emit('console', consoleEvent())
    await expect(duplicate.diagnostics.expectNoCriticalIssues()).rejects.toThrow('unexpected browser console/page/request failures')

    const wrongLocation = diagnosticHarness()
    wrongLocation.diagnostics.allowExpectedControlledApiFault(controlledUrl, controlledRequestId, 503)
    wrongLocation.emit('response', responseEvent())
    wrongLocation.emit('console', consoleEvent('http://frontend/api/v1/etf-holdings/IGV/acquire'))
    await expect(wrongLocation.diagnostics.expectNoCriticalIssues()).rejects.toThrow('unexpected browser console/page/request failures')
  })
})
