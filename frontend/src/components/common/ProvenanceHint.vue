<template>
  <span
    v-if="title"
    class="prov-hint"
    :title="title"
  >i</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
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
  width: 12px;
  height: 12px;
  margin-left: 4px;
  border: 1px solid #2c2c2c;
  border-radius: 50%;
  color: #666;
  background: #141414;
  font-size: 9px;
  line-height: 1;
  cursor: help;
  flex-shrink: 0;
}
.prov-hint:hover {
  color: #8ab4f8;
  border-color: #35527a;
}
</style>
