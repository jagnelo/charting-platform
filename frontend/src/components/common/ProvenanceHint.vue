<template>
  <HoverTooltip v-if="title" :text="title">
    <span class="prov-hint">i</span>
  </HoverTooltip>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import HoverTooltip from '@/components/common/HoverTooltip.vue'
import type { FieldProvenance } from '@/types'

const props = defineProps<{
  provenance?: FieldProvenance | null
  label?: string
}>()

const title = computed(() => {
  const p = props.provenance
  if (!p) return ''
  const lines = [
    props.label ? `${props.label}` : 'Field provenance',
    `Source: ${p.source}`,
  ]
  if (p.provider_symbol) lines.push(`Provider symbol: ${p.provider_symbol}`)
  if (p.observed_at) lines.push(`Observed: ${new Date(p.observed_at).toLocaleString()}`)
  if (p.fetched_at) lines.push(`Fetched: ${new Date(p.fetched_at).toLocaleString()}`)
  if (p.selection_reason) lines.push(`Reason: ${p.selection_reason}`)
  if (p.quality_score != null) lines.push(`Quality score: ${p.quality_score.toFixed(2)}`)
  if (p.note) lines.push(`Note: ${p.note}`)
  return lines.join('\n')
})
</script>

<style scoped>
.prov-hint {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 9px;
  height: 9px;
  margin-left: 2px;
  border: 1px solid #2c2c2c;
  border-radius: 50%;
  color: #666;
  background: #141414;
  font-family: ui-sans-serif, system-ui, sans-serif;
  font-size: 7px;
  font-weight: 700;
  font-style: normal;
  text-transform: none;
  letter-spacing: 0;
  line-height: 1;
  cursor: help;
  flex-shrink: 0;
  vertical-align: super;
  transform: translateY(-0.2em);
}
.prov-hint:hover {
  color: #8ab4f8;
  border-color: #35527a;
}
</style>
