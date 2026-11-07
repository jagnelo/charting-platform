<template>
  <div class="compact-status" :class="[`compact-status--${kind}`, { 'compact-status--open': open }]">
    <span :id="summaryId" class="compact-status__sr-only" :role="kind" :aria-live="kind === 'alert' ? 'assertive' : 'polite'" aria-atomic="true">{{ detail }}</span>
    <details @toggle="open = ($event.currentTarget as HTMLDetailsElement).open">
      <summary :aria-label="`${summary}. ${detail}`" :title="detail" :aria-describedby="summaryId">
        <span class="compact-status__summary" aria-hidden="true">{{ summary }}</span>
        <span class="compact-status__hint" aria-hidden="true">Details</span>
      </summary>
      <div :id="detailId" class="compact-status__detail">{{ detail }}</div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, useId } from 'vue'

withDefaults(defineProps<{
  summary: string
  detail: string
  kind?: 'status' | 'alert'
}>(), { kind: 'status' })

const id = useId()
const summaryId = `compact-status-summary-${id}`
const detailId = `compact-status-detail-${id}`
const open = ref(false)
</script>

<style scoped>
.compact-status {
  position: relative;
  display: inline-block;
  min-width: 0;
  max-width: 100%;
  color: var(--tc-text-muted, #9baab5);
  vertical-align: middle;
}
.compact-status details { position: relative; }
.compact-status summary {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  max-width: 100%;
  padding: 2px 4px;
  border: 1px solid var(--tc-border, #303940);
  border-radius: var(--tc-radius, 2px);
  background: var(--tc-control-bg, #172027);
  cursor: pointer;
  list-style: none;
}
.compact-status summary::-webkit-details-marker { display: none; }
.compact-status summary::marker { content: ''; }
.compact-status summary:focus-visible { outline: 2px solid var(--tc-focus, #80bce8); outline-offset: 1px; }
.compact-status__summary { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.compact-status__sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0; }
.compact-status__hint { flex: 0 0 auto; color: var(--tc-accent-soft, #9bc9e7); font-size: .9em; text-decoration: underline; text-underline-offset: 2px; }
.compact-status--alert summary { color: var(--tc-danger, #ed9696); }
.compact-status--open { z-index: 80; }
.compact-status__detail {
  position: absolute;
  z-index: 81;
  top: calc(100% + 4px);
  right: 0;
  box-sizing: border-box;
  width: min(360px, calc(100vw - 20px));
  max-height: min(45vh, 320px);
  overflow: auto;
  padding: 8px 10px;
  border: 1px solid var(--tc-border-strong, #526674);
  border-radius: var(--tc-radius, 2px);
  background: var(--tc-panel-bg, #172027);
  color: var(--tc-text, #dce6ed);
  box-shadow: 0 4px 14px #000b;
  font: 11px/1.4 var(--tc-font-family, "Segoe UI", Arial, sans-serif);
  white-space: normal;
  overflow-wrap: anywhere;
}
</style>
