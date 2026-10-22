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

export function rendererConfigurationSignature(configuration: unknown): string {
  return JSON.stringify(stableValue(configuration))
}

export type RendererInitAction = 'skip-pending' | 'update-existing' | 'rebuild'

export interface RendererLifecycleState {
  renderedSignature: string | null
  pending: { signature: string; promise: Promise<boolean> } | null
}

export function createRendererLifecycleState(): RendererLifecycleState {
  return { renderedSignature: null, pending: null }
}

export function rendererInitAction(input: {
  nextSignature: string
  renderedSignature: string | null
  pendingSignature: string | null
  hasRenderer: boolean
}): RendererInitAction {
  if (input.pendingSignature === input.nextSignature) return 'skip-pending'
  if (input.hasRenderer && input.renderedSignature === input.nextSignature) return 'update-existing'
  return 'rebuild'
}

export async function initializeRenderer(
  state: RendererLifecycleState,
  signature: string,
  hasRenderer: boolean,
  rebuild: () => Promise<boolean>,
  update: () => void,
): Promise<RendererInitAction> {
  const action = rendererInitAction({
    nextSignature: signature,
    renderedSignature: state.renderedSignature,
    pendingSignature: state.pending?.signature ?? null,
    hasRenderer,
  })

  if (action === 'skip-pending') {
    await state.pending?.promise
    return action
  }
  if (action === 'update-existing') {
    update()
    return action
  }

  const pending = { signature, promise: rebuild() }
  state.pending = pending
  try {
    const rendered = await pending.promise
    if (state.pending === pending && rendered) state.renderedSignature = signature
  } finally {
    if (state.pending === pending) state.pending = null
  }
  return action
}

export function clearRenderedRenderer(state: RendererLifecycleState): void {
  state.renderedSignature = null
}

export function invalidateRendererLifecycle(state: RendererLifecycleState): void {
  state.renderedSignature = null
  state.pending = null
}
