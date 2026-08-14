export interface StudyDashboardPanel {
  artifact: string
  title: string
  span: number
}

/**
 * Validate the serialisable dashboard layout emitted by the Study SDK.
 *
 * A dashboard is user-authored data, so an invalid span must not be allowed
 * to escape into CSS grid declarations and damage the surrounding workstation
 * layout. Returning null keeps the artifact visible through the generic
 * structured-payload fallback instead of rendering a misleading partial
 * dashboard.
 */
export function normalizeStudyDashboardPanels(value: unknown): StudyDashboardPanel[] | null {
  if (!value || typeof value !== 'object' || Array.isArray(value) || !Array.isArray((value as { panels?: unknown }).panels)) return null
  const panels = (value as { panels: unknown[] }).panels
  if (!panels.length) return null
  const normalized = panels.map(panel => {
    if (!panel || typeof panel !== 'object' || Array.isArray(panel)) return null
    const candidate = panel as Record<string, unknown>
    if (typeof candidate.artifact !== 'string' || !candidate.artifact.trim()) return null
    if (typeof candidate.title !== 'string' || !candidate.title.trim()) return null
    if (typeof candidate.span !== 'number' || !Number.isInteger(candidate.span) || candidate.span < 1 || candidate.span > 12) return null
    return { artifact: candidate.artifact, title: candidate.title, span: candidate.span }
  })
  return normalized.every((panel): panel is StudyDashboardPanel => panel !== null) ? normalized : null
}
