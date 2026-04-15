<template>
  <div class="layout-picker">
    <!-- Preset layout buttons -->
    <button
      v-for="opt in presets"
      :key="opt.value"
      :title="opt.label"
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
        :class="['lp-btn', { active: isCustomActive }]"
        title="Custom grid layout"
        @click="showGrid = !showGrid"
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
        <div v-if="showGrid" class="grid-popup" @mouseleave="hoverCell = null">
          <div class="grid-cells">
            <template v-for="row in MAX_ROWS" :key="row">
              <div
                v-for="col in MAX_COLS"
                :key="col"
                :class="['grid-cell', { lit: isCellLit(col, row) }]"
                @mouseenter="hoverCell = { col, row }"
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
      :class="['lp-btn', 'sync-btn', { active: layoutStore.isSyncEnabled }]"
      title="Sync crosshair across panels"
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
      <button class="lp-btn" title="Layout profiles" @click="showProfiles = !showProfiles">P</button>
      <div v-if="showProfiles" class="profile-menu" @click.stop>
        <button class="profile-action" @click="saveProfile">Save current layout</button>
        <div class="profile-empty" v-if="!layoutStore.profiles.length">No saved profiles</div>
        <div v-for="profile in layoutStore.profiles" :key="profile.id" class="profile-row">
          <button class="profile-load" @click="loadProfile(profile.id)">{{ profile.name }}</button>
          <button class="profile-delete" title="Delete profile" @click="layoutStore.deleteProfile(profile.id)">x</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useLayoutStore } from '@/stores/layout'
import type { PresetLayout } from '@/stores/layout'

const layoutStore = useLayoutStore()

const MAX_COLS = 6
const MAX_ROWS = 4

const showGrid  = ref(false)
const showProfiles = ref(false)
const hoverCell = ref<{ col: number; row: number } | null>(null)

const isCustomActive = computed(() => /^\d+x\d+$/.test(layoutStore.layout))

function isCellLit(col: number, row: number): boolean {
  if (!hoverCell.value) return false
  return col <= hoverCell.value.col && row <= hoverCell.value.row
}

function applyCustomGrid(cols: number, rows: number) {
  showGrid.value  = false
  hoverCell.value = null
  // Single cell = single panel preset
  if (cols === 1 && rows === 1) { layoutStore.setLayout('1'); return }
  layoutStore.setLayout(`${cols}x${rows}`)
}

function saveProfile() {
  const name = prompt('Layout profile name:')
  if (name?.trim()) layoutStore.saveProfile(name)
  showProfiles.value = false
}

function loadProfile(id: string) {
  layoutStore.loadProfile(id)
  showProfiles.value = false
}

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
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 300;
  width: 190px;
  padding: 4px;
  background: #161616;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.6);
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
  position: absolute;
  top: calc(100% + 6px);
  left: 50%;
  transform: translateX(-50%);
  background: #161616;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  padding: 10px;
  z-index: 300;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6);
  white-space: nowrap;
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
