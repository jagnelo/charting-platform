<template>
  <div ref="host" class="workspace-layout-host" aria-label="Dockable workstation surface" />
</template>

<script setup lang="ts">
import { getCurrentInstance, nextTick, onBeforeUnmount, onMounted, ref, render, watch, type VNode } from 'vue'
import { GoldenLayout, type LayoutConfig } from 'golden-layout'
import '../../../node_modules/golden-layout/dist/css/goldenlayout-base.css'
import { normaliseGoldenLayoutConfig } from '@/lib/workstation/layout'

interface DockToolState {
  instance_key: string
  title: string
  tool_type: string
}

export interface DockToolActions {
  toggleMaximize: () => void
  close: () => void
}

const props = defineProps<{
  layout: LayoutConfig
  activeWindowKey?: string | null
  /** Increment only when the parent replaces the complete workspace snapshot. */
  reloadKey?: number
  renderTool: (tool: DockToolState, actions: DockToolActions) => VNode
}>()
const emit = defineEmits<{
  changed: [layout: Record<string, unknown>, visibleToolKeys: string[]]
  'active-window-changed': [windowKey: string]
}>()
const host = ref<HTMLElement | null>(null)
const appContext = getCurrentInstance()?.appContext
let goldenLayout: GoldenLayout | null = null
let suppressChange = false
let suppressChangeUntil = 0
// Golden Layout emits observational state/activation events while it is
// constructing a persisted tree. Do not turn those bootstrap notifications
// into writes until the user has interacted with the dock itself. Explicit
// workstation actions (Add tool, close, link changes) persist through the
// store and therefore do not depend on this flag.
let initialEventsSuppressed = true
let activationGuardKey: string | null = null
let activationRetryTimer: number | null = null
let activationGuardTimer: number | null = null
let lastLayoutFingerprint: string | null = null
let layoutGeneration = 0
const mountedToolRoots: HTMLElement[] = []
// Golden Layout's virtual component root is intentionally detached from the
// visible stack DOM. Retain the actual ComponentItem supplied to the factory so
// activation remains reliable even when tabs overflow into the dropdown.
const componentItems = new Map<string, any>()
let resizeObserver: ResizeObserver | null = null

function changeSuppressed() {
  return initialEventsSuppressed || suppressChange || Date.now() < suppressChangeUntil
}

function releaseInitialSuppression() {
  initialEventsSuppressed = false
  suppressChangeUntil = 0
}

function layoutFingerprint(layout: LayoutConfig) {
  const stripRuntimeSelection = (value: unknown): unknown => {
    if (Array.isArray(value)) return value.map(stripRuntimeSelection)
    if (!value || typeof value !== 'object') return value
    const record = value as Record<string, unknown>
    return Object.fromEntries(Object.entries(record)
      .filter(([key]) => key !== 'activeItemIndex')
      .map(([key, child]) => [key, stripRuntimeSelection(child)]))
  }
  return JSON.stringify(stripRuntimeSelection(normaliseGoldenLayoutConfig(layout)))
}

function withRequestedActiveIndex(value: Record<string, unknown>, windowKey: string | null): Record<string, unknown> {
  const content = Array.isArray(value.content) ? value.content : null
  if (!content) return value
  const nextContent = content.map(child => child && typeof child === 'object'
    ? withRequestedActiveIndex(child as Record<string, unknown>, windowKey)
    : child)
  const index = nextContent.findIndex(child => {
    if (!child || typeof child !== 'object') return false
    const state = (child as Record<string, unknown>).componentState
    return Boolean(state && typeof state === 'object' && (state as Record<string, unknown>).instance_key === windowKey)
  })
  return {
    ...value,
    content: nextContent,
    ...(value.type === 'stack' && index >= 0 ? { activeItemIndex: index } : {}),
  }
}

function normaliseComponentStacks(value: Record<string, unknown>): Record<string, unknown> {
  const content = Array.isArray(value.content) ? value.content : null
  if (!content) return value
  const nextContent = content.flatMap(child => {
    if (!child || typeof child !== 'object') return [child]
    const normalized = normaliseComponentStacks(child as Record<string, unknown>)
    return normalized.type === 'component'
      ? [{ type: 'stack', content: [normalized] }]
      : [normalized]
  })
  return { ...value, content: nextContent }
}

