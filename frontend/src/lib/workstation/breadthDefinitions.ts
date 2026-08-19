export type BreadthDefinition = {
  universe?: unknown
  condition?: unknown
  timeframe?: unknown
  adjusted?: unknown
  as_of?: unknown
}

/** Serialize the JSON-shaped breadth AST using Python literals for the sandbox. */
export function breadthPythonLiteral(value: unknown): string {
  if (value === null) return 'None'
  if (value === true) return 'True'
  if (value === false) return 'False'
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  if (typeof value === 'string') return JSON.stringify(value)
  if (Array.isArray(value)) return `[${value.map(item => breadthPythonLiteral(item)).join(', ')}]`
  if (value && typeof value === 'object') {
    return `{${Object.entries(value as Record<string, unknown>).map(([key, item]) => `${JSON.stringify(key)}: ${breadthPythonLiteral(item)}`).join(', ')}}`
  }
  return 'None'
}

export function breadthDefinitionStableKey(name: string, timestamp = Date.now()): string {
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 54) || 'breadth'
  return `breadth-${slug}-${timestamp.toString(36)}`.slice(0, 80)
}

export function buildBreadthStudyAssetPayload(name: string, definition: BreadthDefinition, timestamp = Date.now()) {
  const source = [
    `definition = parameters.get('breadth_definition', ${breadthPythonLiteral(definition)})`,
    "condition = definition.get('condition', {})",
    "snapshot = research.breadth_condition(dataset, condition)",
    "history = research.breadth_condition(dataset, condition, True)",
    "output.scalar('current_percentage', snapshot['percentage'] if snapshot['percentage'] is not None else 0)",
    "output.scalar('current_pass_count', snapshot['pass_count'])",
    "output.scalar('current_eligible_count', snapshot['eligible_count'])",
    "output.series('percentage_history', [point['percentage'] for point in history['points']])",
    "output.table('breadth_members', snapshot['rows'])",
    "output.table('breadth_exclusions', snapshot['exclusions'])",
    "output.table('historical_breadth', history['points'])",
  ].join('\n')
  const universe = definition.universe && typeof definition.universe === 'object'
    ? definition.universe as Record<string, unknown>
    : {}
  return {
    stable_key: breadthDefinitionStableKey(name, timestamp),
    name,
    kind: 'study' as const,
    initial_version: {
      source,
      output_contract: 'study' as const,
      parameter_schema: {
        properties: {
          breadth_definition: { type: 'object' },
          universe_source_id: { type: 'string' },
          timeframe: { type: 'string' },
          adjustment: { type: 'string' },
          as_of: { type: 'string' },
        },
        required: ['breadth_definition', 'universe_source_id'],
      },
      default_parameters: {
        breadth_definition: definition,
        universe_source_id: typeof universe.key === 'string' ? universe.key : null,
        timeframe: definition.timeframe,
        adjustment: definition.adjusted === false ? 'raw' : 'split_adjusted',
        as_of: definition.as_of ?? null,
      },
    },
  }
}
