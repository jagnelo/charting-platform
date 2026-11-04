<template>
  <div v-if="available && eligible" class="holding-resolution-action">
    <button v-if="!active" type="button" @click="active = true">
      Resolve reported holding {{ reportedSymbol }}
    </button>
    <div v-else class="holding-resolution-picker">
      <p>Confirm the reported ticker {{ reportedSymbol }} against an exact listing before opening its chart. The saved fund snapshot will not be changed.</p>
      <SearchBar
        :key="`${holding.id}:${reportedSymbol}`"
        :model-value="reportedSymbol"
        mode="picker"
        fluid
        :show-recent="false"
        :show-screener-link="false"
        :allow-expressions="false"
        :result-types="['Equity', 'Stock', 'CS']"
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
  isConfirmedETFHoldingIdentity,
  isEligibleUnresolvedEquityHolding,
  type ETFHoldingDrilldownContext,
} from '@/lib/etfHoldingDrilldown'
import type { InstrumentAcquireResponse } from '@/lib/onDemandAcquisition'
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
  startImmediately?: boolean
}>()
const emit = defineEmits<{
  resolved: [symbol: string, context: ETFHoldingDrilldownContext, confirmedIdentity: InstrumentAcquireResponse]
}>()

const active = ref(Boolean(props.startImmediately))
const message = ref('')
const isError = ref(false)
const reportedSymbol = computed(() => String(props.holding.reported_symbol || '').trim())
const eligible = computed(() => isEligibleUnresolvedEquityHolding(props.holding))

function onCandidateResolved(
  symbol: string,
  result?: ResolvedSearchResult,
  confirmedIdentity?: InstrumentAcquireResponse,
) {
  const canonical = symbol.trim()
  const expected = reportedSymbol.value
  const instrumentId = result?.instrument_id
  if (!result?.explicitlyResolved || !Number.isSafeInteger(instrumentId) || Number(instrumentId) <= 0
    || !['resolved', 'verified'].includes(String(result?.identity_status || '').trim().toLowerCase())
    || canonical.toUpperCase() !== expected.toUpperCase()
    || !confirmedIdentity?.instrument
    || confirmedIdentity.instrument.instrument_id !== instrumentId
    || confirmedIdentity.instrument.symbol.trim().toUpperCase() !== canonical.toUpperCase()) {
    isError.value = true
    message.value = 'The candidate did not resolve to an exact, provider-verified reported ticker. The holding was not opened.'
    return
  }
  message.value = ''
  const context = createETFHoldingDrilldownContext(
    props.snapshot,
    props.holding,
    Number(instrumentId),
    canonical,
  )
  if (!isConfirmedETFHoldingIdentity(confirmedIdentity, context)) {
    isError.value = true
    message.value = 'The confirmed identity no longer matches this reported holding. The chart was not opened.'
    return
  }
  emit('resolved', canonical, context, confirmedIdentity)
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