function activateWindow(windowKey: string | null | undefined) {
  const root = (goldenLayout as any)?.root
  if (!windowKey || !root) return
  const items: any[] = []
  const visit = (item: any) => {
    if (!item) return
    items.push(item)
    for (const child of item.contentItems ?? []) visit(child)
  }
  visit(root)
  const component = componentItems.get(windowKey) ?? items.find(item => item.type === 'component' && item.config?.componentState?.instance_key === windowKey)
  const stack = component?.parentItem
  if (component && stack?.setActiveComponentItem) {
    const generation = layoutGeneration
    const ownsComponent = () => {
      if (generation !== layoutGeneration || goldenLayout == null) return false
      const parent = component.parentItem as any
      return Boolean(parent
        && Array.isArray(parent.contentItems)
        && parent.contentItems.includes(component)
        && Array.isArray(parent.header?.tabs)
        && parent.header.tabs.some((tab: any) => tab.contentItem === component))
    }
    // Golden Layout can expose a component item before its header tab has been
    // constructed, or retain an item briefly while a replacement layout is
    // being torn down. Calling setActiveComponentItem in either state triggers
    // its internal HSACI56632 assertion. Let the bounded retry below wait for
    // the current generation and a real owning header instead.
    if (!ownsComponent()) {
      const generation = layoutGeneration
      window.setTimeout(() => {
        if (generation === layoutGeneration) activateWindow(windowKey)
      }, 25)
      return
    }
    const activate = () => stack.setActiveComponentItem(component, false, true)
    // Selecting a tab is view state, not a layout mutation. Golden Layout can
    // emit stateChanged while setActiveComponentItem is running; suppress that
    // emission or the parent will replace the just-installed layout and reset
    // the active tab back to the first component.
    const wasSuppressed = suppressChange
    suppressChange = true
    suppressChangeUntil = Date.now() + 250
    activate()
    suppressChange = wasSuppressed
    // A freshly loaded stack can finish constructing its tab header one tick
    // after loadLayout returns. Re-assert the persisted active component after
    // that construction so opening a tool never leaves it hidden behind the
    // previous tab.
    const reassert = () => {
      if (ownsComponent() && component.parentItem?.setActiveComponentItem) {
        const parent = component.parentItem as any
        const wasSuppressed = suppressChange
        suppressChange = true
        suppressChangeUntil = Date.now() + 250
        parent.setActiveComponentItem(component, false, true)
        suppressChange = wasSuppressed
        // A dynamically normalized stack can report the requested component
        // as internally active while its header DOM still marks the original
        // component active. Reconcile both surfaces explicitly.
        for (const sibling of parent.contentItems ?? []) {
          if (sibling === component) sibling.show?.()
          else sibling.hide?.()
        }
        // During a Golden Layout drag the component temporarily leaves its
        // original stack/header. The asynchronous active-window reassertion
        // must not ask that header to mark a component it no longer owns as
        // active; Golden Layout treats that as an internal invariant failure.
        const headerTabs = parent.header?.tabs
        if (Array.isArray(headerTabs) && headerTabs.some((tab: any) => tab.contentItem === component)) {
          parent.header.processActiveComponentChanged?.(component)
        }
        if (component.parentItem.activeComponentItem !== component) {
          const tab = component.parentItem.header?.tabs?.find((candidate: any) => candidate.contentItem === component)
          tab?.element?.click?.()
        }
      }
    }
    requestAnimationFrame(reassert)
    // Golden Layout can create tab headers on a second layout turn when a
    // workspace snapshot is replaced while a tool is being opened. Reassert
    // once more after that turn so the newly selected tool cannot remain
    // hidden behind the first tab.
    requestAnimationFrame(() => requestAnimationFrame(reassert))
    window.setTimeout(reassert, 0)
    if (activationRetryTimer !== null) window.clearInterval(activationRetryTimer)
    let attempts = 0
    activationRetryTimer = window.setInterval(() => {
      attempts += 1
      if (generation !== layoutGeneration) {
        if (activationRetryTimer !== null) window.clearInterval(activationRetryTimer)
        activationRetryTimer = null
        return
      }
      if (component.parentItem?.activeComponentItem === component) {
        if (activationRetryTimer !== null) window.clearInterval(activationRetryTimer)
        activationRetryTimer = null
        return
      }
      reassert()
      if (attempts >= 40 && activationRetryTimer !== null) {
        window.clearInterval(activationRetryTimer)
        activationRetryTimer = null
      }
    }, 25)
  }
}

