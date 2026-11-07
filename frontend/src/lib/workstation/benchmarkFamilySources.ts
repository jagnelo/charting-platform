/** Canonical source identities for benchmark-family constituent workflows. */

export function benchmarkFamilyConstituentSourceId(
  familyKey: string,
  role: 'cap_weight' | 'equal_weight' | 'value' | 'growth' = 'cap_weight',
): string | null {
  const normalizedFamily = familyKey.trim().toLowerCase()
  if (!normalizedFamily) return null
  return `benchmark-family:${normalizedFamily}:${role}`
}

/**
 * Breadth snapshots use SPY for generic groups but a family must use its own
 * configured cap proxy. An unmapped family has no comparison leg; borrowing
 * SPY would silently change the meaning of its analysis.
 */
export function breadthSnapshotBenchmark(familyRecord: Record<string, unknown> | null, capProxy: unknown): string | undefined {
  if (!familyRecord) return 'SPY'
  return typeof capProxy === 'string' && capProxy.trim() ? capProxy.trim().toUpperCase() : undefined
}

export function benchmarkFamilyHistoryTargets(familyKey: string, capProxy: unknown) {
  const targets: Array<{ kind: 'family'; family_key: string } | { kind: 'instrument'; symbol: string }> = [
    { kind: 'family', family_key: familyKey.trim() },
  ]
  if (typeof capProxy === 'string' && capProxy.trim()) {
    targets.push({ kind: 'instrument', symbol: capProxy.trim().toUpperCase() })
  }
  return targets
}
