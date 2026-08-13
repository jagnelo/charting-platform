<template>
  <div ref="toolbarRef" class="drawing-toolbar" @mouseleave="closeAllPopups">

    <!-- ── Tool groups ──────────────────────────────────────────────────── -->
    <div
      v-for="group in toolGroups"
      :key="group.id"
      class="toolbar-group"
    >
      <button
        :ref="element => setGroupTrigger(group.id, element)"
        :class="['tool-btn', 'group-btn', {
          active: openPopup === group.id || group.tools.some(t => t.type === activeToolType)
        }]"
        type="button"
        :title="group.label"
        :aria-label="group.label"
        aria-haspopup="menu"
        :aria-expanded="openPopup === group.id ? 'true' : 'false'"
        :aria-controls="openPopup === group.id ? menuId(group.id) : undefined"
        @click.stop="togglePopup(group.id)"
        @keydown="handleGroupTriggerKeydown(group.id, $event)"
      >
        <span class="tool-icon" :class="`tool-icon--${group.icon}`" aria-hidden="true" />
      </button>

      <!-- Popup flyout -->
      <Transition name="popup">
        <div :id="menuId(group.id)" class="tool-popup" v-if="openPopup === group.id" role="menu" :aria-label="`${group.label} drawing tools`" @click.stop @keydown="handlePopupKeydown(group.id, $event)">
          <div class="popup-title">{{ group.label }}</div>
          <button
            v-for="tool in group.tools"
            :key="tool.type"
            :class="['tool-btn', 'popup-tool', { active: activeToolType === tool.type }]"
            type="button"
            role="menuitem"
            tabindex="-1"
            :title="tool.label"
            :aria-label="tool.label"
            @click="selectTool(tool.type)"
          >
            <span class="tool-icon" :class="`tool-icon--${tool.icon}`" aria-hidden="true" />
            <span class="popup-label">{{ tool.label }}</span>
          </button>
        </div>
      </Transition>
    </div>

    <!-- ── AVWAP drop ───────────────────────────────────────────────────── -->
    <div class="toolbar-divider" />
    <button
      :class="['tool-btn', { active: drawStore.avwapDropActive }]"
      type="button"
      title="Anchored VWAP — click on chart to set anchor"
      aria-label="Anchored VWAP — click on chart to set anchor"
      @click="toggleAvwapDrop"
    >
      <span class="tool-icon tool-icon--avwap" aria-hidden="true" />
    </button>

    <!-- ── Divider + utility actions ───────────────────────────────────── -->
    <div class="toolbar-divider" />

    <button class="tool-btn" type="button" title="Delete selected" aria-label="Delete selected" @click="deleteSelected" :disabled="!selectedId">
      <span class="tool-icon tool-icon--delete" aria-hidden="true" />
    </button>
    <button class="tool-btn" type="button" title="Toggle visibility" aria-label="Toggle visibility" @click="toggleVisibility" :disabled="!selectedId">
      <span class="tool-icon tool-icon--visibility" aria-hidden="true" />
    </button>
    <button class="tool-btn" type="button" title="Lock / Unlock drawing" aria-label="Lock / Unlock drawing" @click="lockDrawing" :disabled="!selectedId">
      <span class="tool-icon tool-icon--lock" aria-hidden="true" />
    </button>

    <div class="toolbar-divider" />

    <button class="tool-btn escape-btn" type="button" title="Cancel / Escape (Esc)" aria-label="Cancel / Escape (Esc)" @click="cancelTool">
      <span class="tool-icon tool-icon--cancel" aria-hidden="true" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref, computed, type ComponentPublicInstance } from 'vue'
import { useDrawingsStore } from '@/stores/drawings'
import type { DrawingType } from '@/types'

const drawStore      = useDrawingsStore()
const activeToolType = computed(() => drawStore.activeToolType)
const selectedId     = computed(() => drawStore.selectedId)