function clearMountedTools() {
  for (const root of mountedToolRoots.splice(0)) {
    render(null, root)
    // Virtual roots are appended directly to the host by Golden Layout rather
    // than nested under a removable component container. Unmounting Vue alone
    // leaves an orphaned positioned element that can retain stale geometry and
    // intercept pointer events after a layout reinstall or workspace restore.
    root.remove()
  }
}

function teardown() {
  layoutGeneration += 1
  goldenLayout?.destroy()
  goldenLayout = null
  clearMountedTools()
  componentItems.clear()
  if (activationRetryTimer !== null) window.clearInterval(activationRetryTimer)
  activationRetryTimer = null
  activationGuardKey = null
  if (activationGuardTimer !== null) window.clearTimeout(activationGuardTimer)
  activationGuardTimer = null
  resizeObserver?.disconnect()
  resizeObserver = null
}

/**
 * Remove a tool from the serializable Golden Layout tree without asking
 * Golden Layout to mutate a live stack. The library can schedule a resize
 * callback while `ComponentItem.close()` is deleting the last tab in a stack;
 * that callback then dereferences the tab it just removed. Rebuilding from a
 * filtered JSON tree keeps the same persisted layout contract while allowing
 * teardown to disconnect every observer before the old tree is destroyed.
 */
function withoutComponent(value: unknown, windowKey: string): unknown {
  if (Array.isArray(value)) {
    const children = value
      .map(child => withoutComponent(child, windowKey))
      .filter(child => child !== null)
    return children
  }
  if (!value || typeof value !== 'object') return value
  const record = value as Record<string, unknown>
  if (record.type === 'component') {
    const state = record.componentState
    if (state && typeof state === 'object' && (state as Record<string, unknown>).instance_key === windowKey) {
      return null
    }
    return record
  }
  if (record.root && typeof record.root === 'object') {
    const root = withoutComponent(record.root, windowKey)
    return root && typeof root === 'object' ? { ...record, root } : null
  }
  if (!Array.isArray(record.content)) return record
  const content = withoutComponent(record.content, windowKey)
  const children = Array.isArray(content) ? content : []
  if (children.length === 0) return null
  // Golden Layout accepts a single remaining child at the root, but a stack is
  // required for component tabs. Keep stacks intact and only collapse empty or
  // redundant row/column containers created by the removed component.
  if (children.length === 1 && (record.type === 'row' || record.type === 'column')) return children[0]
  if (record.type === 'stack') {
    const requestedIndex = typeof record.activeItemIndex === 'number' ? record.activeItemIndex : 0
    return {
      ...record,
      content: children,
      activeItemIndex: Math.max(0, Math.min(requestedIndex, children.length - 1)),
    }
  }
  return { ...record, content: children }
}

function closeComponent(windowKey: string) {
  if (!goldenLayout) return
  const saved = goldenLayout.saveLayout() as unknown as Record<string, unknown>
  const filtered = withoutComponent(saved, windowKey)
  if (!filtered || typeof filtered !== 'object') return
  const nextLayout = normaliseGoldenLayoutConfig(filtered as Record<string, unknown>)
  suppressChange = true
  suppressChangeUntil = Date.now() + 1_000
  teardown()
  // Reinstall immediately from the filtered tree. The parent store will apply
  // the same JSON snapshot and update the active-window key on the next Vue
  // turn; leaving the host empty until that round trip makes the remaining
  // workstation controls disappear during rapid drill-down.
  install(nextLayout as LayoutConfig)
  emit('changed', nextLayout, extractToolKeys(nextLayout))
}

