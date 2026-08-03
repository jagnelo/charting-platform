import { describe, expect, it } from 'vitest'
import { CHART_PLOT_DRAG_MIME, createChartPlotDragPayload, createTechnicalConditionDragPayload, readAnalysisDrag, readChartPlotDrag, writeChartPlotDrag, writeTechnicalConditionDrag } from '@/lib/workstation/plotDrag'

function transfer() {
  const values = new Map<string, string>()
  return {
    values,
    effectAllowed: '',
    setData: (type: string, value: string) => values.set(type, value),
    getData: (type: string) => values.get(type) ?? '',
  } as unknown as DataTransfer & { values: Map<string, string> }
}

describe('plot drag payloads', () => {
  it('round-trips only serializable indicator metadata', () => {
    const dataTransfer = transfer()
    const payload = createChartPlotDragPayload({ type: 'rsi', params: { period: 14 }, style: { color: '#fff', lineWidth: 1 }, pane: 'separate' }, 'D1', 'chart-source')
    expect(writeChartPlotDrag(dataTransfer, payload)).toBe(true)
    expect(readChartPlotDrag(dataTransfer)).toMatchObject({ kind: 'chart-plot', version: 1, indicator: { type: 'rsi', params: { period: 14 }, timeframe: 'D1', sourceWindowKey: 'chart-source' } })
    expect(dataTransfer.effectAllowed).toBe('copy')
  })

  it('rejects malformed, unknown-version, and oversized drops', () => {
    const malformed = transfer()
    malformed.setData(CHART_PLOT_DRAG_MIME, JSON.stringify({ version: 1, kind: 'chart-plot', indicator: { type: 'not-real', params: {}, timeframe: 'D1', label: 'bad', sourceWindowKey: 'source' } }))
    expect(readChartPlotDrag(malformed)).toBeNull()
    malformed.setData(CHART_PLOT_DRAG_MIME, JSON.stringify({ version: 9, kind: 'chart-plot', indicator: {} }))
    expect(readChartPlotDrag(malformed)).toBeNull()
    malformed.setData(CHART_PLOT_DRAG_MIME, 'x'.repeat(16_385))
    expect(readChartPlotDrag(malformed)).toBeNull()
  })

  it('round-trips a technical condition for Boolean-column drops', () => {
    const dataTransfer = transfer()
    const payload = createTechnicalConditionDragPayload({ operator: 'AND', conditions: [{ type: 'indicator_threshold', indicator: 'rsi', params: { period: 14 }, op: 'gt', value: 50 }] }, 'D1', 'scan-source', 'RSI above 50')
    expect(writeTechnicalConditionDrag(dataTransfer, payload)).toBe(true)
    expect(readAnalysisDrag(dataTransfer)).toMatchObject({ kind: 'technical-condition', timeframe: 'D1', label: 'RSI above 50', sourceWindowKey: 'scan-source', condition: { operator: 'AND' } })
  })
})