const toolbarRef = ref<HTMLElement | null>(null)
const openPopup = ref<string | null>(null)
const groupTriggers = new Map<string, HTMLButtonElement>()
const toolbarInstanceId = `toolbar-${globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`}`

function menuId(groupId: string) {
  return `drawing-toolbar-menu-${toolbarInstanceId}-${groupId}`
}

function setGroupTrigger(id: string, element: Element | ComponentPublicInstance | null) {
  if (element instanceof HTMLButtonElement) groupTriggers.set(id, element)
  else if (element && '$el' in element && element.$el instanceof HTMLButtonElement) groupTriggers.set(id, element.$el)
  else groupTriggers.delete(id)
}

interface ToolDef { type: DrawingType; label: string; icon: string }
interface GroupDef { id: string; label: string; icon: string; tools: ToolDef[] }

const toolGroups: GroupDef[] = [
  {
    id: 'lines',
    label: 'Lines',
    icon: 'line',
    tools: [
      { type: 'trendline',       label: 'Trend Line',      icon: 'line' },
      { type: 'ray',             label: 'Ray',             icon: 'ray' },
      { type: 'horizontal_line', label: 'Horizontal Line', icon: 'horizontal' },
      { type: 'vertical_line',   label: 'Vertical Line',   icon: 'vertical' },
    ],
  },
  {
    id: 'fibonacci',
    label: 'Fibonacci',
    icon: 'fibonacci',
    tools: [
      { type: 'fibonacci_retracement', label: 'Fibonacci Retracement', icon: 'fibonacci' },
      { type: 'fibonacci_extension',   label: 'Fibonacci Extension',   icon: 'fibonacci-extension' },
    ],
  },
  {
    id: 'shapes',
    label: 'Shapes',
    icon: 'rectangle',
    tools: [
      { type: 'rectangle', label: 'Rectangle',      icon: 'rectangle' },
      { type: 'circle',    label: 'Circle/Ellipse', icon: 'circle' },
      { type: 'half_circle', label: 'Half Circle',  icon: 'half-circle' },
    ],
  },
  {
    id: 'annotations',
    label: 'Annotations',
    icon: 'text',
    tools: [
      { type: 'arrow',    label: 'Arrow',    icon: 'arrow' },
      { type: 'text_box', label: 'Text',     icon: 'text' },
      { type: 'freehand', label: 'Freehand', icon: 'freehand' },
    ],
  },
]

function popupItems(id: string) {
  return Array.from(toolbarRef.value?.querySelectorAll<HTMLButtonElement>(`#${menuId(id)} [role="menuitem"]`) ?? [])
}

function focusPopupItem(id: string, index: number) {
  const items = popupItems(id)
  if (!items.length) return
  items[Math.max(0, Math.min(index, items.length - 1))]?.focus()
}

function setPopup(id: string | null, focusIndex = 0) {
  openPopup.value = id
  if (id) void nextTick(() => focusPopupItem(id, focusIndex))
}

function togglePopup(id: string) {
  setPopup(openPopup.value === id ? null : id)
}

function closeAllPopups() {
  openPopup.value = null
}

function closePopupToTrigger(id: string) {
  setPopup(null)
  void nextTick(() => groupTriggers.get(id)?.focus())
}

function handleGroupTriggerKeydown(id: string, event: KeyboardEvent) {
  if (event.key === 'Enter' || event.key === ' ' || event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    setPopup(id, event.key === 'ArrowUp' ? popupItems(id).length - 1 : 0)
  }
}

function handlePopupKeydown(id: string, event: KeyboardEvent) {
  const items = popupItems(id)
  const target = event.target instanceof HTMLButtonElement ? event.target : null
  const currentIndex = target ? items.indexOf(target) : -1
  if (!items.length) return
  if (event.key === 'Escape') {
    event.preventDefault()
    closePopupToTrigger(id)
  } else if (event.key === 'ArrowDown' || event.key === 'ArrowRight') {
    event.preventDefault()
    focusPopupItem(id, (currentIndex + 1 + items.length) % items.length)
  } else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') {
    event.preventDefault()
    focusPopupItem(id, (currentIndex - 1 + items.length) % items.length)
  } else if (event.key === 'Home') {
    event.preventDefault()
    focusPopupItem(id, 0)
  } else if (event.key === 'End') {
    event.preventDefault()
    focusPopupItem(id, items.length - 1)
  } else if ((event.key === 'Enter' || event.key === ' ') && target) {
    event.preventDefault()
    target.click()
  }
}

