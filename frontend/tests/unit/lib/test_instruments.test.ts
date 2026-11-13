import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
  setQueuedApiRequestPriority: vi.fn(),
}))

import { api, setQueuedApiRequestPriority } from '@/lib/api'
import {
  classifyInstrumentInput,
  ensureKnownInstrumentSymbol,
  formatInstrumentLookupError,
  resolveCanonicalSymbols,
  resolveKnownInstrument,
} from '@/lib/instruments'

describe('instrument helpers', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('treats bare and trailing-operator expressions as pending input', () => {
    expect(classifyInstrumentInput('=').kind).toBe('pending_expression')
    expect(classifyInstrumentInput('=SPY/').kind).toBe('pending_expression')
    expect(classifyInstrumentInput('=SPY/QQQ').kind).toBe('expression')
  })

  it('rejects incomplete expressions without touching the API', async () => {
    await expect(ensureKnownInstrumentSymbol('=')).rejects.toThrow('Finish the expression to continue.')
    expect(api.get).not.toHaveBeenCalled()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('formats unresolved expression lookups cleanly', () => {
    const error = new Error(
      'API POST /instruments/resolve-expression → 404: {"detail":"Constituent instrument \'MISS\' not found"}'
    )

    expect(formatInstrumentLookupError('=DIA/MISS', error)).toBe('Could not resolve =DIA/MISS')
  })

  it('returns canonical identity alongside the normalized symbol', async () => {
    vi.mocked(api.get).mockResolvedValue({ id: 42, symbol: 'NVDA', instrument_type: 'Exchange Traded Vehicle' })
    await expect(resolveKnownInstrument('nvda', 'Workstation symbol', { canonicalOnly: true }))
      .resolves.toEqual({ symbol: 'NVDA', id: 42, instrumentType: 'Exchange Traded Vehicle' })
    expect(api.get).toHaveBeenCalledWith('/instruments/NVDA', { canonical_only: true })
  })

  it('promotes a queued canonical lookup for an explicit foreground selection', async () => {
    vi.mocked(api.get).mockResolvedValue({ id: 3, symbol: 'RSP', instrument_type: 'ETF' })
    await expect(resolveKnownInstrument('rsp', 'Comparison symbol', {
      canonicalOnly: true,
      priority: 'high',
      foreground: true,
    })).resolves.toEqual({ symbol: 'RSP', id: 3, instrumentType: 'ETF' })
    expect(setQueuedApiRequestPriority).toHaveBeenCalledWith('instrument-lookup:RSP:canonical', 'high', true)
    expect(api.get).toHaveBeenCalledWith('/instruments/RSP', { canonical_only: true }, {
      priority: 'high', foreground: true, queueKey: 'instrument-lookup:RSP:canonical',
    })
  })

  it('resolves a bounded symbol batch through one canonical-only request', async () => {
    vi.mocked(api.post).mockResolvedValue({
      resolved: [{ symbol: 'NVDA', instrument_id: 42 }, { symbol: 'MSFT', instrument_id: 43 }],
      missing: [],
    })
    await expect(resolveCanonicalSymbols(['nvda', 'MSFT', 'NVDA'], 'Explicit symbol'))
      .resolves.toEqual([{ symbol: 'NVDA', id: 42 }, { symbol: 'MSFT', id: 43 }])
    expect(api.post).toHaveBeenCalledWith('/instruments/resolve-canonical', { symbols: ['NVDA', 'MSFT'] })
    expect(api.get).not.toHaveBeenCalled()
  })

  it('reports missing members without silently falling back to providers', async () => {
    vi.mocked(api.post).mockResolvedValue({ resolved: [{ symbol: 'NVDA', instrument_id: 42 }], missing: ['MISSING'] })
    await expect(resolveCanonicalSymbols(['NVDA', 'MISSING'], 'Explicit symbol'))
      .rejects.toThrow('Could not resolve MISSING')
    expect(api.get).not.toHaveBeenCalled()
  })
})
