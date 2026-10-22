type EvidenceRecord = Record<string, unknown>

export interface BreadthReferenceTargetEvidence {
  kind: 'symbol' | 'aggregate'
  target: string
  derivation: string | null
  membership: string | null
  coverage: string | null
  alignedSeries: string | null
  alignment: string | null
}

function asRecord(value: unknown): EvidenceRecord | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as EvidenceRecord
    : null
}

function firstString(...values: unknown[]): string | null {
  return values.find((value): value is string => typeof value === 'string' && value.trim().length > 0)?.trim() ?? null
}

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function displayedMethod(value: unknown): string | null {
  const method = firstString(value)
  if (!method) return null
  const readable = method.replace(/[_-]+/g, ' ')
  return readable.charAt(0).toUpperCase() + readable.slice(1)
}

function alignmentLabel(value: unknown): string | null {
  if (value === 'exact_timestamp_no_forward_fill') return 'Exact timestamp · no forward fill'
  return displayedMethod(value)
}

export function breadthReferenceTargetEvidence(conditionValue: unknown): BreadthReferenceTargetEvidence | null {
  const condition = asRecord(conditionValue)
  if (!condition) return null

  const referenceUniverse = asRecord(condition.reference_universe)
  if (referenceUniverse) {
    const referenceTarget = asRecord(condition.reference_target) ?? {}
    const universeProvenance = asRecord(referenceTarget.universe) ?? {}
    const sourceKind = firstString(referenceUniverse.kind) ?? 'reference'
    const sourceKey = firstString(
      referenceUniverse.key,
      universeProvenance.stable_key,
      universeProvenance.family_key,
    )
    const memberCount = finiteNumber(referenceTarget.member_count)
    const meanCoveredMembers = finiteNumber(referenceTarget.mean_covered_members)
    const meanCoverage = memberCount != null && memberCount > 0 && meanCoveredMembers != null
      ? `${((meanCoveredMembers / memberCount) * 100).toFixed(1)}% average · ${meanCoveredMembers.toFixed(1)}/${memberCount} members per point`
      : null
    const membershipVersion = referenceTarget.membership_version
    const membershipParts = [
      typeof membershipVersion === 'string' || typeof membershipVersion === 'number'
        ? `version ${membershipVersion}`
        : null,
      memberCount == null ? null : `${memberCount} members`,
    ].filter((part): part is string => part !== null)
    const pointCount = finiteNumber(referenceTarget.point_count)
    const coveredMemberPoints = finiteNumber(referenceTarget.covered_member_points)
    const seriesParts = [
      pointCount == null ? null : `${pointCount} aligned points`,
      coveredMemberPoints == null ? null : `${coveredMemberPoints} covered member-points`,
    ].filter((part): part is string => part !== null)
    const sourceLabel = sourceKind === 'group' ? 'group' : sourceKind.replace(/[_-]+/g, ' ')

    return {
      kind: 'aggregate',
      target: `Equal-weight ${sourceLabel} aggregate${sourceKey ? ` · ${sourceKey}` : ''}`,
      derivation: displayedMethod(referenceTarget.method ?? referenceTarget.target),
      membership: membershipParts.join(' · ') || null,
      coverage: meanCoverage,
      alignedSeries: seriesParts.join(' · ') || null,
      alignment: alignmentLabel(referenceTarget.alignment),
    }
  }

  const referenceSymbol = firstString(condition.reference_symbol)
  return referenceSymbol
    ? {
        kind: 'symbol',
        target: `Reference symbol · ${referenceSymbol.toUpperCase()}`,
        derivation: null,
        membership: null,
        coverage: null,
        alignedSeries: null,
        alignment: null,
      }
    : null
}