function install(layout: LayoutConfig) {
  if (!host.value) return
  initialEventsSuppressed = true
  layoutGeneration += 1
  const stackNormalised = normaliseComponentStacks(layout as unknown as Record<string, unknown>)
  const normalised = normaliseGoldenLayoutConfig(
    withRequestedActiveIndex(stackNormalised, props.activeWindowKey ?? null),
  ) as LayoutConfig
  // Keep the fingerprint tied to the serializable parent prop. The explicit
  // activeItemIndex below is a load-time hint and must not cause an install loop.
  lastLayoutFingerprint = layoutFingerprint(layout)
  goldenLayout?.destroy()
  goldenLayout = null
  clearMountedTools()
  goldenLayout = new GoldenLayout(host.value)
  activationGuardKey = props.activeWindowKey ?? null
  if (activationGuardTimer !== null) window.clearTimeout(activationGuardTimer)
  activationGuardTimer = activationGuardKey
    ? window.setTimeout(() => { activationGuardKey = null; activationGuardTimer = null }, 1_000)
    : null
  goldenLayout.registerComponentFactoryFunction('workstation-tool', (container, state) => {
    const tool = (state ?? {}) as DockToolState
    if (tool.instance_key && (container as any).parent) componentItems.set(tool.instance_key, (container as any).parent)
    const rootHtmlElement = document.createElement('section')
    rootHtmlElement.className = 'workspace-layout-host__virtual-tool'
    rootHtmlElement.dataset.toolKey = tool.instance_key ?? ''
    mountedToolRoots.push(rootHtmlElement)
    const vnode = props.renderTool(tool, {
      toggleMaximize: () => {
        const stack = container.parent.parentItem as unknown as { toggleMaximise?: () => void }
        stack.toggleMaximise?.()
      },
      close: () => closeComponent(tool.instance_key),
    })
    // Golden Layout asks Vue to render each virtual component into a detached root.
    // Carry the host application context across that boundary so injected services
    // (Vue Query, Pinia, router, and global providers) remain available to tools.
    if (appContext) vnode.appContext = appContext
    render(vnode, rootHtmlElement)
    if (tool.instance_key === props.activeWindowKey) {
      // The factory is the first point at which the component has its final
      // containing stack. Activate here instead of relying only on a later
      // tree traversal that can race Golden Layout's initial selection.
      queueMicrotask(() => activateWindow(tool.instance_key))
    }
    return { rootHtmlElement }
  }, true)
  goldenLayout.on('stateChanged', () => {
    if (!changeSuppressed() && goldenLayout) {
      const saved = normaliseGoldenLayoutConfig(
        goldenLayout.saveLayout() as unknown as Record<string, unknown>,
      )
      const fingerprint = layoutFingerprint(saved as LayoutConfig)
      if (fingerprint === lastLayoutFingerprint) return
      // The parent will persist this exact JSON and pass it back as a prop. Record
      // it before emitting so the watcher does not destroy/recreate every virtual
      // tool in response to Golden Layout's own stateChanged notification.
      lastLayoutFingerprint = fingerprint
      emit('changed', saved, extractToolKeys(saved))
    }
  })
  goldenLayout.on('activeContentItemChanged', (item: any) => {
    const windowKey = item?.config?.componentState?.instance_key
    // Golden Layout can emit a late bootstrap activation for the first tab
    // after the requested component has been installed. Do not let that
    // construction event overwrite the serialized active-window selection.
    if (activationGuardKey && windowKey !== activationGuardKey) {
      activateWindow(activationGuardKey)
      return
    }
    // Loading a persisted layout briefly activates its first component before
    // the requested active window is restored. Do not let that bootstrap event
    // overwrite the persisted active-window key.
    if (!changeSuppressed() && typeof windowKey === 'string' && windowKey) emit('active-window-changed', windowKey)
  })
  suppressChange = true
  // Keep bootstrap normalization/activation events out of persistence for the
  // same bounded window as the active-item guard. A late stateChanged event
  // after loadLayout can otherwise consume the next revision-conflict oracle
  // (and, in production, create a needless snapshot write before the user has
  // changed anything). Explicit tool edits persist directly through the store,
  // so suppressing only these observational Golden Layout events is safe.
  suppressChangeUntil = Date.now() + 1_000
  goldenLayout.loadLayout(normalised)
  // Golden Layout may emit its initial active-component/state events on a later
  // turn. Keep persistence suppressed through that turn, then restore the
  // requested active window once all stack items and headers exist.
  activateWindow(props.activeWindowKey)
  requestAnimationFrame(() => {
    suppressChange = false
    activateWindow(props.activeWindowKey)
  })
  const width = host.value.clientWidth
  const height = host.value.clientHeight
  if (width > 0 && height > 0) goldenLayout.setSize(width, height)
}

