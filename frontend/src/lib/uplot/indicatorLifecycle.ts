import { nextTick, watch } from 'vue'
import type { IndicatorConfig } from '@/types'

function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stableValue)
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, nested]) => [key, stableValue(nested)]),
    )
  }
  return value
}

export function indicatorStackSignature(indicators: readonly IndicatorConfig[]): string {
  return JSON.stringify(stableValue(indicators))
}

/** Rebuild only when the rendered indicator configuration changes semantically. */
export function watchIndicatorStack(
  source: () => readonly IndicatorConfig[],
  rebuild: () => void | Promise<void>,
) {
  return watch(
    () => indicatorStackSignature(source()),
    async (signature, previous) => {
      if (signature === previous) return
      await nextTick()
      await rebuild()
    },
  )
}
