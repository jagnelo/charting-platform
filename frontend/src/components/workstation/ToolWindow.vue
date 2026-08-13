<template>
  <section class="tool-window" :data-window-key="windowKey" :class="{ 'tool-window--active': active }" @keydown.escape="closeMenuToTrigger">
    <header class="tool-window__header">
      <span class="tool-window__drag-handle" draggable="true" aria-label="Drag tool" title="Drag tool" @dragstart="emit('dragstart', $event)"><span class="tool-window__drag-glyph" aria-hidden="true" /></span>
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
        <div ref="menuRoot" class="tool-window__menu-wrap">
          <button ref="menuTrigger" type="button" title="Tool menu" aria-label="Open tool menu" aria-haspopup="menu" :aria-expanded="menuOpen" @click.stop="toggleMenu" @keydown="handleMenuTriggerKeydown"><span class="tool-window__menu-glyph" aria-hidden="true" /></button>
          <div v-if="menuOpen" class="tool-window__menu" role="menu" :aria-label="`${title} tool menu`" :style="menuStyle" @click.stop @keydown="handleMenuKeydown">
            <button type="button" role="menuitem" tabindex="-1" @click="runMenuAction('maximize')">Maximize</button>
            <button type="button" role="menuitem" tabindex="-1" @click="runMenuAction('float')">Float</button>
            <button type="button" role="menuitem" tabindex="-1" @click="runMenuAction('close')">Close</button>
          </div>
        </div>
        <button type="button" title="Maximize" aria-label="Maximize tool" @click="emit('maximize')"><span class="tool-window__maximize-glyph" aria-hidden="true" /></button>
        <button type="button" title="Float" aria-label="Float tool" @click="emit('float')"><span class="tool-window__float-glyph" aria-hidden="true" /></button>
        <button type="button" title="Close" aria-label="Close tool" @click="emit('close')"><span class="tool-window__close-glyph" aria-hidden="true" /></button>
      </div>
    </header>
    <div class="tool-window__body">
      <slot />
    </div>
  </section>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import type { LinkGroup } from '@/stores/workspace'
import { dashboardLinkGroupColor, dashboardLinkGroupLabel } from '@/stores/dashboardLinks'

withDefaults(defineProps<{
  windowKey?: string
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
const menuRoot = ref<HTMLElement | null>(null)
const menuTrigger = ref<HTMLButtonElement | null>(null)
const menuStyle = ref<Record<string, string>>({})

function menuItems() {
  return Array.from(menuRoot.value?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? [])
}

function focusMenuItem(index: number) {
  const items = menuItems()
  if (!items.length) return
  items[Math.max(0, Math.min(index, items.length - 1))]?.focus()
}

function setMenuOpen(open: boolean, focusIndex = 0) {
  menuOpen.value = open
  if (!open) {
    window.removeEventListener('resize', positionMenu)
    window.removeEventListener('scroll', positionMenu, true)
    return
  }
  void nextTick(() => {
    positionMenu()
    window.addEventListener('resize', positionMenu)
    window.addEventListener('scroll', positionMenu, true)
    focusMenuItem(focusIndex)
  })
}

function toggleMenu() {
  setMenuOpen(!menuOpen.value)
}

function closeMenuToTrigger() {
  if (!menuOpen.value) return
  menuOpen.value = false
  window.removeEventListener('resize', positionMenu)
  window.removeEventListener('scroll', positionMenu, true)
  void nextTick(() => menuTrigger.value?.focus())
}

function positionMenu() {
  const rect = menuTrigger.value?.getBoundingClientRect()
  if (!rect) return
  const gutter = 8
  const width = 110
  const menuHeight = Math.min(180, Math.max(96, window.innerHeight - gutter * 2))
  const left = Math.max(gutter, Math.min(rect.right - width, window.innerWidth - width - gutter))
  const below = rect.bottom + 3
  const above = rect.top - menuHeight - 3
  const top = below + menuHeight <= window.innerHeight - gutter ? below : Math.max(gutter, above)
  menuStyle.value = { position: 'fixed', left: `${Math.round(left)}px`, top: `${Math.round(top)}px`, width: `${width}px`, maxHeight: `${Math.round(menuHeight)}px` }
}

function handleMenuTriggerKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' || event.key === ' ' || event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    setMenuOpen(true, event.key === 'ArrowUp' ? menuItems().length - 1 : 0)
  }
}

function handleMenuKeydown(event: KeyboardEvent) {
  const items = menuItems()
  const target = event.target instanceof HTMLElement ? event.target : null
  const currentIndex = target ? items.indexOf(target as HTMLButtonElement) : -1
  if (!items.length) return
  if (event.key === 'Escape') {
    event.preventDefault()
    closeMenuToTrigger()
    return
  }
  if (event.key === 'ArrowDown' || event.key === 'ArrowRight') {
    event.preventDefault()
    focusMenuItem((currentIndex + 1 + items.length) % items.length)
  } else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') {
    event.preventDefault()
    focusMenuItem((currentIndex - 1 + items.length) % items.length)
  } else if (event.key === 'Home') {
    event.preventDefault()
    focusMenuItem(0)
  } else if (event.key === 'End') {
    event.preventDefault()
    focusMenuItem(items.length - 1)
  } else if ((event.key === 'Enter' || event.key === ' ') && target) {
    event.preventDefault()
    target.click()
  }
}

function dismissMenuOnOutsidePointer(event: PointerEvent) {
  const target = event.target
  if (!(target instanceof Node) || !menuRoot.value?.contains(target)) setMenuOpen(false)
}

