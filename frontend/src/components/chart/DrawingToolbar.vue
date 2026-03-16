<template>
  <div class="drawing-toolbar">
    <div class="toolbar-group">
      <button
        v-for="tool in drawingTools"
        :key="tool.type"
        :class="['tool-btn', { active: activeToolType === tool.type }]"
        :title="tool.label"
        @click="toggleTool(tool.type)"
      >
        <span class="tool-icon" v-html="tool.icon" />
        <span class="tool-label">{{ tool.label }}</span>
      </button>
    </div>

    <div class="toolbar-divider" />

    <div class="toolbar-group">
      <button class="tool-btn" title="Delete selected" @click="deleteSelected" :disabled="!selectedId">
        <span class="tool-icon">🗑</span>
      </button>
      <button class="tool-btn" title="Toggle visibility" @click="toggleVisibility" :disabled="!selectedId">
        <span class="tool-icon">👁</span>
      </button>
      <button class="tool-btn" title="Lock drawing" @click="lockDrawing" :disabled="!selectedId">
        <span class="tool-icon">🔒</span>
      </button>
    </div>

    <div class="toolbar-divider" />

    <div class="toolbar-group">
      <button class="tool-btn escape-btn" title="Cancel / Escape" @click="cancelTool">
        <span class="tool-icon">✕</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useDrawingsStore } from '@/stores/drawings'
import type { DrawingType } from '@/types'

const drawStore = useDrawingsStore()
const activeToolType = computed(() => drawStore.activeToolType)
const selectedId     = computed(() => drawStore.selectedId)

const drawingTools: Array<{ type: DrawingType; label: string; icon: string }> = [
  { type: 'trendline',             label: 'Trend Line',         icon: '╱' },
  { type: 'horizontal_line',       label: 'Horizontal Line',    icon: '—' },
  { type: 'vertical_line',         label: 'Vertical Line',      icon: '|' },
  { type: 'ray',                   label: 'Ray',                icon: '→' },
  { type: 'fibonacci_retracement', label: 'Fibonacci Retr.',    icon: 'φ' },
  { type: 'fibonacci_extension',   label: 'Fibonacci Ext.',     icon: 'Φ' },
  { type: 'rectangle',             label: 'Rectangle',          icon: '▭' },
  { type: 'circle',                label: 'Circle / Ellipse',   icon: '◯' },
  { type: 'arrow',                 label: 'Arrow',              icon: '↗' },
  { type: 'text_box',              label: 'Text',               icon: 'T' },
]

function toggleTool(type: DrawingType) {
  drawStore.setActiveTool(activeToolType.value === type ? null : type)
}

function cancelTool() {
  drawStore.setActiveTool(null)
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
}

.toolbar-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
}

.toolbar-divider {
  width: 28px;
  height: 1px;
  background: #333;
  margin: 4px 0;
}

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

.tool-icon {
  font-size: 14px;
  line-height: 1;
}

.tool-label {
  display: none;
}
</style>
