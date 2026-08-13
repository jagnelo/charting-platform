import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

import { api } from '@/lib/api'
import {
  classifyInstrumentInput,
  ensureKnownInstrumentSymbol,
  formatInstrumentLookupError,
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
    vi.mocked(api.get).mockResolvedValue({ id: 42, symbol: 'NVDA' })
    await expect(resolveKnownInstrument('nvda', 'Workstation symbol', { canonicalOnly: true }))
      .resolves.toEqual({ symbol: 'NVDA', id: 42 })
    expect(api.get).toHaveBeenCalledWith('/instruments/NVDA', { canonical_only: true })
  })
})
