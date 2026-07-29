<template>
  <div ref="host" class="workspace-layout-host" aria-label="Dockable workstation surface" />
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, render, watch, type VNode } from 'vue'
import { GoldenLayout, type LayoutConfig } from 'golden-layout'

interface DockToolState {
  instance_key: string
  title: string
  tool_type: string
}

export interface DockToolActions {
  toggleMaximize: () => void
}

const props = defineProps<{ layout: LayoutConfig; renderTool: (tool: DockToolState, actions: DockToolActions) => VNode }>()
const emit = defineEmits<{ changed: [layout: Record<string, unknown>, visibleToolKeys: string[]] }>()
const host = ref<HTMLElement | null>(null)
let goldenLayout: GoldenLayout | null = null
let suppressChange = false
const mountedToolRoots: HTMLElement[] = []

function clearMountedTools() {
  for (const root of mountedToolRoots.splice(0)) render(null, root)
}

function install(layout: LayoutConfig) {
  if (!host.value) return
  clearMountedTools()
  goldenLayout?.destroy()
  goldenLayout = new GoldenLayout(host.value)
  goldenLayout.registerComponentFactoryFunction('workstation-tool', (container, state) => {
    const tool = (state ?? {}) as DockToolState
    const rootHtmlElement = document.createElement('section')
    rootHtmlElement.className = 'workspace-layout-host__virtual-tool'
    rootHtmlElement.dataset.toolKey = tool.instance_key ?? ''
    mountedToolRoots.push(rootHtmlElement)
    render(props.renderTool(tool, {
      toggleMaximize: () => {
        const stack = container.parent.parentItem as unknown as { toggleMaximise?: () => void }
        stack.toggleMaximise?.()
      },
    }), rootHtmlElement)
    return { rootHtmlElement }
  }, true)
  goldenLayout.on('stateChanged', () => {
    if (!suppressChange && goldenLayout) {
      const saved = goldenLayout.saveLayout() as unknown as Record<string, unknown>
      emit('changed', saved, extractToolKeys(saved))
    }
  })
  suppressChange = true
  goldenLayout.loadLayout(layout)
  suppressChange = false
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

watch(() => props.layout, layout => install(layout), { deep: true })
onMounted(() => install(props.layout))
onBeforeUnmount(() => {
  clearMountedTools()
  goldenLayout?.destroy()
})

defineExpose({
  saveLayout: () => goldenLayout?.saveLayout(),
  destroy: () => goldenLayout?.destroy(),
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
