import { describe, expect, it } from 'vitest'
import { layoutMarketMapCells } from '@/lib/workstation/marketMap'

describe('market map layout', () => {
  it('fills a deterministic rectangle and preserves area ordering', () => {
    const cells = [
      { instrument_id: 1, symbol: 'A', name: 'A', group_path: [], area_value: 3, color_value: 0.1, coverage: 1, warnings: [] },
      { instrument_id: 2, symbol: 'B', name: 'B', group_path: [], area_value: 1, color_value: -0.1, coverage: 1, warnings: [] },
    ]
    const result = layoutMarketMapCells(cells)
    expect(result).toHaveLength(2)
    expect(result[0].width).toBeGreaterThan(result[1].width)
    expect(result[0].x + result[0].width).toBeCloseTo(75)
    expect(result[1].x + result[1].width).toBeCloseTo(100)
    expect(result.every(cell => cell.x >= 0 && cell.y >= 0 && cell.width > 0 && cell.height > 0)).toBe(true)
  })

  it('does not invent geometry for missing or non-positive area values', () => {
    const cells = [
      { instrument_id: 1, symbol: 'A', name: 'A', group_path: [], area_value: 2, color_value: 0.1, coverage: 1, warnings: [] },
      { instrument_id: 2, symbol: 'B', name: 'B', group_path: [], area_value: null, color_value: 0.2, coverage: 0, warnings: [] },
      { instrument_id: 3, symbol: 'C', name: 'C', group_path: [], area_value: 0, color_value: -0.1, coverage: 0, warnings: [] },
    ]
    const result = layoutMarketMapCells(cells)
    expect(result.map(cell => cell.symbol)).toEqual(['A'])
    expect(result[0].x + result[0].width).toBeCloseTo(100)
  })
})
