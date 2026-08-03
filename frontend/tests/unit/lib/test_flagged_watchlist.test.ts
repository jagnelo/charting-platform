import { describe, expect, it } from 'vitest'
import { buildFlaggedWatchlistRows } from '@/lib/workstation/flagged-watchlist'

describe('buildFlaggedWatchlistRows', () => {
  it('deduplicates flagged instruments and preserves the first canonical source', () => {
    const rows = buildFlaggedWatchlistRows([
      {
        id: 10, name: 'Momentum', is_default: false, is_managed: false, is_locked: false,
        position: 0,
        items: [
          { id: 101, instrument_id: 7, symbol: 'NVDA', name: 'NVIDIA', position: 0, flagged: true },
          { id: 102, instrument_id: 8, symbol: 'MSFT', name: 'Microsoft', position: 1, flagged: false },
        ],
      },
      {
        id: 11, name: 'Breakouts', is_default: false, is_managed: false, is_locked: false,
        position: 1,
        items: [
          { id: 111, instrument_id: 7, symbol: 'NVDA', name: 'NVIDIA', position: 0, flagged: true },
          { id: 112, instrument_id: 9, symbol: 'AMD', name: 'AMD', position: 1, flagged: true },
        ],
      },
    ], { NVDA: { close: 140, pct: 0.02 } })

    expect(rows).toEqual([
      expect.objectContaining({ itemId: 101, sourceWatchlistId: 10, instrumentId: 7, symbol: 'NVDA', values: { last: 140, change: 0.02 } }),
      expect.objectContaining({ itemId: 112, sourceWatchlistId: 11, instrumentId: 9, symbol: 'AMD' }),
    ])
    expect(rows).toHaveLength(2)
  })

  it('uses stable instrument fallbacks when metadata or quotes are absent', () => {
    const rows = buildFlaggedWatchlistRows([
      {
        id: 4, name: 'Watch', is_default: false, is_managed: false, is_locked: false,
        position: 0, items: [{ id: 41, instrument_id: 99, position: 0, flagged: true }],
      },
    ], {})

    expect(rows[0]).toMatchObject({ symbol: '#99', name: 'Instrument 99', values: { last: null, change: null } })
  })
})
