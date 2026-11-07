/**
 * Golden Layout renders workstation tools into virtual component hosts. Those
 * roots do not have an `.lm_stack` DOM ancestor, so the current workspace key
 * is the authoritative foreground signal for this host type.
 */
export function isActiveVirtualToolRoot(
  root: HTMLElement,
  requestedWindowKey: string,
  activeWindowKey: string | null | undefined,
): boolean {
  const virtualHost = root.closest<HTMLElement>('.workspace-layout-host__virtual-tool')
  return virtualHost?.dataset.toolKey === requestedWindowKey
    && activeWindowKey === requestedWindowKey
}

export interface DockTabBinding {
  windowKey: string
  element: HTMLElement
}

/** Resolve a real Golden Layout tab interaction to its exact component key. */
export function dockTabWindowKey(
  target: EventTarget | null,
  bindings: readonly DockTabBinding[],
): string | null {
  if (!(target instanceof Element) || target.closest('.lm_close_tab')) return null
  const tab = target.closest<HTMLElement>('.lm_tab')
  if (!tab) return null
  const binding = bindings.find(candidate => candidate.element === tab
    || candidate.element.contains(tab)
    || tab.contains(candidate.element))
  return binding?.windowKey ?? null
}