function selectTool(type: DrawingType) {
  drawStore.setActiveTool(activeToolType.value === type ? null : type)
  setPopup(null)
}

function toggleAvwapDrop() {
  drawStore.setAvwapDrop(!drawStore.avwapDropActive)
}

function cancelTool() {
  drawStore.setActiveTool(null)
  drawStore.setAvwapDrop(false)
  setPopup(null)
}

async function deleteSelected() {
  if (selectedId.value) await drawStore.deleteDrawing(selectedId.value)
}

async function toggleVisibility() {
  const drawing = drawStore.drawings.find(d => d.id === selectedId.value)
  if (!drawing) return
  await drawStore.updateDrawing(drawing.id, { is_visible: !drawing.is_visible })
}

async function lockDrawing() {
  const drawing = drawStore.drawings.find(d => d.id === selectedId.value)
  if (!drawing) return
  await drawStore.updateDrawing(drawing.id, { is_locked: !drawing.is_locked })
}
</script>

<style scoped>
.drawing-toolbar {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 5px 3px;
  background: #12171c;
  border-right: 1px solid #2b353c;
  min-width: 40px;
  position: relative;
  z-index: 50;
  user-select: none;
}

.toolbar-group {
  position: relative;
  width: 100%;
  display: flex;
  justify-content: center;
}

.toolbar-divider {
  width: 26px;
  height: 1px;
  background: #334149;
  margin: 3px 0;
}

/* ── Buttons ──────────────────────────────────────────────────────────── */
.tool-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid transparent;
  border-radius: 2px;
  background: transparent;
  color: #aab7bf;
  cursor: pointer;
  transition: background 0.1s, color 0.1s;
  font-size: 11px;
  padding: 0;
  flex-shrink: 0;
}

.tool-btn:hover:not(:disabled) {
  background: #1d2a32;
  color: #e1edf3;
}

.tool-btn.active {
  background: #17364d;
  color: #7fc7f7;
  border-color: #4c9bd0;
}

.tool-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.group-btn.active {
  background: #182b39;
  color: #9bd4fa;
  border-color: #365e78;
}

.tool-icon {
  position: relative;
  display: block;
  width: 16px;
  height: 16px;
  line-height: 1;
}

/* Deterministic, original geometric glyphs. These deliberately avoid emoji and
   platform-dependent Unicode symbols so the compact chart toolbar has stable
   geometry across browsers and display scales. */
