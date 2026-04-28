import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '@/lib/api'
import type {
  ExpirationSummary,
  OptionsExposureResponse,
} from '@/types'

export const useOptionsExposureStore = defineStore('optionsExposure', () => {
  const symbol = ref<string | null>(null)
  const data = ref<OptionsExposureResponse | null>(null)
  const expirationSummaries = ref<ExpirationSummary[]>([])
  const selectedExpiration = ref<string | null>(null)
  const enabledExpirations = ref<Set<string>>(new Set())
  const strikeRange = ref<{ min: number | null; max: number | null }>({ min: null, max: null })
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  let _loadSeq = 0

  const availableExpirations = computed(() => data.value?.expirations ?? [])

  const visibleLadder = computed(() => {
    if (!data.value) return []
    const { min, max } = strikeRange.value
    return data.value.ladder.filter(row => {
      if (min != null && row.strike < min) return false
      if (max != null && row.strike > max) return false
      return true
    })
  })

  const filteredLadder = computed(() => {
    const enabled = enabledExpirations.value
    if (!enabled.size) return visibleLadder.value
    return visibleLadder.value.map(row => {
      let call_gex = 0, put_gex = 0, call_dex = 0, put_dex = 0
      let call_oi = 0, put_oi = 0
      for (const [exp, bd] of Object.entries(row.by_expiry)) {
        if (!enabled.has(exp)) continue
        call_gex += bd.call_gex; put_gex += bd.put_gex
        call_dex += bd.call_dex; put_dex += bd.put_dex
        call_oi += bd.call_oi; put_oi += bd.put_oi
      }
      return {
        ...row,
        call_gex, put_gex, net_gex: call_gex + put_gex,
        call_dex, put_dex, net_dex: call_dex + put_dex,
        call_oi, put_oi,
      }
    })
  })

  async function load(sym: string, expiration?: string | null) {
    const seq = ++_loadSeq
    const previousSymbol = symbol.value
    symbol.value = sym
    isLoading.value = true
    error.value = null
    try {
      const params: Record<string, string> = {}
      if (expiration) params.expiration = expiration

      const [exposure, summaries] = await Promise.all([
        api.get<OptionsExposureResponse>(
          `/instruments/${encodeURIComponent(sym)}/options/exposure`,
          params,
        ),
        api.get<ExpirationSummary[]>(
          `/instruments/${encodeURIComponent(sym)}/options/exposure/expirations`,
        ),
      ])

      if (seq !== _loadSeq) return

      data.value = exposure
      expirationSummaries.value = summaries

      // Initialize enabled expirations to all available on first load
      if (enabledExpirations.value.size === 0 || previousSymbol !== sym) {
        enabledExpirations.value = new Set(exposure.expirations)
      }
    } catch (e) {
      if (seq !== _loadSeq) return
      error.value = e instanceof Error ? e.message : 'Failed to load exposure data'
      console.error('[optionsExposure]', e)
    } finally {
      if (seq === _loadSeq) isLoading.value = false
    }
  }

  function toggleExpiration(exp: string) {
    const s = new Set(enabledExpirations.value)
    if (s.has(exp)) {
      s.delete(exp)
    } else {
      s.add(exp)
    }
    enabledExpirations.value = s
  }

  function setAllExpirations(enabled: boolean) {
    if (enabled) {
      enabledExpirations.value = new Set(availableExpirations.value)
    } else {
      enabledExpirations.value = new Set()
    }
  }

  function setStrikeRange(min: number | null, max: number | null) {
    strikeRange.value = { min, max }
  }

  function reset() {
    ++_loadSeq
    symbol.value = null
    data.value = null
    expirationSummaries.value = []
    selectedExpiration.value = null
    enabledExpirations.value = new Set()
    strikeRange.value = { min: null, max: null }
    isLoading.value = false
    error.value = null
  }

  return {
    symbol, data, expirationSummaries,
    selectedExpiration, enabledExpirations,
    strikeRange, isLoading, error,
    availableExpirations, visibleLadder, filteredLadder,
    load, toggleExpiration, setAllExpirations, setStrikeRange, reset,
  }
})
