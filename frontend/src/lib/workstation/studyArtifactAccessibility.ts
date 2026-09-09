export type StudyArtifactAccessibilityInput = {
  name: string
  artifact_type: string
  payload?: Record<string, unknown> | null
}

function valueOf(artifact: StudyArtifactAccessibilityInput): unknown {
  return artifact.payload && typeof artifact.payload === 'object' ? artifact.payload.value : undefined
}

function finiteValues(value: unknown): number[] {
  return Array.isArray(value)
    ? value.filter((item): item is number => typeof item === 'number' && Number.isFinite(item))
    : []
}

function dateRange(timestamps: unknown): string {
  if (!Array.isArray(timestamps)) return ''
  const dates = timestamps.filter((item): item is string => typeof item === 'string' && Number.isFinite(Date.parse(item)))
  if (!dates.length) return ''
  return ` from ${dates[0]} through ${dates[dates.length - 1]}`
}

function alignedSeries(value: unknown): { timestamps: string[]; values: Array<number | null> } | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const candidate = value as { timestamps?: unknown; values?: unknown }
  if (!Array.isArray(candidate.timestamps) || !candidate.timestamps.every(item => typeof item === 'string') || !Array.isArray(candidate.values)) return null
  if (candidate.timestamps.length !== candidate.values.length || !candidate.values.every(item => item == null || typeof item === 'number')) return null
  return { timestamps: candidate.timestamps, values: candidate.values }
}

function describeScalar(artifact: StudyArtifactAccessibilityInput, value: unknown): string {
  const rendered = value === true ? 'true' : value === false ? 'false' : value == null ? 'unavailable' : String(value)
  return `${artifact.name} ${artifact.artifact_type} result: ${rendered}.`
}

/**
 * Describe a persisted Study Lab artifact without flattening or mutating its
 * payload. The description is consumed by hidden aria-describedby text next
 * to canvas-based result surfaces, so assistive users receive the same shape
 * and missing-data boundaries that visual users can infer from the renderer.
 */
export function describeStudyArtifact(artifact: StudyArtifactAccessibilityInput): string {
  const value = valueOf(artifact)
  if (artifact.artifact_type === 'scalar' || artifact.artifact_type === 'boolean') return describeScalar(artifact, value)

  if (artifact.artifact_type === 'series') {
    const structured = alignedSeries(value)
    const values = finiteValues(structured?.values ?? value)
    const total = structured?.values.length ?? (Array.isArray(value) ? value.length : 0)
    const missing = Math.max(total - values.length, 0)
    return `${artifact.name} series result with ${total} observations, ${values.length} finite and ${missing} missing${dateRange(structured?.timestamps)}.`
  }

  if (artifact.artifact_type === 'range') {
    const candidate = value && typeof value === 'object' && !Array.isArray(value) ? value as { timestamps?: unknown; lower?: unknown; upper?: unknown; center?: unknown } : null
    const timestamps = Array.isArray(candidate?.timestamps) ? candidate.timestamps : []
    const lower = finiteValues(candidate?.lower)
    const upper = finiteValues(candidate?.upper)
    const center = finiteValues(candidate?.center)
    const centerLabel = center.length === timestamps.length && timestamps.length > 0 ? 'with an aligned center series' : 'without an aligned center series'
    return `${artifact.name} range result with ${timestamps.length} observations, ${lower.length} finite lower bounds and ${upper.length} finite upper bounds, ${centerLabel}${dateRange(timestamps)}.`
  }

  if (artifact.artifact_type === 'table') {
    const rows = Array.isArray(value) ? value : []
    const columns = [...new Set(rows.flatMap(row => row && typeof row === 'object' && !Array.isArray(row) ? Object.keys(row) : []))]
    return `${artifact.name} table result with ${rows.length} rows and ${columns.length} columns.`
  }

  if (artifact.artifact_type === 'bar') {
    const candidate = value && typeof value === 'object' && !Array.isArray(value) ? value as { labels?: unknown; values?: unknown } : null
    const labels = Array.isArray(candidate?.labels) ? candidate.labels.filter(item => typeof item === 'string') : []
    const values = finiteValues(candidate?.values)
    return `${artifact.name} bar result with ${labels.length} labelled categories and ${values.length} finite values.`
  }

  if (artifact.artifact_type === 'histogram') {
    const bins = value && typeof value === 'object' && !Array.isArray(value) && Array.isArray((value as { bins?: unknown }).bins)
      ? (value as { bins: unknown[] }).bins
      : []
    const count = bins.reduce<number>((sum, bin) => sum + (bin && typeof bin === 'object' && Number.isFinite((bin as { count?: unknown }).count) ? Number((bin as { count: number }).count) : 0), 0)
    return `${artifact.name} histogram result with ${bins.length} bins covering ${count} observations.`
  }

  if (artifact.artifact_type === 'scatter') {
    const candidate = value && typeof value === 'object' && !Array.isArray(value) ? value as { x?: unknown; y?: unknown } : null
    const x = finiteValues(candidate?.x)
    const y = finiteValues(candidate?.y)
    return `${artifact.name} scatter result with ${Math.min(x.length, y.length)} finite pairs.`
  }

  if (artifact.artifact_type === 'heatmap') {
    const candidate = value && typeof value === 'object' && !Array.isArray(value) ? value as { rows?: unknown; columns?: unknown; values?: unknown } : null
    const rows = Array.isArray(candidate?.rows) ? candidate.rows.filter(item => typeof item === 'string').length : 0
    const columns = Array.isArray(candidate?.columns) ? candidate.columns.filter(item => typeof item === 'string').length : 0
    return `${artifact.name} heatmap result with ${rows} rows by ${columns} columns.`
  }

  if (artifact.artifact_type === 'dashboard') {
    const panels = value && typeof value === 'object' && !Array.isArray(value) && Array.isArray((value as { panels?: unknown }).panels)
      ? (value as { panels: unknown[] }).panels.length
      : 0
    return `${artifact.name} dashboard result with ${panels} panels.`
  }

  if (artifact.artifact_type === 'events') {
    const events = Array.isArray(value) ? value : []
    const symbols = new Set(events.map(event => event && typeof event === 'object' && typeof (event as { symbol?: unknown }).symbol === 'string' ? (event as { symbol: string }).symbol : null).filter(Boolean))
    return `${artifact.name} events result with ${events.length} occurrences across ${symbols.size} symbols.`
  }

  if (artifact.artifact_type === 'breadth_history') {
    const candidate = value && typeof value === 'object' && !Array.isArray(value) ? value as { points?: unknown; occurrences?: unknown } : null
    const points = Array.isArray(candidate?.points) ? candidate.points.length : 0
    const occurrences = Array.isArray(candidate?.occurrences) ? candidate.occurrences.length : 0
    return `${artifact.name} breadth-history result with ${points} dated points and ${occurrences} member occurrences.`
  }

  return `${artifact.name} ${artifact.artifact_type} result; inspect the structured payload for details.`
}
