import { describe, expect, it } from 'vitest'
import { layoutMarketMapCells, layoutMarketMapGroups } from '@/lib/workstation/marketMap'

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

  it('partitions grouped universes before laying out their members', () => {
    const cells = [
      { instrument_id: 1, symbol: 'A', name: 'A', group_path: ['Technology', 'Software'], area_value: 3, color_value: 0.1, coverage: 1, warnings: [] },
      { instrument_id: 2, symbol: 'B', name: 'B', group_path: ['Technology', 'Hardware'], area_value: 1, color_value: -0.1, coverage: 1, warnings: [] },
      { instrument_id: 3, symbol: 'C', name: 'C', group_path: ['Health Care', 'Devices'], area_value: 2, color_value: 0.2, coverage: 1, warnings: [] },
    ]
    const result = layoutMarketMapCells(cells)
    const technology = result.filter(cell => cell.group_path[0] === 'Technology')
    const healthCare = result.filter(cell => cell.group_path[0] === 'Health Care')
    expect(technology).toHaveLength(2)
    expect(healthCare).toHaveLength(1)
    expect(technology.every(cell => cell.x >= 0 && cell.x + cell.width <= 100 && cell.y >= 0 && cell.y + cell.height <= 100)).toBe(true)
    const technologyArea = technology.reduce((sum, cell) => sum + cell.width * cell.height, 0)
    expect(healthCare[0].width * healthCare[0].height).toBeLessThan(technologyArea)
    const sameColumn = Math.abs(technology[0].x - technology[1].x) < 0.001
    const sameRow = Math.abs(technology[0].y - technology[1].y) < 0.001
    expect(sameColumn || sameRow).toBe(true)
  })

  it('exposes deterministic top-level group frames for grouped universes', () => {
    const cells = [
      { instrument_id: 1, symbol: 'A', name: 'A', group_path: ['Technology', 'Software'], area_value: 3, color_value: 0.1, coverage: 1, warnings: [] },
      { instrument_id: 2, symbol: 'B', name: 'B', group_path: ['Technology', 'Hardware'], area_value: 1, color_value: -0.1, coverage: 1, warnings: [] },
      { instrument_id: 3, symbol: 'C', name: 'C', group_path: ['Health Care', 'Devices'], area_value: 2, color_value: 0.2, coverage: 1, warnings: [] },
      { instrument_id: 4, symbol: 'D', name: 'D', group_path: [], area_value: 1, color_value: 0, coverage: 1, warnings: [] },
    ]
    const groups = layoutMarketMapGroups(cells)
    expect(groups).toHaveLength(5)
    expect(groups.filter(group => group.level === 0).map(group => group.label).sort()).toEqual(['Health Care', 'Technology'])
    expect(groups.filter(group => group.level === 1).map(group => group.label).sort()).toEqual(['Devices', 'Hardware', 'Software'])
    expect(groups.find(group => group.label === 'Software')?.parent_key).toBe(groups.find(group => group.label === 'Technology')?.key)
    expect(groups.find(group => group.label === 'Devices')?.parent_key).toBe(groups.find(group => group.label === 'Health Care')?.key)
    expect(groups.every(group => group.x >= 0 && group.y >= 0 && group.width > 0 && group.height > 0 && group.x + group.width <= 100.001 && group.y + group.height <= 100.001)).toBe(true)
    expect(groups.find(group => group.label === 'Technology')!.width * groups.find(group => group.label === 'Technology')!.height).toBeGreaterThan(groups.find(group => group.label === 'Health Care')!.width * groups.find(group => group.label === 'Health Care')!.height)
  })

  it('does not expose a frame for a single ungrouped source', () => {
    expect(layoutMarketMapGroups([
      { instrument_id: 1, symbol: 'A', name: 'A', group_path: [], area_value: 1, color_value: 0, coverage: 1, warnings: [] },
    ])).toEqual([])
  })
})
