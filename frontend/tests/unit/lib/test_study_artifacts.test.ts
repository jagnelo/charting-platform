import { describe, expect, it } from 'vitest'
import { normalizeStudyDashboardPanels } from '@/lib/workstation/studyArtifacts'

describe('study dashboard artifact validation', () => {
  it('accepts a non-empty dashboard with integer spans within the twelve-column grid', () => {
    expect(normalizeStudyDashboardPanels({ panels: [{ artifact: 'streak', title: 'Current streak', span: 4 }, { artifact: 'distribution', title: 'Distribution', span: 8 }] })).toEqual([
      { artifact: 'streak', title: 'Current streak', span: 4 },
      { artifact: 'distribution', title: 'Distribution', span: 8 },
    ])
  })

  it.each([
    ['missing panels', {}],
    ['empty panels', { panels: [] }],
    ['empty artifact name', { panels: [{ artifact: ' ', title: 'Title', span: 4 }] }],
    ['empty title', { panels: [{ artifact: 'streak', title: '', span: 4 }] }],
    ['zero span', { panels: [{ artifact: 'streak', title: 'Title', span: 0 }] }],
    ['fractional span', { panels: [{ artifact: 'streak', title: 'Title', span: 1.5 }] }],
    ['span beyond grid', { panels: [{ artifact: 'streak', title: 'Title', span: 13 }] }],
    ['non-finite span', { panels: [{ artifact: 'streak', title: 'Title', span: Number.POSITIVE_INFINITY }] }],
    ['mixed valid and invalid panels', { panels: [{ artifact: 'streak', title: 'Title', span: 4 }, { artifact: 'broken', title: 'Broken', span: 20 }] }],
  ])('rejects %s without leaking invalid CSS layout data', (_label, value) => {
    expect(normalizeStudyDashboardPanels(value)).toBeNull()
  })
})
