<template>
  <div class="multi-layout" :class="layoutClass" :style="layoutStyle">
    <ChartPanel
      v-for="panel in layoutStore.panels"
      :key="panel.id"
      :panel-id="panel.id"
      :class="`panel-slot-${panel.id}`"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useLayoutStore, parseLayoutGrid } from '@/stores/layout'
import ChartPanel from '@/components/chart/ChartPanel.vue'

const layoutStore = useLayoutStore()

const layoutClass = computed(() => {
  // Only apply preset class names; NxM grids use inline styles
  const l = layoutStore.layout
  if (['2h', '2v', '3l', '3r', '4'].includes(l)) return `layout-${l}`
  return ''
})

const layoutStyle = computed(() => {
  const grid = parseLayoutGrid(layoutStore.layout)
  if (!grid) return {}
  return {
    gridTemplateColumns: `repeat(${grid.cols}, 1fr)`,
    gridTemplateRows:    `repeat(${grid.rows}, 1fr)`,
  }
})
</script>

<style scoped>
.multi-layout {
  display: grid;
  flex: 1;
  min-width: 0;
  min-height: 0;
  gap: 0;
}

/* ── 2 horizontal (side by side) ─────────────────── */
.layout-2h {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr;
}

/* ── 2 vertical (stacked) ────────────────────────── */
.layout-2v {
  grid-template-columns: 1fr;
  grid-template-rows: 1fr 1fr;
}

/* ── 3 large left ────────────────────────────────── */
.layout-3l {
  grid-template-columns: 2fr 1fr;
  grid-template-rows: 1fr 1fr;
  grid-template-areas:
    "main top-right"
    "main bottom-right";
}
.layout-3l .panel-slot-p0 { grid-area: main; }
.layout-3l .panel-slot-p1 { grid-area: top-right; }
.layout-3l .panel-slot-p2 { grid-area: bottom-right; }

/* ── 3 large right ───────────────────────────────── */
.layout-3r {
  grid-template-columns: 1fr 2fr;
  grid-template-rows: 1fr 1fr;
  grid-template-areas:
    "top-left main"
    "bottom-left main";
}
.layout-3r .panel-slot-p0 { grid-area: top-left; }
.layout-3r .panel-slot-p1 { grid-area: bottom-left; }
.layout-3r .panel-slot-p2 { grid-area: main; }

/* ── 4 panels 2 × 2 ──────────────────────────────── */
.layout-4 {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
}
</style>
