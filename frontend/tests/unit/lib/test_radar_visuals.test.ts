import { describe, expect, it } from 'vitest'

import {
  buildRadarDrawingOverlays,
  buildRadarIndicatorOverlays,
  mergeChartDrawingsWithRadar,
  mergeChartIndicatorsWithRadar,
} from '@/lib/radar/visuals'
import type { ChartDrawing, IndicatorConfig, RadarDetection } from '@/types'

function detection(overrides: Partial<RadarDetection> = {}): RadarDetection {
  return {
    id: 1,
    run_id: 1,
    instrument_id: 7,
    instrument_symbol: 'AAPL',
    instrument_name: 'Apple',
    timeframe: 'D1',
    setup_type: 'breakout',
    state: 'confirmed',
    score: 0.88,
    observed_at: '2026-05-05T12:00:00Z',
    signal_at: '2026-05-05T12:00:00Z',
    context_at: '2026-05-04T12:00:00Z',
    fresh_until: '2026-05-10T12:00:00Z',
    thread_id: 4,
    thread_event_index: 1,
    key_level_price: 101,
    entry_price: 102,
    invalidation_price: 99,
    target_price: 108,
    outcome_status: 'open',
    outcome_last_evaluated_at: '2026-05-05T12:00:00Z',
    bars_since_signal: 0,
    max_favorable_excursion_pct: null,
    max_adverse_excursion_pct: null,
    target_hit_at: null,
    invalidated_at: null,
    summary: 'Breakout setup',
    invalidation_hint: 'Lose 99',
    score_factors: {},
    evidence: {
      overlays: [],
      indicator_visuals: [],
      drawing_visuals: [],
      metrics: {},
      structures: [],
    },
    created_at: '2026-05-05T12:00:01Z',
    updated_at: '2026-05-05T12:00:01Z',
    ...overrides,
  }
}

describe('radar visuals helpers', () => {
  it('reuses matching user indicators and only overlays missing radar indicators', () => {
    const userIndicators: IndicatorConfig[] = [
      { type: 'ema', params: { period: 20 }, style: { color: '#26a69a', lineWidth: 2 }, pane: 'main' },
    ]
    const radarIndicators = buildRadarIndicatorOverlays([
      detection({
        evidence: {
          overlays: [],
          indicator_visuals: [
            { type: 'ema', params: { period: 20 }, style: { color: '#26a69a', lineWidth: 2 }, pane: 'main', role: 'ema20' },
            { type: 'avwap', params: { anchor_timestamp: 1746403200 }, style: { color: '#c77dff', lineWidth: 2 }, pane: 'main', role: 'avwap_primary' },
          ],
          drawing_visuals: [],
          metrics: {},
          structures: [],
        },
      }),
    ], 1)

    const merged = mergeChartIndicatorsWithRadar(userIndicators, radarIndicators)

    expect(merged).toHaveLength(2)
    expect((merged[0] as any).__radarSource).toBe('reuse')
    expect((merged[1] as any).__radarSource).toBe('overlay')
    expect(merged[1].type).toBe('avwap')
  })

  it('reuses equivalent user drawings and only adds missing radar drawings', () => {
    const userDrawings: ChartDrawing[] = [
      {
        id: 12,
        instrument_id: 7,
        timeframe: 'D1',
        pin_to_all: false,
        indicator_key: null,
        drawing_type: 'rectangle',
        label: 'Resistance zone',
        data: { points: [{ time: 1746316800, price: 112 }, { time: 1746662400, price: 110 }], filled: true },
        style: { color: '#ef5350', lineWidth: 1, opacity: 0.6, filled: true },
        is_visible: true,
        is_locked: false,
        position: 0,
        created_at: '',
        updated_at: '',
      },
    ]

    const radarDrawings = buildRadarDrawingOverlays([
      detection({
        evidence: {
          overlays: [],
          indicator_visuals: [],
          drawing_visuals: [
            {
              drawing_type: 'rectangle',
              data: { points: [{ time: 1746316800, price: 112 }, { time: 1746662400, price: 110 }], filled: true },
              style: { color: '#ef5350', lineWidth: 1, opacity: 0.6, filled: true },
              is_visible: true,
              is_locked: true,
              source_role: 'resistance',
              source_tag: 'radar',
            },
            {
              drawing_type: 'horizontal_line',
              data: { points: [{ time: 1746316800, price: 99 }] },
              style: { color: '#ef5350', lineWidth: 1, opacity: 0.9 },
              is_visible: true,
              is_locked: true,
              source_role: 'invalidation',
              source_tag: 'radar',
              label: 'Invalidation',
            },
          ],
          metrics: {},
          structures: [],
        },
      }),
    ], 1)

    const merged = mergeChartDrawingsWithRadar(userDrawings, radarDrawings, {
      instrumentId: 7,
      timeframe: 'D1',
    })

    expect(merged).toHaveLength(2)
    expect((merged[0] as any).__radarSource).toBe('reuse')
    expect((merged[1] as any).__radarSource).toBe('overlay')
    expect(merged[1].drawing_type).toBe('horizontal_line')
  })
})
