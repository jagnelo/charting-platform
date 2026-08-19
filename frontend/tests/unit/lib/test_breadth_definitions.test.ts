import { describe, expect, it } from 'vitest'
import { breadthPythonLiteral, buildBreadthStudyAssetPayload, breadthDefinitionStableKey } from '@/lib/workstation/breadthDefinitions'

describe('breadth definition persistence', () => {
  it('serializes the JSON AST as valid Python literals', () => {
    expect(breadthPythonLiteral({ enabled: true, threshold: 0.01, values: [null, 'SPY'] })).toBe("{\"enabled\": True, \"threshold\": 0.01, \"values\": [None, \"SPY\"]}")
  })

  it('creates a Study Lab asset that retains the locked source and predicate', () => {
    const definition = {
      version: 1,
      universe: { kind: 'watchlist', key: 'etf-holdings:SPY', point_in_time: true },
      condition: { kind: 'within_52_week_high', params: { lookback: 252, threshold: 0.01, direction: 'high' } },
      timeframe: 'D1',
      adjusted: true,
    }
    const payload = buildBreadthStudyAssetPayload('SPY breadth', definition, 1_725_000_000_000)

    expect(payload.stable_key).toBe(breadthDefinitionStableKey('SPY breadth', 1_725_000_000_000))
    expect(payload.kind).toBe('study')
    expect(payload.initial_version.output_contract).toBe('study')
    expect(payload.initial_version.source).toContain("research.breadth_condition(dataset, condition, True)")
    expect(payload.initial_version.source).toContain('etf-holdings:SPY')
    expect(payload.initial_version.default_parameters).toMatchObject({
      universe_source_id: 'etf-holdings:SPY',
      timeframe: 'D1',
      adjustment: 'split_adjusted',
      breadth_definition: definition,
    })
  })
})