.tool-icon::before,
.tool-icon::after {
  position: absolute;
  display: block;
  content: '';
  box-sizing: border-box;
}
.tool-icon--line::before { left: 2px; top: 7px; width: 13px; height: 1px; background: currentColor; transform: rotate(-35deg); transform-origin: center; }
.tool-icon--ray::before { left: 2px; top: 8px; width: 12px; height: 1px; background: currentColor; transform: rotate(-25deg); transform-origin: left center; }
.tool-icon--ray::after { right: 0; top: 5px; width: 5px; height: 5px; border-top: 1px solid currentColor; border-right: 1px solid currentColor; transform: rotate(22deg); }
.tool-icon--horizontal::before { left: 1px; top: 8px; width: 14px; height: 1px; background: currentColor; }
.tool-icon--vertical::before { left: 8px; top: 1px; width: 1px; height: 14px; background: currentColor; }
.tool-icon--fibonacci::before { left: 2px; top: 2px; width: 12px; height: 12px; border-top: 1px solid currentColor; border-bottom: 1px solid currentColor; transform: skewY(-28deg); }
.tool-icon--fibonacci::after { left: 4px; top: 5px; width: 8px; height: 1px; background: currentColor; box-shadow: 0 3px currentColor; transform: rotate(-28deg); }
.tool-icon--fibonacci-extension::before { left: 2px; top: 2px; width: 1px; height: 13px; background: currentColor; box-shadow: 5px 0 currentColor, 10px 0 currentColor; }
.tool-icon--fibonacci-extension::after { left: 2px; top: 4px; width: 12px; height: 1px; background: currentColor; transform: rotate(24deg); box-shadow: 0 5px currentColor; }
.tool-icon--rectangle::before { left: 2px; top: 3px; width: 12px; height: 10px; border: 1px solid currentColor; }
.tool-icon--circle::before { left: 2px; top: 2px; width: 12px; height: 12px; border: 1px solid currentColor; border-radius: 50%; }
.tool-icon--half-circle::before { left: 2px; top: 2px; width: 12px; height: 12px; border: 1px solid currentColor; border-radius: 50% 50% 0 0; }
.tool-icon--arrow::before { left: 2px; top: 9px; width: 12px; height: 1px; background: currentColor; transform: rotate(-35deg); transform-origin: left center; }
.tool-icon--arrow::after { right: 0; top: 3px; width: 6px; height: 6px; border-top: 1px solid currentColor; border-right: 1px solid currentColor; transform: rotate(10deg); }
.tool-icon--text::before { left: 3px; top: 2px; width: 10px; height: 12px; border-top: 2px solid currentColor; }
.tool-icon--text::after { left: 8px; top: 3px; width: 1px; height: 11px; background: currentColor; }
.tool-icon--freehand::before { left: 2px; top: 8px; width: 12px; height: 6px; border-top: 1px solid currentColor; border-radius: 50%; transform: rotate(-25deg); }
.tool-icon--freehand::after { right: 0; top: 2px; width: 4px; height: 4px; border: 1px solid currentColor; transform: rotate(35deg); }
.tool-icon--avwap::before { left: 7px; top: 1px; width: 3px; height: 13px; background: currentColor; border-radius: 2px; }
.tool-icon--avwap::after { left: 3px; top: 8px; width: 11px; height: 5px; border: 1px solid currentColor; border-top: 0; border-radius: 0 0 8px 8px; }
.tool-icon--delete::before { left: 4px; top: 5px; width: 8px; height: 9px; border: 1px solid currentColor; border-top: 0; }
.tool-icon--delete::after { left: 3px; top: 3px; width: 10px; height: 1px; background: currentColor; box-shadow: 3px -2px 0 -0.5px currentColor; }
.tool-icon--visibility::before { left: 1px; top: 4px; width: 14px; height: 8px; border: 1px solid currentColor; border-radius: 50% / 60%; }
.tool-icon--visibility::after { left: 7px; top: 7px; width: 3px; height: 3px; background: currentColor; border-radius: 50%; }
.tool-icon--lock::before { left: 3px; top: 7px; width: 10px; height: 8px; border: 1px solid currentColor; border-radius: 1px; }
.tool-icon--lock::after { left: 5px; top: 2px; width: 6px; height: 7px; border: 1px solid currentColor; border-bottom: 0; border-radius: 5px 5px 0 0; }
.tool-icon--cancel::before,
.tool-icon--cancel::after { left: 7px; top: 1px; width: 1px; height: 14px; background: currentColor; }
.tool-icon--cancel::before { transform: rotate(45deg); }
.tool-icon--cancel::after { transform: rotate(-45deg); }

/* ── Popup flyout ─────────────────────────────────────────────────────── */
.tool-popup {
  position: absolute;
  left: calc(100% + 6px);
  top: 0;
  background: #151c21;
  border: 1px solid #394852;
  border-radius: 2px;
  padding: 4px;
  min-width: 180px;
  z-index: 200;
  box-shadow: 0 3px 12px rgba(0,0,0,0.55);
}

.popup-title {
  font-size: 10px;
  color: #71818b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 2px 4px 5px;
  border-bottom: 1px solid #2d3941;
  margin-bottom: 3px;
}

.popup-tool {
  width: 100%;
  height: 29px;
  flex-direction: row;
  gap: 7px;
  justify-content: flex-start;
  padding: 0 8px;
  border-radius: 2px;
}

.popup-label {
  font-size: 11px;
  color: inherit;
  white-space: nowrap;
}

/* ── Popup transition ─────────────────────────────────────────────────── */
.popup-enter-active,
.popup-leave-active {
  transition: opacity 0.1s ease, transform 0.1s ease;
}
.popup-enter-from,
.popup-leave-to {
  opacity: 0;
  transform: translateX(-4px);
}
</style>
