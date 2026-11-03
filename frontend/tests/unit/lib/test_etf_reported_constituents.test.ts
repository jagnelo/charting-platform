import { describe, expect, it } from 'vitest'
import type { ETFHolding, ETFHoldingsSnapshot } from '@/types'
import {
  createETFHoldingDrilldownContext,
  isCurrentETFHoldingSelection,
  holdingDrilldownRouteQuery,
  parseETFHoldingDrilldownRouteQuery,
} from '@/lib/etfHoldingDrilldown'
import { etfHoldingWatchlistRowKey, projectReportedETFHoldings } from '@/lib/workstation/etfReportedConstituents'

const snapshot: ETFHoldingsSnapshot = {
  id: 510,
  etf_profile_id: 81,
  etf_instrument_id: 82,
  etf_symbol: 'IGV',
  etf_name: 'Software ETF fixture',
  composition_date: '2026-10-31',
  known_at: '2026-11-01T14:30:00Z',
  provenance: 'controlled_fixture_only',
  source_provider: 'test-fixture',
  source_quality: 'controlled_fixture',
  completeness_status: 'complete',
  row_count: 3,
  resolved_count: 0,
  unresolved_count: 3,
  parser_version: 'fixture-v1',
  holdings: [],
}

const holdings: ETFHolding[] = [
  {
    id: 610,
    snapshot_id: snapshot.id,
    constituent_instrument_id: null,
    constituent_symbol: null,
    constituent_name: null,
    reported_symbol: 'UNXQ',
    reported_name: 'Unlisted Example Software Corp',
    position: 1,
    weight: '0.1275',
    holding_type: 'equity',
    row_type: 'security',
    source_row_id: 'fixture-row-610',
    is_resolved: false,
  },
  {
    id: 611,
    snapshot_id: snapshot.id,
    constituent_instrument_id: null,
    constituent_symbol: null,
    constituent_name: null,
    reported_symbol: 'FUTURE-A',
    reported_name: 'Named software index future',
    position: 2,
    weight: '0.005',
    holding_type: 'future',
    row_type: 'derivative',
    source_row_id: 'fixture-row-611',
    is_resolved: false,
  },
  {
    id: 612,
    snapshot_id: snapshot.id,
    constituent_instrument_id: 99,
    constituent_symbol: 'AAPL',
    constituent_name: 'Apple Inc.',
    reported_symbol: 'AAPL-R',
    reported_name: 'Apple Inc.',
    position: 3,
    weight: 0.09,
    holding_type: 'equity',
    row_type: 'security',
    source_row_id: 'fixture-row-612',
    is_resolved: true,
  },
  {
    id: 613,
    snapshot_id: snapshot.id,
    constituent_instrument_id: null,
    constituent_symbol: null,
    constituent_name: null,
    reported_symbol: null,
    reported_name: 'Cash and equivalents',
    position: 4,
    weight: '0.0025',
    holding_type: 'cash',
    row_type: 'cash',
    source_row_id: 'fixture-row-613',
    is_resolved: false,
  },
]

describe('reported ETF constituent projection', () => {
  it('keeps reported snapshot rows visible when no holding has a canonical equity identity', () => {
    const fixtureHoldings = [holdings[0]!, holdings[1]!, holdings[3]!]
    const rows = projectReportedETFHoldings('IGV', snapshot.id, fixtureHoldings)

    expect(fixtureHoldings.every(row => !row.is_resolved && row.constituent_instrument_id == null)).toBe(true)
    expect(rows).toEqual([
      {
        rowKey: etfHoldingWatchlistRowKey('IGV', snapshot.id, 610),
        instrumentId: null,
        symbol: 'UNXQ',
        name: 'Unlisted Example Software Corp',
        values: { weight: 0.1275, holding_type: 'security · equity', resolution: 'Equity identity not resolved' },
      },
      {
        rowKey: etfHoldingWatchlistRowKey('IGV', snapshot.id, 611),
        instrumentId: null,
        symbol: 'FUTURE-A',
        name: 'Named software index future',
        values: { weight: 0.005, holding_type: 'derivative · future', resolution: 'Not eligible for equity charting' },
      },
      {
        rowKey: etfHoldingWatchlistRowKey('IGV', snapshot.id, 613),
        instrumentId: null,
        symbol: '—',
        name: 'Cash and equivalents',
        values: { weight: 0.0025, holding_type: 'cash · cash', resolution: 'Not eligible for equity charting' },
      },
    ])
    expect(new Set(rows.map(row => row.rowKey)).size).toBe(3)
  })

  it('exposes only a confirmed canonical equity as chartable and retains the reported rows', () => {
    const rows = projectReportedETFHoldings('IGV', snapshot.id, holdings)
    expect(rows.map(row => row.symbol)).toEqual(['UNXQ', 'FUTURE-A', 'AAPL-R', '—'])
    expect(rows.map(row => row.instrumentId)).toEqual([null, null, 99, null])
    expect(rows[2]?.values).toMatchObject({ holding_type: 'security · equity', resolution: 'Canonical equity resolved' })
    expect(rows[3]?.values).toMatchObject({ holding_type: 'cash · cash', resolution: 'Not eligible for equity charting' })
  })

  it('rejects a late resolution tied to an old ETF snapshot or a different selected holding', () => {
    const context = createETFHoldingDrilldownContext(snapshot, holdings[0]!, 1234, 'UNXQ')
    const nextSnapshot = { ...snapshot, id: snapshot.id + 1 }
    expect(isCurrentETFHoldingSelection(context, 'IGV', snapshot, holdings[0])).toBe(true)
    expect(isCurrentETFHoldingSelection(context, 'OIH', snapshot, holdings[0])).toBe(false)
    expect(isCurrentETFHoldingSelection(context, 'IGV', nextSnapshot, holdings[0])).toBe(false)
    expect(isCurrentETFHoldingSelection(context, 'IGV', snapshot, holdings[1])).toBe(false)
  })

  it('hydrates chart acquisition intent only from a complete holding-lineage route', () => {
    const context = createETFHoldingDrilldownContext(snapshot, holdings[0]!, 1234, 'UNXQ')
    const query = holdingDrilldownRouteQuery(context)
    expect(parseETFHoldingDrilldownRouteQuery(query, 'UNXQ')).toEqual(context)
    expect(parseETFHoldingDrilldownRouteQuery({ holding_snapshot_id: '510' }, 'UNXQ')).toBeNull()
    expect(parseETFHoldingDrilldownRouteQuery(query, '')).toBeNull()
  })
})
