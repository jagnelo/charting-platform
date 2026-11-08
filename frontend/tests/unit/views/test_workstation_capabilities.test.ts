import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { workspaceToolRole, type OpenableToolDefinition } from '@/stores/workspace'

// Contract fixtures mirror the authenticated server catalogue shape. Product
// menu contents are loaded from that endpoint rather than a second UI registry.
const supported: OpenableToolDefinition[] = [
  { key: 'chart', tool_type: 'chart', title: 'Chart', instance_prefix: 'chart', configuration: { symbol: 'SPY', timeframe: 'D1' } },
  { key: 'watchlist', tool_type: 'watchlist', title: 'WatchList', instance_prefix: 'watchlist', configuration: { personal: true, watchlist_id: null } },
  { key: 'favorites', tool_type: 'watchlist', title: 'My Favorites', instance_prefix: 'favorites', configuration: { personal: true, favorites: true } },
  { key: 'benchmark-list', tool_type: 'watchlist', title: 'Benchmarks', instance_prefix: 'benchmark-list', configuration: { market_group: 'us-benchmarks' } },
  { key: 'sector-list', tool_type: 'watchlist', title: 'S&P 500 Sectors', instance_prefix: 'sector-list', configuration: { market_group: 'sp500-sectors' } },
  { key: 'industry-list', tool_type: 'watchlist', title: 'Industries', instance_prefix: 'industry-list', configuration: { market_group: 'selected-sector-industries' } },
  { key: 'constituent-list', tool_type: 'watchlist', title: 'Constituents', instance_prefix: 'constituent-list', configuration: { market_group: 'selected-industry-constituents' } },
  { key: 'ratio-chart', tool_type: 'chart', title: 'Relative Strength', instance_prefix: 'ratio-chart', configuration: { expression: '=SPY/RSP', timeframe: 'D1', auto_ratio: true } },
  { key: 'relative-rotation', tool_type: 'relative_rotation', title: 'Relative Rotation', instance_prefix: 'relative-rotation', configuration: { group_key: 'sp500-sectors', benchmark: 'SPY', timeframe: 'D1', sampling: 1, lookback: 20, tail_length: 10, adjusted: true } },
  { key: 'breadth', tool_type: 'breadth', title: 'Market Breadth', instance_prefix: 'breadth', configuration: { group_key: 'sp500-sectors' } },
  { key: 'scan', tool_type: 'scan', title: 'EasyScan', instance_prefix: 'easy-scan', configuration: { scope: 'saved-conditions' } },
  { key: 'gauge', tool_type: 'gauge', title: 'Market Gauge', instance_prefix: 'market-gauge', configuration: { scope: 'saved-scans' } },
  { key: 'study-lab', tool_type: 'study_lab', title: 'Study Lab', instance_prefix: 'study-lab', configuration: { symbol: 'SPY' } },
  { key: 'market-map', tool_type: 'market_map', title: 'Market Map', instance_prefix: 'market-map', configuration: { group_by: 'sector_industry', period: '1D', area_metric: 'market_cap', color_metric: 'return' } },
  { key: 'notes', tool_type: 'notes', title: 'Notes', instance_prefix: 'notes', configuration: { scope: 'active-instrument' } },
  { key: 'alerts', tool_type: 'alerts', title: 'Alerts', instance_prefix: 'alerts', configuration: { scope: 'active-instrument' } },
  { key: 'code-library', tool_type: 'code_library', title: 'Python Library', instance_prefix: 'code-library', configuration: {} },
  { key: 'technical-summary', tool_type: 'technical_summary', title: 'Technicals', instance_prefix: 'technical-summary', configuration: { scope: 'selected' } },
  { key: 'coverage', tool_type: 'coverage', title: 'Coverage', instance_prefix: 'coverage', configuration: { scope: 'selected' } },
  { key: 'report', tool_type: 'report', title: 'Instrument Report', instance_prefix: 'report', configuration: {} },
  { key: 'research-results', tool_type: 'research_results', title: 'Study Results', instance_prefix: 'research-results', configuration: {} },
]

