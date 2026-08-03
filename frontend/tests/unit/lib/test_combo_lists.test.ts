import { describe, expect, it } from 'vitest'
import { buildComboWatchlistRows } from '@/lib/workstation/combo-lists'

const lists = [
  { id: 1, name: 'Tech', is_default: false, is_managed: false, is_locked: false, position: 0, items: [
    { id: 11, instrument_id: 101, symbol: 'NVDA', name: 'NVIDIA', position: 0, flagged: true },
    { id: 12, instrument_id: 102, symbol: 'MSFT', name: 'Microsoft', position: 1 },
  ] },
  { id: 2, name: 'Leaders', is_default: false, is_managed: false, is_locked: false, position: 1, items: [
    { id: 21, instrument_id: 101, symbol: 'NVDA', name: 'NVIDIA', position: 0 },
    { id: 22, instrument_id: 103, symbol: 'AMD', name: 'AMD', position: 1 },
  ] },
  { id: 3, name: 'Exclude', is_default: false, is_managed: false, is_locked: false, position: 2, items: [
    { id: 31, instrument_id: 102, symbol: 'MSFT', name: 'Microsoft', position: 0 },
  ] },
] as any

describe('buildComboWatchlistRows', () => {
  it('applies union, intersection, and exclusion against canonical instrument IDs', () => {
    const rows = buildComboWatchlistRows(lists, {
      stable_key: 'combo', name: 'Combo', payload: {
        union_watchlist_ids: [1],
        intersection_watchlist_ids: [2],
        exclude_watchlist_ids: [3],
      },
    }, {})
    expect(rows.map(row => row.symbol)).toEqual(['NVDA'])
    expect(rows[0]).toMatchObject({ itemId: 11, sourceWatchlistId: 1, flagged: true })
  })

  it('preserves deterministic first-source metadata for a union', () => {
    const rows = buildComboWatchlistRows(lists, {
      stable_key: 'combo', name: 'Combo', payload: { union_watchlist_ids: [1, 2] },
    }, { NVDA: { close: 140, pct: 0.02 } })
    expect(rows.map(row => row.symbol)).toEqual(['NVDA', 'MSFT', 'AMD'])
    expect(rows[0]).toMatchObject({ sourceWatchlistId: 1, values: { last: 140, change: 0.02 } })
  })

  it('uses the intersection as the seed when no union is configured', () => {
    const rows = buildComboWatchlistRows(lists, {
      stable_key: 'intersection-only', name: 'Intersection only', payload: { intersection_watchlist_ids: [1, 2] },
    }, {})
    expect(rows.map(row => row.symbol)).toEqual(['NVDA'])
    expect(rows[0].sourceWatchlistId).toBe(1)
  })
})
