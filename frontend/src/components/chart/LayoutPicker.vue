<template>
  <div ref="root" class="layout-picker" @keydown.capture="handleKeydown">
    <!-- Preset layout buttons -->
    <button
      v-for="opt in presets"
      :key="opt.value"
      type="button"
      :title="opt.label"
      :aria-label="opt.label"
      :aria-pressed="layoutStore.layout === opt.value"
      :class="['lp-btn', { active: layoutStore.layout === opt.value }]"
      @click="layoutStore.setLayout(opt.value)"
    >
      <svg :viewBox="opt.viewBox" width="20" height="14" fill="currentColor">
        <rect v-for="r in opt.rects" v-bind="r" :key="`${r.x}-${r.y}`" rx="1" />
      </svg>
    </button>

    <!-- Custom NxM grid picker -->
    <div class="custom-grid-wrap" @mouseleave="hoverCell = null">
      <button
        :id="gridTriggerId"
        type="button"
        :class="['lp-btn', { active: isCustomActive }]"
        title="Custom grid layout"
        ref="gridTrigger"
        aria-label="Custom grid layout"
        :aria-expanded="showGrid"
        :aria-controls="gridMenuId"
        aria-haspopup="menu"
        @click="toggleGrid()"
        @keydown="handleGridTriggerKeydown"
      >
        <svg viewBox="0 0 20 14" width="20" height="14" fill="currentColor">
          <rect x="1"  y="1"  width="5" height="5" rx="1" />
          <rect x="8"  y="1"  width="5" height="5" rx="1" />
          <rect x="15" y="1"  width="4" height="5" rx="1" />
          <rect x="1"  y="8"  width="5" height="5" rx="1" />
          <rect x="8"  y="8"  width="5" height="5" rx="1" />
          <rect x="15" y="8"  width="4" height="5" rx="1" />
        </svg>
      </button>

      <Transition name="grid-popup">
        <div v-if="showGrid" :id="gridMenuId" class="grid-popup" role="menu" aria-label="Custom grid layout" :aria-labelledby="gridTriggerId" :style="gridPopupStyle" @mouseleave="hoverCell = null" @keydown="handleGridMenuKeydown">
          <div class="grid-cells">
            <template v-for="row in MAX_ROWS" :key="row">
              <button
                v-for="col in MAX_COLS"
                :key="col"
                type="button"
                role="menuitem"
                :class="['grid-cell', { lit: isCellLit(col, row) }]"
                :aria-label="`${col} by ${row} layout`"
                :aria-current="layoutStore.layout === `${col}x${row}` || (col === 1 && row === 1 && layoutStore.layout === '1') ? 'true' : undefined"
                @mouseenter="hoverCell = { col, row }"
                @focus="hoverCell = { col, row }"
                @click="applyCustomGrid(col, row)"
              />
            </template>
          </div>
          <div class="grid-label">
            {{ hoverCell ? `${hoverCell.col} × ${hoverCell.row}` : 'Custom' }}
          </div>
        </div>
      </Transition>
    </div>

    <div class="lp-divider" />

    <!-- Crosshair sync toggle -->
    <button
      type="button"
      :class="['lp-btn', 'sync-btn', { active: layoutStore.isSyncEnabled }]"
      title="Sync crosshair across panels"
      aria-label="Sync crosshair across panels"
      :aria-pressed="layoutStore.isSyncEnabled"
      @click="layoutStore.toggleSync"
    >
      <svg viewBox="0 0 20 14" width="20" height="14" fill="none" stroke="currentColor" stroke-width="1.5">
        <line x1="4" y1="7" x2="16" y2="7" />
        <line x1="10" y1="2" x2="10" y2="12" />
        <circle cx="4"  cy="7" r="1.5" fill="currentColor" stroke="none" />
        <circle cx="16" cy="7" r="1.5" fill="currentColor" stroke="none" />
      </svg>
    </button>

    <div class="profile-wrap">
      <button :id="profileTriggerId" ref="profileTrigger" type="button" class="lp-btn" title="Layout profiles" aria-label="Layout profiles" aria-haspopup="menu" :aria-expanded="showProfiles" :aria-controls="profileMenuId" @click="toggleProfiles()" @keydown="handleProfileTriggerKeydown">P</button>
      <div v-if="showProfiles" :id="profileMenuId" class="profile-menu" role="menu" aria-label="Layout profiles" :aria-labelledby="profileTriggerId" :style="profileMenuStyle" @click.stop @keydown="handleProfileMenuKeydown">
        <button type="button" role="menuitem" class="profile-action" @click="saveProfile">Save current layout</button>
        <div class="profile-empty" v-if="!layoutStore.profiles.length">No saved profiles</div>
        <div v-for="profile in layoutStore.profiles" :key="profile.id" class="profile-row">
          <button type="button" role="menuitem" class="profile-load" @click="loadProfile(profile.id)">{{ profile.name }}</button>
          <button type="button" role="menuitem" class="profile-delete" :aria-label="`Delete ${profile.name}`" title="Delete profile" @click="layoutStore.deleteProfile(profile.id)">x</button>
        </div>
      </div>
    </div>

    <TextPromptModal
      v-model="showSaveProfileModal"
      title="Save Layout Profile"
      label="Profile name"
      placeholder="Layout profile name"
      confirm-label="Save"
      @submit="confirmSaveProfile"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import { useLayoutStore } from '@/stores/layout'
