import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { OHLCVBar, Timeframe, Instrument, IndicatorConfig } from '@/types'
import { api } from '@/lib/api'

export const useChartStore = defineStore('chart', () => {
  const symbol = ref<string>('')
  const timeframe = ref<Timeframe>('D1')
  const bars = ref<OHLCVBar[]>([])
  const instrument = ref<Instrument | null>(null)
  const indicators = ref<IndicatorConfig[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const uplotData = computed(() => {
    if (!bars.value.length) return [[], [], [], [], [], []]
    const timestamps = bars.value.map(b => new Date(b.ts).getTime() / 1000)
    const opens   = bars.value.map(b => b.open)
    const highs   = bars.value.map(b => b.high)
    const lows    = bars.value.map(b => b.low)
    const closes  = bars.value.map(b => b.close)
    const volumes = bars.value.map(b => b.volume ?? 0)
    return [timestamps, opens, highs, lows, closes, volumes]
  })

  async function loadInstrument(sym: string) {
    try {
      instrument.value = await api.get(`/instruments/${sym}`)
    } catch {
      // Auto-creates from yfinance on first visit
    }
  }

  async function loadBars(sym: string, tf: Timeframe) {
    isLoading.value = true
    error.value = null
    symbol.value = sym
    timeframe.value = tf

    await loadInstrument(sym)

    try {
      const raw = await api.get<any[]>(`/ohlcv/${sym}/${tf}`)
      bars.value = raw.map(b => ({
        ...b,
        open:   Number(b.open),
        high:   Number(b.high),
        low:    Number(b.low),
        close:  Number(b.close),
        volume: b.volume != null ? Number(b.volume) : undefined,
        vwap:   b.vwap   != null ? Number(b.vwap)   : undefined,
      }))
    } catch (e: any) {
      error.value = e.message ?? 'Failed to load chart data'
    } finally {
      isLoading.value = false
    }
  }

  function setIndicators(configs: IndicatorConfig[]) {
    indicators.value = configs
  }

  function addIndicator(config: IndicatorConfig) {
    indicators.value.push(config)
  }

  function removeIndicator(index: number) {
    indicators.value.splice(index, 1)
  }

  function updateIndicator(index: number, config: IndicatorConfig) {
    indicators.value[index] = config
  }

  return {
    symbol, timeframe, bars, instrument, indicators,
    isLoading, error, uplotData,
    loadBars, loadInstrument,
    setIndicators, addIndicator, removeIndicator, updateIndicator,
  }
})
