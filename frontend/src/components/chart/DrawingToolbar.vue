<template>
  <div class="drawing-toolbar" @mouseleave="closeAllPopups">

    <!-- ── Tool groups ──────────────────────────────────────────────────── -->
    <div
      v-for="group in toolGroups"
      :key="group.id"
      class="toolbar-group"
    >
      <button
        :class="['tool-btn', 'group-btn', {
          active: openPopup === group.id || group.tools.some(t => t.type === activeToolType)
        }]"
        :title="group.label"
        @click.stop="togglePopup(group.id)"
      >
        <span class="tool-icon" v-html="group.icon" />
      </button>

      <!-- Popup flyout -->
      <Transition name="popup">
        <div class="tool-popup" v-if="openPopup === group.id" @click.stop>
          <div class="popup-title">{{ group.label }}</div>
          <button
            v-for="tool in group.tools"
            :key="tool.type"
            :class="['tool-btn', 'popup-tool', { active: activeToolType === tool.type }]"
            :title="tool.label"
            @click="selectTool(tool.type)"
          >
            <span class="tool-icon" v-html="tool.icon" />
            <span class="popup-label">{{ tool.label }}</span>
          </button>
        </div>
      </Transition>
    </div>

    <!-- ── AVWAP drop ───────────────────────────────────────────────────── -->
    <div class="toolbar-divider" />
    <button
      :class="['tool-btn', { active: drawStore.avwapDropActive }]"
      title="Anchored VWAP — click on chart to set anchor"
      @click="toggleAvwapDrop"
    >
      <span class="tool-icon avwap-icon">⚓</span>
    </button>

    <!-- ── Divider + utility actions ───────────────────────────────────── -->
    <div class="toolbar-divider" />

    <button class="tool-btn" title="Delete selected" @click="deleteSelected" :disabled="!selectedId">
      <span class="tool-icon">🗑</span>
    </button>
    <button class="tool-btn" title="Toggle visibility" @click="toggleVisibility" :disabled="!selectedId">
      <span class="tool-icon">👁</span>
    </button>
    <button class="tool-btn" title="Lock / Unlock drawing" @click="lockDrawing" :disabled="!selectedId">
      <span class="tool-icon">🔒</span>
    </button>

    <div class="toolbar-divider" />

    <button class="tool-btn escape-btn" title="Cancel / Escape (Esc)" @click="cancelTool">
      <span class="tool-icon">✕</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useDrawingsStore } from '@/stores/drawings'
import type { DrawingType } from '@/types'

const drawStore      = useDrawingsStore()
const activeToolType = computed(() => drawStore.activeToolType)
const selectedId     = computed(() => drawStore.selectedId)

const openPopup = ref<string | null>(null)

interface ToolDef { type: DrawingType; label: string; icon: string }
interface GroupDef { id: string; label: string; icon: string; tools: ToolDef[] }

const toolGroups: GroupDef[] = [
  {
    id: 'lines',
    label: 'Lines',
    icon: '╱',
    tools: [
      { type: 'trendline',       label: 'Trend Line',      icon: '╱' },
      { type: 'ray',             label: 'Ray',             icon: '→' },
      { type: 'horizontal_line', label: 'Horizontal Line', icon: '—' },
      { type: 'vertical_line',   label: 'Vertical Line',   icon: '|' },
    ],
  },
  {
    id: 'fibonacci',
    label: 'Fibonacci',
    icon: 'φ',
    tools: [
      { type: 'fibonacci_retracement', label: 'Fibonacci Retracement', icon: 'φ' },
      { type: 'fibonacci_extension',   label: 'Fibonacci Extension',   icon: 'Φ' },
    ],
  },
  {
    id: 'shapes',
    label: 'Shapes',
    icon: '▭',
    tools: [
      { type: 'rectangle', label: 'Rectangle',      icon: '▭' },
      { type: 'circle',    label: 'Circle/Ellipse', icon: '◯' },
    ],
  },
  {
    id: 'annotations',
    label: 'Annotations',
    icon: 'T',
    tools: [
      { type: 'arrow',    label: 'Arrow', icon: '↗' },
      { type: 'text_box', label: 'Text',  icon: 'T' },
    ],
  },
]

function togglePopup(id: string) {
  openPopup.value = openPopup.value === id ? null : id
}

function closeAllPopups() {
  openPopup.value = null
}

function selectTool(type: DrawingType) {
  drawStore.setActiveTool(activeToolType.value === type ? null : type)
  openPopup.value = null
}

function toggleAvwapDrop() {
  drawStore.setAvwapDrop(!drawStore.avwapDropActive)
}

function cancelTool() {
  drawStore.setActiveTool(null)
  drawStore.setAvwapDrop(false)
  openPopup.value = null
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
  padding: 8px 4px;
  background: #111;
  border-right: 1px solid #222;
  min-width: 44px;
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
  width: 28px;
  height: 1px;
  background: #333;
  margin: 4px 0;
}

/* ── Buttons ──────────────────────────────────────────────────────────── */
.tool-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: #888;
  cursor: pointer;
  transition: background 0.1s, color 0.1s;
  font-size: 14px;
  padding: 0;
  flex-shrink: 0;
}

.tool-btn:hover:not(:disabled) {
  background: #1e1e1e;
  color: #ccc;
}

.tool-btn.active {
  background: #1a3a5c;
  color: #64b5f6;
  border: 1px solid #64b5f6;
}

.tool-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.group-btn.active {
  background: #1a2a3a;
  color: #90caf9;
  border: 1px solid #2a4a6a;
}

.tool-icon {
  font-size: 14px;
  line-height: 1;
}

.avwap-icon { font-size: 12px; }

/* ── Popup flyout ─────────────────────────────────────────────────────── */
.tool-popup {
  position: absolute;
  left: calc(100% + 6px);
  top: 0;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 6px;
  min-width: 180px;
  z-index: 200;
  box-shadow: 0 4px 16px rgba(0,0,0,0.6);
}

.popup-title {
  font-size: 10px;
  color: #555;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 2px 4px 6px;
  border-bottom: 1px solid #2a2a2a;
  margin-bottom: 4px;
}

.popup-tool {
  width: 100%;
  height: 32px;
  flex-direction: row;
  gap: 8px;
  justify-content: flex-start;
  padding: 0 8px;
  border-radius: 4px;
}

.popup-label {
  font-size: 12px;
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