describe('primary workstation capability boundary', () => {
  it('classifies all current catalogue and factory panels by concrete type and semantic configuration', () => {
    const matrix = JSON.parse(readFileSync(resolve(process.cwd(), '../ops/workstreams/feat-tc2000-frontend-rework/journey-matrix.json'), 'utf8')) as {
      add_tool_definitions: Array<{ key: string; tool_type: string; configuration: Record<string, unknown> }>
      factory_layouts: Array<{ panels: Array<{ instance_key: string; tool_type: string; configuration: Record<string, unknown> }> }>
    }
    const panels = matrix.factory_layouts.flatMap(layout => layout.panels)
    expect(matrix.add_tool_definitions).toHaveLength(21)
    expect(panels).toHaveLength(38)
    const records = [
      ...matrix.add_tool_definitions.map(tool => ({ instance_key: tool.key, tool_type: tool.tool_type, configuration: tool.configuration })),
      ...panels,
    ]
    const expectedRole = (tool: typeof records[number]) => {
      if (tool.tool_type === 'chart') return tool.configuration.auto_ratio === true || tool.instance_key.startsWith('ratio-chart') ? 'relative-strength' : null
      if (tool.tool_type !== 'watchlist') return null
      const role = tool.configuration.workspace_role
      if (['benchmark-universe', 'sector-universe', 'industry-universe', 'constituent-universe'].includes(String(role))) return role
      const group = tool.configuration.market_group
      if (group === 'us-benchmarks') return 'benchmark-universe'
      if (group === 'sp500-sectors') return 'sector-universe'
      if (group === 'selected-sector-industries') return 'industry-universe'
      if (group === 'selected-industry-constituents') return 'constituent-universe'
      const key = tool.instance_key.toLowerCase()
      if (['benchmark-list'].includes(key)) return 'benchmark-universe'
      if (['sector-list', 'sectors'].includes(key)) return 'sector-universe'
      if (['industry-list', 'industries'].includes(key)) return 'industry-universe'
      if (['constituent-list', 'components'].includes(key)) return 'constituent-universe'
      return null
    }
    for (const tool of records) {
      expect(workspaceToolRole(tool), `${tool.tool_type}:${tool.instance_key}`).toBe(expectedRole(tool))
    }
    expect(workspaceToolRole({
      instance_key: 'sector-comparison', tool_type: 'chart',
      configuration: { workspace_role: 'sector-universe', market_group: 'sp500-sectors' },
    })).toBeNull()
    expect(workspaceToolRole({
      instance_key: 'industry-list-snapshot-copy', tool_type: 'watchlist', configuration: {},
    })).toBe('industry-universe')
  })

  it('keeps supported analysis and research tool types represented by the canonical contract', () => {
    const registered = new Set(supported.map(tool => tool.tool_type))
    expect(registered).toEqual(new Set([
      'chart', 'watchlist', 'notes', 'alerts', 'scan', 'gauge', 'study_lab', 'research_results',
      'relative_rotation', 'breadth', 'market_map', 'technical_summary', 'coverage', 'report', 'code_library',
    ]))
    for (const excluded of ['brokerage', 'trading', 'options', 'news', 'analyst-ratings', 'earnings', 'financial-statements', 'consolidated-realtime']) {
      expect(registered.has(excluded)).toBe(false)
    }
  })

  it('keeps favorites separate and preserves semantic roles for copied factory variants', () => {
    const favorites = supported.find(tool => tool.key === 'favorites')
    expect(favorites).toMatchObject({
      tool_type: 'watchlist',
      instance_prefix: 'favorites',
      configuration: { personal: true, favorites: true },
    })
    const roles = supported.filter(tool => ['benchmark-list', 'sector-list', 'industry-list', 'constituent-list', 'ratio-chart'].includes(tool.key))
      .map(tool => workspaceToolRole({ instance_key: `${tool.instance_prefix}-copy`, tool_type: tool.tool_type, configuration: tool.configuration }))
    expect(roles).toEqual(['benchmark-universe', 'sector-universe', 'industry-universe', 'constituent-universe', 'relative-strength'])
  })
})
