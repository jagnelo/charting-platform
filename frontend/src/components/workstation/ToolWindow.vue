<template>
  <section class="tool-window" :class="{ 'tool-window--active': active }">
    <header class="tool-window__header">
      <strong class="tool-window__title">{{ title }}</strong>
      <span v-if="symbol" class="tool-window__symbol">{{ symbol }}</span>
      <div class="tool-window__actions">
        <select v-if="timeframe" :value="timeframeLinkGroup" class="tool-window__timeframe-link" :aria-label="title + ' timeframe link group'" @change="emit('update:timeframeLinkGroup', ($event.target as HTMLSelectElement).value as LinkGroup)">
          <option v-for="group in groups" :key="group" :value="group">{{ group }}</option>
        </select>
        <select v-if="timeframe" :value="timeframe" class="tool-window__timeframe" :aria-label="title + ' timeframe'" @change="emit('update:timeframe', ($event.target as HTMLSelectElement).value)">
          <option value="M1">1m</option><option value="M5">5m</option><option value="M15">15m</option><option value="M30">30m</option><option value="H1">1h</option><option value="H2">2h</option><option value="H4">4h</option><option value="H12">12h</option><option value="D1">D</option><option value="W1">W</option><option value="MN">M</option>
        </select>
        <select
          :value="linkGroup"
          class="tool-window__link"
          :aria-label="title + ' symbol link group'"
          @change="emit('update:linkGroup', ($event.target as HTMLSelectElement).value as LinkGroup)"
        >
          <option v-for="group in groups" :key="group" :value="group">{{ group }}</option>
        </select>
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
import type { LinkGroup } from '@/stores/workspace'

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
  maximize: []
  float: []
  close: []
}>()

const groups: LinkGroup[] = ['blue', 'red', 'green', 'purple', 'orange', 'cyan', 'pink', 'brown', 'yellow', 'grey']
</script>

<style scoped>
.tool-window { min-width: 0; min-height: 0; display: flex; flex-direction: column; border: 1px solid var(--tc-border, #30363c); background: var(--tc-window, #15191e); box-shadow: inset 0 1px rgba(255, 255, 255, 0.035); }
.tool-window--active { border-color: #607486; }
.tool-window__header { height: 25px; display: flex; align-items: center; gap: 5px; padding: 0 4px; background: linear-gradient(#2a3036, #1d2227); border-bottom: 1px solid #0d0f11; color: #d7dce0; font: 600 11px/1 "Segoe UI", Arial, sans-serif; user-select: none; }
.tool-window__actions button { border: 0; color: #aab4bc; background: transparent; cursor: pointer; min-width: 17px; height: 20px; font-size: 12px; }
.tool-window__actions button:hover { color: #fff; background: #38414a; }
.tool-window__title { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tool-window__symbol { color: #9fc2e0; font-weight: 700; }
.tool-window__actions { margin-left: auto; display: flex; align-items: center; }
.tool-window__link { width: 54px; height: 18px; color: #d7dce0; border: 1px solid #4b5660; background: #161b20; font: 10px "Segoe UI", Arial, sans-serif; }
.tool-window__timeframe { width: 27px; height: 18px; color: #d7dce0; border: 1px solid #4b5660; background: #161b20; font: 10px "Segoe UI", Arial, sans-serif; }
.tool-window__timeframe-link { width: 54px; height: 18px; color: #d7dce0; border: 1px solid #4b5660; background: #161b20; font: 10px "Segoe UI", Arial, sans-serif; }
.tool-window__body { min-width: 0; min-height: 0; flex: 1; overflow: hidden; }
</style>
