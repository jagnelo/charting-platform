export type StudyArtifactCapability = {
  targets: readonly string[]
  note: string
}

/**
 * The persisted-result promotion matrix is deliberately explicit. An
 * artifact may be rendered and exported without being safe to reinterpret as
 * a different workstation value. Keep this table aligned with the backend
 * asset contracts and prefer a visible limitation over a lossy adapter.
 */
export const STUDY_ARTIFACT_CAPABILITIES: Readonly<Record<string, StudyArtifactCapability>> = {
  scalar: {
    targets: ['watchlist column'],
    note: 'Compatible target: watchlist column.',
  },
  boolean: {
    targets: ['watchlist column', 'watchlist filter', 'scan', 'Market Gauge', 'alert'],
    note: 'Compatible targets: watchlist column, filter, scan, Market Gauge, and alert.',
  },
  series: {
    targets: ['chart plot', 'latest-value watchlist column', 'thresholded Boolean condition'],
    note: 'Compatible targets: chart plot, latest-value watchlist column, or a thresholded Boolean condition when a finite observation is present.',
  },
  range: {
    targets: ['center chart plot'],
    note: 'Compatible target: center chart plot when an aligned finite center series is present; bounds remain source-only.',
  },
  events: {
    targets: ['watchlist filter', 'alert', 'Strategy signal'],
    note: 'Structured-study event targets: watchlist filter, alert, and Strategy signal; all preserve the selected artifact and source lineage.',
  },
  table: {
    targets: [],
    note: 'View/export only: table rows cannot be safely converted to a per-symbol column or time-series plot.',
  },
  bar: {
    targets: [],
    note: 'View/export only: categorical labels are not a time-series chart contract.',
  },
  histogram: {
    targets: [],
    note: 'View/export only: bucket counts must remain a histogram, not a chart series.',
  },
  scatter: {
    targets: [],
    note: 'View/export only: paired x/y observations have no compatible watchlist or chart-plot target.',
  },
  heatmap: {
    targets: [],
    note: 'View/export only: matrix dimensions and cell meaning must remain intact.',
  },
  dashboard: {
    targets: [],
    note: 'View/export only: panel layout is a composed result and is not flattened into another target.',
  },
  breadth_history: {
    targets: [],
    note: 'View/export only here: historical breadth uses its dedicated aggregate and member promotion contracts.',
  },
}

export function studyArtifactCapability(artifactType: string): StudyArtifactCapability | null {
  return STUDY_ARTIFACT_CAPABILITIES[artifactType] ?? null
}