import type { PresetLayout } from '@/stores/layout'
import TextPromptModal from '@/components/common/TextPromptModal.vue'

const layoutStore = useLayoutStore()
const pickerId = useId()
const gridTriggerId = `${pickerId}-grid-trigger`
const gridMenuId = `${pickerId}-grid-menu`
const profileTriggerId = `${pickerId}-profile-trigger`
const profileMenuId = `${pickerId}-profile-menu`

const MAX_COLS = 6
const MAX_ROWS = 4

const showGrid  = ref(false)
const showProfiles = ref(false)
const showSaveProfileModal = ref(false)
const hoverCell = ref<{ col: number; row: number } | null>(null)
const gridTrigger = ref<HTMLButtonElement | null>(null)
const profileTrigger = ref<HTMLButtonElement | null>(null)
const root = ref<HTMLElement | null>(null)
const gridPopupStyle = ref<Record<string, string>>({})
const profileMenuStyle = ref<Record<string, string>>({})

const isCustomActive = computed(() => /^\d+x\d+$/.test(layoutStore.layout))

function isCellLit(col: number, row: number): boolean {
  if (!hoverCell.value) return false
  return col <= hoverCell.value.col && row <= hoverCell.value.row
}

function applyCustomGrid(cols: number, rows: number) {
  closePopups(false)
  // Single cell = single panel preset
  if (cols === 1 && rows === 1) { layoutStore.setLayout('1'); return }
  layoutStore.setLayout(`${cols}x${rows}`)
}

function positionPopup(trigger: HTMLButtonElement | null, width: number, maxHeight: number): Record<string, string> {
  const rect = trigger?.getBoundingClientRect()
  if (!rect) return { position: 'fixed' }
  const gutter = 8
  const boundedWidth = Math.min(width, Math.max(120, window.innerWidth - gutter * 2))
  const height = Math.min(maxHeight, Math.max(96, window.innerHeight - gutter * 2))
  const left = Math.max(gutter, Math.min(rect.right - boundedWidth, window.innerWidth - boundedWidth - gutter))
  const below = rect.bottom + 6
  const above = rect.top - height - 6
  const top = below + height <= window.innerHeight - gutter ? below : Math.max(gutter, above)
  return { position: 'fixed', left: `${Math.round(left)}px`, top: `${Math.round(top)}px`, width: `${Math.round(boundedWidth)}px`, maxHeight: `${Math.round(height)}px` }
}

function positionOpenPopups() {
  if (showGrid.value) gridPopupStyle.value = positionPopup(gridTrigger.value, 155, 150)
  if (showProfiles.value) profileMenuStyle.value = positionPopup(profileTrigger.value, 190, 280)
}

function addViewportListeners() {
  window.addEventListener('resize', positionOpenPopups)
  window.addEventListener('scroll', positionOpenPopups, true)
}

function removeViewportListeners() {
  window.removeEventListener('resize', positionOpenPopups)
  window.removeEventListener('scroll', positionOpenPopups, true)
}

function closePopups(restoreFocus = true) {
  const focusTarget = showGrid.value ? gridTrigger : profileTrigger
  const wasOpen = showGrid.value || showProfiles.value
  showGrid.value = false
  showProfiles.value = false
  hoverCell.value = null
  removeViewportListeners()
  removeDismissListener()
  if (wasOpen && restoreFocus) {
    void nextTick(() => focusTarget.value?.focus())
  }
}

function dismissOnOutsidePointer(event: PointerEvent) {
  const target = event.target as Node | null
  if (target && !root.value?.contains(target)) closePopups()
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && (showGrid.value || showProfiles.value)) {
    event.preventDefault()
    closePopups()
  }
}

