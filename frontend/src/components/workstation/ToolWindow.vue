<template>
  <section class="tool-window" :class="{ 'tool-window--active': active }" @keydown.escape="menuOpen = false">
    <header class="tool-window__header">
      <span class="tool-window__drag-handle" draggable="true" aria-label="Drag tool" title="Drag tool" @dragstart="emit('dragstart', $event)">⋮⋮</span>
      <strong class="tool-window__title">{{ title }}</strong>
      <span v-if="symbol" class="tool-window__symbol">{{ symbol }}</span>
      <div class="tool-window__actions">
        <span v-if="timeframe" class="tool-window__link-swatch" :style="{ background: dashboardLinkGroupColor(timeframeLinkGroup) }" :title="`${dashboardLinkGroupLabel(timeframeLinkGroup)} timeframe link`" aria-hidden="true" />
        <select v-if="timeframe" :value="timeframeLinkGroup" class="tool-window__timeframe-link" :aria-label="title + ' timeframe link group'" @change="emit('update:timeframeLinkGroup', ($event.target as HTMLSelectElement).value as LinkGroup)">
          <option v-for="group in groups" :key="group" :value="group">{{ dashboardLinkGroupLabel(group) }}</option>
        </select>
        <select v-if="timeframe" :value="timeframe" class="tool-window__timeframe" :aria-label="title + ' timeframe'" @change="emit('update:timeframe', ($event.target as HTMLSelectElement).value)">
          <option value="M1">1m</option><option value="M5">5m</option><option value="M15">15m</option><option value="M30">30m</option><option value="H1">1h</option><option value="H2">2h</option><option value="H4">4h</option><option value="H12">12h</option><option value="D1">D</option><option value="W1">W</option><option value="MN">M</option>
        </select>
        <span class="tool-window__link-swatch" :style="{ background: dashboardLinkGroupColor(linkGroup) }" :title="`${dashboardLinkGroupLabel(linkGroup)} symbol link`" aria-hidden="true" />
        <select
          :value="linkGroup"
          class="tool-window__link"
          :aria-label="title + ' symbol link group'"
          @change="emit('update:linkGroup', ($event.target as HTMLSelectElement).value as LinkGroup)"
        >
          <option v-for="group in groups" :key="group" :value="group">{{ dashboardLinkGroupLabel(group) }}</option>
        </select>
        <div class="tool-window__menu-wrap">
          <button type="button" title="Tool menu" aria-haspopup="menu" :aria-expanded="menuOpen" @click.stop="menuOpen = !menuOpen">⋮</button>
          <div v-if="menuOpen" class="tool-window__menu" role="menu" :aria-label="`${title} tool menu`" @click.stop>
            <button type="button" role="menuitem" @click="runMenuAction('maximize')">Maximize</button>
            <button type="button" role="menuitem" @click="runMenuAction('float')">Float</button>
            <button type="button" role="menuitem" @click="runMenuAction('close')">Close</button>
          </div>
        </div>
        <button type="button" title="Maximize" @click="emit('maximize')">□</button>
        <button type="button" title="Float" @click="emit('float')">↗</button>
        <button type="button" title="Close" aria-label="Close tool" @click="emit('close')">×</button>
      </div>
    </header>
    <div class="tool-window__body">
      <slot />
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { LinkGroup } from '@/stores/workspace'
import { dashboardLinkGroupColor, dashboardLinkGroupLabel } from '@/stores/dashboardLinks'

withDefaults(defineProps<{
  title: string
  symbol?: string
  linkGroup?: LinkGroup
  timeframeLinkGroup?: LinkGroup
  timeframe?: string
  active?: boolean
}>(), {
  symbol: '',
  linkGroup: 'blue',
  timeframeLinkGroup: 'blue',
  timeframe: '',
  active: false,
})

const emit = defineEmits<{
  'update:linkGroup': [value: LinkGroup]
  'update:timeframeLinkGroup': [value: LinkGroup]
  'update:timeframe': [value: string]
  dragstart: [event: DragEvent]
  maximize: []
  float: []
  close: []
}>()

const menuOpen = ref(false)

function runMenuAction(action: 'maximize' | 'float' | 'close') {
  menuOpen.value = false
  if (action === 'maximize') emit('maximize')
  else if (action === 'float') emit('float')
  else emit('close')
}

const groups: LinkGroup[] = ['blue', 'red', 'green', 'purple', 'orange', 'cyan', 'pink', 'brown', 'yellow', 'grey']
</script>

<style scoped>
.tool-window { position: relative; min-width: 0; min-height: 0; display: flex; flex-direction: column; border: 1px solid var(--tc-border, #30363c); background: var(--tc-window, #15191e); box-shadow: inset 0 1px rgba(255, 255, 255, 0.035); }
.tool-window--active { border-color: #607486; }
.tool-window__header { height: var(--tc-window-header-height); display: flex; align-items: center; gap: 5px; padding: 0 4px; background: linear-gradient(var(--tc-header-top), var(--tc-header-bottom)); border-bottom: 1px solid #0d0f11; color: var(--tc-text); font: 600 11px/1 var(--tc-font-family); user-select: none; }
.tool-window__drag-handle { display: inline-flex; width: 12px; flex: 0 0 12px; align-items: center; justify-content: center; color: #748793; font-size: 11px; letter-spacing: -2px; cursor: grab; }
.tool-window__drag-handle:active { cursor: grabbing; }
.tool-window__actions button { border: 0; color: #aab4bc; background: transparent; cursor: pointer; min-width: 17px; height: 20px; font-size: 12px; }
.tool-window__actions button:hover { color: #fff; background: #38414a; }
.tool-window__title { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tool-window__symbol { color: #9fc2e0; font-weight: 700; }
.tool-window__actions { margin-left: auto; display: flex; align-items: center; }
.tool-window__menu-wrap { position: relative; }
.tool-window__menu { position: absolute; z-index: 20; top: calc(100% + 3px); right: 0; display: grid; min-width: 110px; padding: 3px; border: 1px solid var(--tc-border-strong); background: #1a2025; box-shadow: 0 5px 14px rgba(0, 0, 0, .45); }
.tool-window__menu button { width: 100%; padding: 4px 7px; text-align: left; }
.tool-window__link { width: 54px; height: 18px; color: var(--tc-text); border: 1px solid var(--tc-border-strong); background: var(--tc-input-bg); font: 10px var(--tc-font-family); }
.tool-window__link-swatch { width: 8px; height: 8px; flex: 0 0 8px; border: 1px solid #0b0f12; border-radius: 50%; box-shadow: 0 0 0 1px #65737d; }
.tool-window__timeframe { width: 27px; height: 18px; color: var(--tc-text); border: 1px solid var(--tc-border-strong); background: var(--tc-input-bg); font: 10px var(--tc-font-family); }
.tool-window__timeframe-link { width: 54px; height: 18px; color: var(--tc-text); border: 1px solid var(--tc-border-strong); background: var(--tc-input-bg); font: 10px var(--tc-font-family); }
.tool-window__body { min-width: 0; min-height: 0; flex: 1; overflow: hidden; }
</style>
