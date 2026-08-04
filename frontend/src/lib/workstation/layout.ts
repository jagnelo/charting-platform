/**
 * Golden Layout v2 accepts a size only as a unit-bearing string. Older persisted
 * snapshots (and some resolved-layout saves) can contain numeric `size` values or
 * the pre-v8 numeric `width` key on columns; normalize them before either rendering
 * or persisting so a recoverable old layout cannot crash the workstation during
 * `trimStart()` parsing or silently lose its saved column proportions.
 */
export function normaliseGoldenLayoutConfig<T>(value: T): T {
  if (Array.isArray(value)) return value.map(normaliseGoldenLayoutConfig) as T
  if (!value || typeof value !== 'object') return value

  const record = value as Record<string, unknown>
  const entries = Object.entries(record)
  // The workstation originally emitted `width` for Golden Layout columns. Golden
  // Layout v2 uses `size`; migrate only layout columns so arbitrary component state
  // fields named width are never rewritten.
  if (record.type === 'column' && record.size == null && record.width != null) {
    entries.splice(entries.findIndex(([key]) => key === 'width'), 1, ['size', record.width])
  }
  return Object.fromEntries(entries.map(([key, child]) => {
    if (key === 'size' && typeof child === 'number') return [key, `${child}fr`]
    // Resolved-layout snapshots produced by older Golden Layout integration code
    // stored these as raw pixels; v2 parses the public config as a size string.
    if ((key === 'minSize' || key === 'defaultMinItemHeight' || key === 'defaultMinItemWidth') && typeof child === 'number') {
      return [key, `${child}px`]
    }
    return [key, normaliseGoldenLayoutConfig(child)]
  })) as T
}