function dismissOnEscape(event: KeyboardEvent) {
  handleKeydown(event)
}

function addDismissListener() {
  document.addEventListener('pointerdown', dismissOnOutsidePointer, true)
  document.addEventListener('keydown', dismissOnEscape, true)
}

function removeDismissListener() {
  document.removeEventListener('pointerdown', dismissOnOutsidePointer, true)
  document.removeEventListener('keydown', dismissOnEscape, true)
}

function focusMenuItem(rootElement: HTMLElement | null, index: number) {
  const items = Array.from(rootElement?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? [])
  if (!items.length) return
  const targetIndex = index < 0 ? items.length - 1 : Math.min(index, items.length - 1)
  items[Math.max(0, targetIndex)]?.focus()
}

function gridItems() {
  return Array.from(document.getElementById(gridMenuId)?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? [])
}

function profileItems() {
  return Array.from(document.getElementById(profileMenuId)?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? [])
}

function moveMenuFocus(event: KeyboardEvent, items: HTMLButtonElement[], delta: number) {
  const target = event.target instanceof HTMLButtonElement ? event.target : null
  const current = target ? items.indexOf(target) : -1
  if (current < 0) return
  event.preventDefault()
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : Math.max(0, Math.min(items.length - 1, current + delta))
  items[next]?.focus()
}

function handleGridTriggerKeydown(event: KeyboardEvent) {
  if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
  event.preventDefault()
  const last = MAX_COLS * MAX_ROWS - 1
  if (!showGrid.value) toggleGrid(event.key === 'ArrowUp' ? last : 0)
  else focusMenuItem(document.getElementById(gridMenuId), event.key === 'ArrowUp' ? last : 0)
}

function handleProfileTriggerKeydown(event: KeyboardEvent) {
  if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
  event.preventDefault()
  if (!showProfiles.value) toggleProfiles(event.key === 'ArrowUp' ? -1 : 0)
  else focusMenuItem(document.getElementById(profileMenuId), event.key === 'ArrowUp' ? -1 : 0)
}

function handleGridMenuKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') return
  const items = gridItems()
  if (event.key === 'ArrowRight') moveMenuFocus(event, items, 1)
  else if (event.key === 'ArrowLeft') moveMenuFocus(event, items, -1)
  else if (event.key === 'ArrowDown') moveMenuFocus(event, items, MAX_COLS)
  else if (event.key === 'ArrowUp') moveMenuFocus(event, items, -MAX_COLS)
  else if (event.key === 'Home' || event.key === 'End') moveMenuFocus(event, items, 0)
}

function handleProfileMenuKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') return
  const items = profileItems()
  if (event.key === 'ArrowDown') moveMenuFocus(event, items, 1)
  else if (event.key === 'ArrowUp') moveMenuFocus(event, items, -1)
  else if (event.key === 'Home' || event.key === 'End') moveMenuFocus(event, items, 0)
}

function toggleGrid(focusIndex?: number) {
  showProfiles.value = false
  showGrid.value = !showGrid.value
  if (showGrid.value) void nextTick(() => { positionOpenPopups(); addViewportListeners(); addDismissListener(); if (focusIndex !== undefined) focusMenuItem(document.getElementById(gridMenuId), focusIndex) })
  else { removeViewportListeners(); removeDismissListener() }
}

function toggleProfiles(focusIndex?: number) {
  showGrid.value = false
  showProfiles.value = !showProfiles.value
  if (showProfiles.value) void nextTick(() => { positionOpenPopups(); addViewportListeners(); addDismissListener(); if (focusIndex !== undefined) focusMenuItem(document.getElementById(profileMenuId), focusIndex) })
  else { removeViewportListeners(); removeDismissListener() }
}

function saveProfile() {
  showSaveProfileModal.value = true
  closePopups(false)
}

function confirmSaveProfile(name: string) {
  layoutStore.saveProfile(name)
  showSaveProfileModal.value = false
}

function loadProfile(id: string) {
  layoutStore.loadProfile(id)
  closePopups(false)
}

onMounted(() => positionOpenPopups())
onBeforeUnmount(() => { removeViewportListeners(); removeDismissListener() })

interface RectDef { x: number; y: number; width: number; height: number }

interface LayoutOption {
  value: PresetLayout
  label: string
  viewBox: string
  rects: RectDef[]
}

