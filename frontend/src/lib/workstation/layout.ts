/**
 * Golden Layout v2 accepts a size only as a unit-bearing string. Older persisted
 * snapshots (and some resolved-layout saves) can contain numeric `size` values;
 * normalize them before either rendering or persisting so a recoverable old layout
 * cannot crash the workstation during `trimStart()` parsing.
 */
export function normaliseGoldenLayoutConfig<T>(value: T): T {
  if (Array.isArray(value)) return value.map(normaliseGoldenLayoutConfig) as T
  if (!value || typeof value !== 'object') return value

  return Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([key, child]) => {
    if (key === 'size' && typeof child === 'number') return [key, `${child}fr`]
    // Resolved-layout snapshots produced by older Golden Layout integration code
    // stored these as raw pixels; v2 parses the public config as a size string.
    if ((key === 'minSize' || key === 'defaultMinItemHeight' || key === 'defaultMinItemWidth') && typeof child === 'number') {
      return [key, `${child}px`]
    }
    return [key, normaliseGoldenLayoutConfig(child)]
  })) as T
}
