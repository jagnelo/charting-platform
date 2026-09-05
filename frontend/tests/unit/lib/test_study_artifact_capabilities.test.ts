import { describe, expect, it } from 'vitest'
import { studyArtifactCapability } from '@/lib/workstation/studyArtifactCapabilities'

describe('study artifact promotion capabilities', () => {
  it('describes compatible scalar, boolean, series, range, and event targets', () => {
    expect(studyArtifactCapability('scalar')?.targets).toEqual(['watchlist column'])
    expect(studyArtifactCapability('boolean')?.targets).toEqual([
      'watchlist column',
      'watchlist filter',
      'scan',
      'Market Gauge',
      'alert',
    ])
    expect(studyArtifactCapability('series')?.targets).toEqual(['chart plot', 'latest-value watchlist column', 'thresholded Boolean condition'])
    expect(studyArtifactCapability('range')?.note).toContain('bounds remain source-only')
    expect(studyArtifactCapability('events')?.targets).toEqual(['watchlist filter', 'alert', 'Strategy signal'])
  })

  it('keeps structured visual shapes view/export-only', () => {
    for (const type of ['table', 'bar', 'histogram', 'scatter', 'heatmap', 'dashboard']) {
      const capability = studyArtifactCapability(type)
      expect(capability?.targets).toEqual([])
      expect(capability?.note).toMatch(/^View\/export only:/)
    }
  })

  it('returns no capability claim for an unknown artifact type', () => {
    expect(studyArtifactCapability('future_shape')).toBeNull()
  })
})
