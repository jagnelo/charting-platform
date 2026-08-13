import { describe, expect, it, vi } from 'vitest'
import { CHART_PLOT_DRAG_MIME, clearAnalysisDrag, createChartPlotDragPayload, createPythonPlotDragPayload, createTechnicalConditionDragPayload, pythonColumnFromPlot, readAnalysisDrag, readChartPlotDrag, scheduleAnalysisDragCleanup, writeChartPlotDrag, writePythonPlotDrag, writeTechnicalConditionDrag } from '@/lib/workstation/plotDrag'

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

  it('round-trips a Python series plot and produces a watchlist column contract', () => {
    const dataTransfer = transfer()
    const payload = createPythonPlotDragPayload({ code_version_id: 91, name: 'Breadth series', color: '#4dd0e1', timeframe: 'W1' }, 'D1', 'chart-source')
    expect(payload).not.toBeNull()
    expect(writePythonPlotDrag(dataTransfer, payload!)).toBe(true)
    expect(readAnalysisDrag(dataTransfer)).toMatchObject({ kind: 'python-plot', python: { codeVersionId: 91, name: 'Breadth series', color: '#4dd0e1', timeframe: 'W1', sourceWindowKey: 'chart-source' } })
    expect(pythonColumnFromPlot(payload!)).toEqual({ code_version_id: 91, name: 'Breadth series', timeframe: 'W1' })
  })

  it('falls back to the active same-document payload when drop MIME data is unavailable', () => {
    const source = transfer()
    const payload = createChartPlotDragPayload({ type: 'rsi', params: { period: 14 }, style: { color: '#fff', lineWidth: 1 }, pane: 'separate' }, 'D1', 'chart-source')
    expect(writeChartPlotDrag(source, payload)).toBe(true)

    const unavailable = transfer()
    expect(readAnalysisDrag(unavailable)).toMatchObject({ kind: 'chart-plot', indicator: { type: 'rsi' } })
    clearAnalysisDrag()
    expect(readAnalysisDrag(unavailable)).toBeNull()
  })

  it('keeps the same-document fallback through dragend grace, then expires it', () => {
    vi.useFakeTimers()
    try {
      const source = transfer()
      const payload = createChartPlotDragPayload({ type: 'rsi', params: { period: 14 }, style: { color: '#fff', lineWidth: 1 }, pane: 'separate' }, 'D1', 'chart-source')
      expect(writeChartPlotDrag(source, payload)).toBe(true)
      scheduleAnalysisDragCleanup(250)
      expect(readAnalysisDrag(transfer())).toMatchObject({ kind: 'chart-plot', indicator: { type: 'rsi' } })
      vi.advanceTimersByTime(249)
      expect(readAnalysisDrag(transfer())).toMatchObject({ kind: 'chart-plot', indicator: { type: 'rsi' } })
      vi.advanceTimersByTime(1)
      expect(readAnalysisDrag(transfer())).toBeNull()
    } finally {
      clearAnalysisDrag()
      vi.useRealTimers()
    }
  })
})
