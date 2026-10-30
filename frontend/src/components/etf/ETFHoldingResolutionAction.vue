<template>
  <div v-if="available && eligible" class="holding-resolution-action">
    <button v-if="!active" type="button" @click="active = true">
      Resolve reported holding {{ reportedSymbol }}
    </button>
    <div v-else class="holding-resolution-picker">
      <p>Search free sources for the reported ticker {{ reportedSymbol }}, then explicitly resolve a matching candidate.</p>
      <SearchBar
        :key="`${holding.id}:${reportedSymbol}`"
        :model-value="reportedSymbol"
        mode="picker"
        fluid
        :show-recent="false"
        :show-screener-link="false"
        :allow-expressions="false"
        :result-types="['Equity', 'Stock']"
        :allow-source-discovery="true"
        source-discovery-only
        readonly
        open-on-mount
        :required-resolved-symbol="reportedSymbol"
        @select="onCandidateResolved"
      />
      <button type="button" @click="active = false">Cancel</button>
      <p v-if="message" :role="isError ? 'alert' : 'status'">{{ message }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import SearchBar from '@/components/common/SearchBar.vue'
import {
  createETFHoldingDrilldownContext,
  isEligibleUnresolvedEquityHolding,
  type ETFHoldingDrilldownContext,
} from '@/lib/etfHoldingDrilldown'
import type { ETFHolding, ETFHoldingsSnapshot } from '@/types'

interface ResolvedSearchResult {
  instrument_id?: number | null
  explicitlyResolved?: boolean
  identity_status?: string
}

const props = defineProps<{
  holding: ETFHolding
  snapshot: ETFHoldingsSnapshot
  available: boolean
}>()
const emit = defineEmits<{
  resolved: [symbol: string, context: ETFHoldingDrilldownContext]
}>()

const active = ref(false)
const message = ref('')
const isError = ref(false)
const reportedSymbol = computed(() => String(props.holding.reported_symbol || '').trim())
const eligible = computed(() => isEligibleUnresolvedEquityHolding(props.holding))

function onCandidateResolved(symbol: string, result?: ResolvedSearchResult) {
  const canonical = symbol.trim()
  const expected = reportedSymbol.value
  const instrumentId = result?.instrument_id
  if (!result?.explicitlyResolved || !Number.isSafeInteger(instrumentId) || Number(instrumentId) <= 0
    || !['resolved', 'verified'].includes(String(result?.identity_status || '').trim().toLowerCase())
    || canonical.toUpperCase() !== expected.toUpperCase()) {
    isError.value = true
    message.value = 'The candidate did not resolve to an exact, provider-verified reported ticker. The holding was not opened.'
    return
  }
  message.value = ''
  emit('resolved', canonical, createETFHoldingDrilldownContext(
    props.snapshot,
    props.holding,
    Number(instrumentId),
    canonical,
  ))
}
</script>

<style scoped>
.holding-resolution-action,
.holding-resolution-picker {
  display: grid;
  gap: 8px;
}

.holding-resolution-picker p {
  margin: 0;
}
</style>