const presets: LayoutOption[] = [
  {
    value: '1',
    label: 'Single panel',
    viewBox: '0 0 20 14',
    rects: [{ x: 1, y: 1, width: 18, height: 12 }],
  },
  {
    value: '2h',
    label: 'Two columns',
    viewBox: '0 0 20 14',
    rects: [
      { x: 1, y: 1, width: 8, height: 12 },
      { x: 11, y: 1, width: 8, height: 12 },
    ],
  },
  {
    value: '2v',
    label: 'Two rows',
    viewBox: '0 0 20 14',
    rects: [
      { x: 1, y: 1, width: 18, height: 5 },
      { x: 1, y: 8, width: 18, height: 5 },
    ],
  },
  {
    value: '3l',
    label: 'Large left + two right',
    viewBox: '0 0 20 14',
    rects: [
      { x: 1, y: 1, width: 11, height: 12 },
      { x: 14, y: 1, width: 5, height: 5 },
      { x: 14, y: 8, width: 5, height: 5 },
    ],
  },
  {
    value: '3r',
    label: 'Two left + large right',
    viewBox: '0 0 20 14',
    rects: [
      { x: 1, y: 1, width: 5, height: 5 },
      { x: 1, y: 8, width: 5, height: 5 },
      { x: 8, y: 1, width: 11, height: 12 },
    ],
  },
  {
    value: '4',
    label: '2 × 2 grid',
    viewBox: '0 0 20 14',
    rects: [
      { x: 1, y: 1, width: 8, height: 5 },
      { x: 11, y: 1, width: 8, height: 5 },
      { x: 1, y: 8, width: 8, height: 5 },
      { x: 11, y: 8, width: 8, height: 5 },
    ],
  },
]
</script>

<style scoped>
.layout-picker {
  display: flex;
  align-items: center;
  gap: 2px;
}

.lp-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 26px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  cursor: pointer;
  color: #555;
  padding: 0;
  transition: color 0.15s, border-color 0.15s;
}

.lp-btn:hover { color: #aaa; border-color: #333; }
.lp-btn.active { color: #64b5f6; border-color: #2a3a4a; background: rgba(100, 181, 246, 0.06); }

.sync-btn { color: #555; }
.sync-btn.active { color: #26a69a; border-color: #1a3a38; background: rgba(38, 166, 154, 0.06); }

.lp-divider {
  width: 1px;
  height: 18px;
  background: #222;
  margin: 0 4px;
}

/* Custom grid picker */
.custom-grid-wrap {
  position: relative;
}

.profile-wrap {
  position: relative;
}

.profile-menu {
  z-index: 300;
  width: 190px;
  padding: 4px;
  background: #161616;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.6);
  overflow: auto;
}

.profile-action,
.profile-load,
.profile-delete {
  border: none;
  background: transparent;
  color: #aaa;
  font-family: monospace;
  font-size: 11px;
  cursor: pointer;
}
.profile-action {
  width: 100%;
  text-align: left;
  padding: 7px 8px;
  border-bottom: 1px solid #242424;
  color: #64b5f6;
}
.profile-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 22px;
  align-items: center;
}
.profile-load {
  min-width: 0;
  padding: 7px 8px;
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.profile-delete {
  color: #555;
  height: 24px;
}
.profile-action:hover,
.profile-load:hover,
.profile-delete:hover { background: #202020; color: #eee; }
.profile-delete:hover { color: #ef5350; }
.profile-empty {
  padding: 8px;
  color: #555;
  font-size: 11px;
}

.grid-popup {
  background: #161616;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  padding: 10px;
  z-index: 300;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6);
  white-space: nowrap;
  overflow: auto;
}

.grid-cells {
  display: grid;
  grid-template-columns: repeat(6, 18px);
  grid-template-rows: repeat(4, 18px);
  gap: 3px;
}

.grid-cell {
  width: 18px;
  height: 18px;
  padding: 0;
  appearance: none;
  color: inherit;
  font: inherit;
  border-radius: 2px;
  background: #222;
  border: 1px solid #333;
  cursor: pointer;
  transition: background 0.1s, border-color 0.1s;
}

.grid-cell.lit {
  background: rgba(100, 181, 246, 0.3);
  border-color: #64b5f6;
}

.grid-cell:hover {
  border-color: #64b5f6;
}

.grid-label {
  margin-top: 8px;
  text-align: center;
  font-size: 11px;
  color: #666;
  font-family: 'JetBrains Mono', monospace;
}

.grid-popup-enter-active,
.grid-popup-leave-active { transition: opacity 0.15s, transform 0.15s; }
.grid-popup-enter-from,
.grid-popup-leave-to { opacity: 0; transform: translateX(-50%) translateY(-4px); }
</style>
