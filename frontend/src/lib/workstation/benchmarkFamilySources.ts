/** Canonical source identities for benchmark-family constituent workflows. */

export function benchmarkFamilyConstituentSourceId(
  familyKey: string,
  role: 'cap_weight' | 'equal_weight' | 'value' | 'growth' = 'cap_weight',
): string | null {
  const normalizedFamily = familyKey.trim().toLowerCase()
  if (!normalizedFamily) return null
  return `benchmark-family:${normalizedFamily}:${role}`
}