onMounted(() => {
  // Capture at document level so a click in another docked tool or the shell
  // cannot leave this fixed-position menu covering the next interaction.
  document.addEventListener('pointerdown', dismissMenuOnOutsidePointer, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', dismissMenuOnOutsidePointer, true)
  window.removeEventListener('resize', positionMenu)
  window.removeEventListener('scroll', positionMenu, true)
})

function runMenuAction(action: 'maximize' | 'float' | 'close') {
  setMenuOpen(false)
  if (action === 'maximize') emit('maximize')
  else if (action === 'float') emit('float')
  else emit('close')
}

const groups: LinkGroup[] = ['blue', 'red', 'green', 'purple', 'orange', 'cyan', 'pink', 'brown', 'yellow', 'grey']
</script>

<style scoped>
.tool-window { position: relative; width: 100%; height: 100%; min-width: 0; min-height: 0; display: flex; flex-direction: column; overflow: hidden; border: 1px solid var(--tc-border, #30363c); background: var(--tc-window, #15191e); box-shadow: inset 0 1px rgba(255, 255, 255, 0.035); }
.tool-window--active { border-color: #607486; }
.tool-window__header { height: var(--tc-window-header-height); min-width: 0; display: flex; align-items: center; gap: 5px; padding: 0 4px; background: linear-gradient(var(--tc-header-top), var(--tc-header-bottom)); border-bottom: 1px solid #0d0f11; color: var(--tc-text); font: 600 11px/1 var(--tc-font-family); user-select: none; }
.tool-window__drag-handle { display: inline-flex; width: 12px; flex: 0 0 12px; align-items: center; justify-content: center; color: #748793; font-size: 11px; letter-spacing: -2px; cursor: grab; }
.tool-window__drag-handle:active { cursor: grabbing; }
.tool-window__drag-glyph { width: 8px; height: 10px; opacity: .9; background: radial-gradient(circle, currentColor 1px, transparent 1.5px) 0 0 / 4px 4px; }
.tool-window__menu-glyph { display: inline-block; width: 3px; height: 3px; border-radius: 50%; background: currentColor; box-shadow: 0 -4px currentColor, 0 4px currentColor; vertical-align: middle; }
.tool-window__maximize-glyph { display: inline-block; width: 9px; height: 9px; border: 1px solid currentColor; vertical-align: middle; }
.tool-window__float-glyph { position: relative; display: inline-block; width: 10px; height: 10px; vertical-align: middle; }
.tool-window__float-glyph::before { content: ''; position: absolute; right: 1px; top: 1px; width: 6px; height: 6px; border-top: 1px solid currentColor; border-right: 1px solid currentColor; }
.tool-window__float-glyph::after { content: ''; position: absolute; left: 1px; bottom: 1px; width: 7px; height: 1px; background: currentColor; transform: rotate(-45deg); transform-origin: left center; }
.tool-window__close-glyph { position: relative; display: inline-block; width: 10px; height: 10px; vertical-align: middle; }
.tool-window__close-glyph::before, .tool-window__close-glyph::after { content: ''; position: absolute; left: 4px; top: 0; width: 1px; height: 10px; background: currentColor; }
.tool-window__close-glyph::before { transform: rotate(45deg); }.tool-window__close-glyph::after { transform: rotate(-45deg); }
.tool-window__actions button { border: 0; color: #aab4bc; background: transparent; cursor: pointer; min-width: 17px; height: 20px; font-size: 12px; }
.tool-window__actions button:hover { color: #fff; background: #38414a; }
.tool-window__title { min-width: 0; flex: 1 1 auto; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tool-window__symbol { min-width: 0; max-width: 22%; color: #9fc2e0; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tool-window__actions { min-width: 0; margin-left: auto; display: flex; align-items: center; flex: 0 1 auto; overflow: visible; }
.tool-window__menu-wrap { position: relative; }
.tool-window__menu { z-index: 20; display: grid; min-width: 110px; overflow: auto; padding: 3px; border: 1px solid var(--tc-border-strong); background: #1a2025; box-shadow: 0 5px 14px rgba(0, 0, 0, .45); }
.tool-window__menu button { width: 100%; padding: 4px 7px; text-align: left; }
.tool-window__link { width: 54px; height: 18px; flex: 0 1 54px; min-width: 28px; color: var(--tc-text); border: 1px solid var(--tc-border-strong); background: var(--tc-input-bg); font: 10px var(--tc-font-family); }
.tool-window__link-swatch { width: 8px; height: 8px; flex: 0 0 8px; border: 1px solid #0b0f12; border-radius: 50%; box-shadow: 0 0 0 1px #65737d; }
.tool-window__timeframe { width: 27px; flex: 0 1 27px; min-width: 24px; height: 18px; color: var(--tc-text); border: 1px solid var(--tc-border-strong); background: var(--tc-input-bg); font: 10px var(--tc-font-family); }
.tool-window__timeframe-link { width: 54px; flex: 0 1 54px; min-width: 28px; height: 18px; color: var(--tc-text); border: 1px solid var(--tc-border-strong); background: var(--tc-input-bg); font: 10px var(--tc-font-family); }
.tool-window__body { min-width: 0; min-height: 0; flex: 1; overflow: hidden; }
@media (max-width: 420px) {
  .tool-window__header { gap: 2px; padding: 0 2px; }
  .tool-window__symbol { max-width: 18%; }
  .tool-window__actions { gap: 1px; }
  .tool-window__actions .tool-window__link-swatch { display: none; }
  .tool-window__link, .tool-window__timeframe-link { width: 32px; min-width: 24px; }
  .tool-window__timeframe { width: 24px; min-width: 22px; }
  .tool-window__actions button { min-width: 16px; padding: 0 1px; }
}
</style>
