import { describe, expect, it } from 'vitest'
import { describeStudyArtifact } from '@/lib/workstation/studyArtifactAccessibility'

describe('study artifact accessibility descriptions', () => {
  it('describes aligned series coverage and missing observations', () => {
    expect(describeStudyArtifact({
      name: 'Trend',
      artifact_type: 'series',
      payload: { value: { timestamps: ['2026-01-01', '2026-01-02'], values: [null, 11] } },
    })).toBe('Trend series result with 2 observations, 1 finite and 1 missing from 2026-01-01 through 2026-01-02.')
  })

  it('keeps range center availability explicit', () => {
    expect(describeStudyArtifact({
      name: 'Confidence',
      artifact_type: 'range',
      payload: { value: { timestamps: ['2026-01-01', '2026-01-02'], lower: [1, 2], upper: [3, 4], center: [2, 3] } },
    })).toContain('with an aligned center series')
    expect(describeStudyArtifact({
      name: 'Bounds',
      artifact_type: 'range',
      payload: { value: { timestamps: ['2026-01-01'], lower: [1], upper: [3] } },
    })).toContain('without an aligned center series')
  })

  it('summarizes structured table, events, and matrix shapes without flattening payloads', () => {
    expect(describeStudyArtifact({ name: 'Rows', artifact_type: 'table', payload: { value: [{ symbol: 'SPY', value: 1 }] } })).toContain('1 rows and 2 columns')
    expect(describeStudyArtifact({ name: 'Signals', artifact_type: 'events', payload: { value: [{ symbol: 'SPY', timestamp: '2026-01-01' }, { symbol: 'QQQ', timestamp: '2026-01-02' }] } })).toContain('2 occurrences across 2 symbols')
    expect(describeStudyArtifact({ name: 'Matrix', artifact_type: 'heatmap', payload: { value: { rows: ['A', 'B'], columns: ['X', 'Y'], values: [[1, 2], [3, 4]] } } })).toContain('2 rows by 2 columns')
  })

  it('keeps unknown shapes explicitly inspectable', () => {
    expect(describeStudyArtifact({ name: 'Future', artifact_type: 'future_shape', payload: { value: { raw: true } } })).toBe('Future future_shape result; inspect the structured payload for details.')
  })
})