function extractToolKeys(value: unknown): string[] {
  if (Array.isArray(value)) return value.flatMap(extractToolKeys)
  if (!value || typeof value !== 'object') return []
  const record = value as Record<string, unknown>
  const state = record.componentState
  const key = state && typeof state === 'object' && typeof (state as Record<string, unknown>).instance_key === 'string'
    ? [(state as Record<string, string>).instance_key]
    : []
  return [...key, ...Object.values(record).flatMap(extractToolKeys)]
}

watch(
  [() => props.layout, () => props.activeWindowKey, () => props.reloadKey],
  ([layout, windowKey, reloadKey], [, , previousReloadKey]) => {
    // Vue updates the serialized layout and active key in the same mutation
    // when Add Tool appends a component. Observe them together after the
    // update so Golden Layout is never installed with a stale active key.
    // A complete workspace import/factory reset can replace every window
    // object while retaining the same Golden Layout structure; the explicit
    // reload token refreshes virtual roots in that case without making normal
    // tool-configuration edits recreate the dock or its uPlot instances.
    if (reloadKey !== previousReloadKey || layoutFingerprint(layout) !== lastLayoutFingerprint) {
      install(layout)
      void nextTick(() => activateWindow(windowKey))
    } else {
      activateWindow(windowKey)
      void nextTick(() => activateWindow(windowKey))
    }
  },
  { flush: 'post' },
)
onMounted(() => {
  host.value?.addEventListener('pointerdown', releaseInitialSuppression, true)
  host.value?.addEventListener('keydown', releaseInitialSuppression, true)
  install(props.layout)
  if (host.value) {
    resizeObserver = new ResizeObserver(entries => {
      const entry = entries[0]
      if (!entry || !goldenLayout) return
      const width = Math.round(entry.contentRect.width)
      const height = Math.round(entry.contentRect.height)
      if (width > 0 && height > 0) goldenLayout.setSize(width, height)
    })
    resizeObserver.observe(host.value)
  }
})
onBeforeUnmount(() => {
  host.value?.removeEventListener('pointerdown', releaseInitialSuppression, true)
  host.value?.removeEventListener('keydown', releaseInitialSuppression, true)
  teardown()
})

defineExpose({
  saveLayout: () => goldenLayout?.saveLayout(),
  destroy: teardown,
})
</script>

<style scoped>
.workspace-layout-host { position: relative; width: 100%; height: 100%; min-width: 0; min-height: 0; overflow: hidden; background: #0b0f12; }
:deep(.lm_goldenlayout) { background: #0b0f12; }
:deep(.lm_header) { height: 25px; background: linear-gradient(#2a3036, #1d2227); border-bottom: 1px solid #0d0f11; }
:deep(.lm_tabs) { height: 25px; }
:deep(.lm_tab) { height: 25px; padding: 6px 8px 0; color: #b9c4cc; font: 600 11px/1 "Segoe UI", Arial, sans-serif; background: #20262b; }
:deep(.lm_tab.lm_active) { color: #edf5f8; background: #303940; box-shadow: inset 0 2px #67b7ea; }
:deep(.lm_content) { background: #15191e; }
:deep(.lm_splitter) { background: #090c0f; opacity: 1; }
:deep(.lm_splitter:hover) { background: #4f6678; }
:deep(.lm_close_tab) { opacity: .65; }
.workspace-layout-host__virtual-tool { width: 100%; height: 100%; min-width: 0; min-height: 0; }
</style>
