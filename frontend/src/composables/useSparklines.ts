import { ref } from 'vue'
import { api } from '@/lib/api'

export type SparkTf = '1D' | '1W' | 'MTD' | '1M' | '3M' | '6M' | 'YTD' | '1Y'

export const sparkTfOptions: { label: string; value: SparkTf }[] = [
  { label: '1D',  value: '1D'  },
  { label: '1W',  value: '1W'  },
  { label: 'MTD', value: 'MTD' },
  { label: '1M',  value: '1M'  },
  { label: '3M',  value: '3M'  },
  { label: '6M',  value: '6M'  },
  { label: 'YTD', value: 'YTD' },
  { label: '1Y',  value: '1Y'  },
]

/** Shared across all component instances */
export const sparkTf = ref<SparkTf>('1M')

/** Cache keyed by `${symbol}:${tf}` */
const cache: Record<string, number[] | null> = {}
const inFlight: Record<string, Promise<number[] | null>> = {}

interface OhlcvBar { close: number }

function tfToParams(tf: SparkTf): { ohlcvTf: string; start: string } {
  const now = new Date()
  function daysAgo(n: number) {
    const d = new Date(now)
    d.setDate(d.getDate() - n)
    return d.toISOString()
  }
  switch (tf) {
    case '1D':  return { ohlcvTf: 'H1',  start: daysAgo(1) }
    case '1W':  return { ohlcvTf: 'H4',  start: daysAgo(7) }
    case 'MTD': return { ohlcvTf: 'D1',  start: new Date(now.getFullYear(), now.getMonth(), 1).toISOString() }
    case '1M':  return { ohlcvTf: 'D1',  start: daysAgo(30) }
    case '3M':  return { ohlcvTf: 'D1',  start: daysAgo(91) }
    case '6M':  return { ohlcvTf: 'D1',  start: daysAgo(182) }
    case 'YTD': return { ohlcvTf: 'D1',  start: new Date(now.getFullYear(), 0, 1).toISOString() }
    case '1Y':  return { ohlcvTf: 'D1',  start: daysAgo(365) }
  }
}

async function fetchSparkPoints(symbol: string, tf: SparkTf): Promise<number[] | null> {
  const key = `${symbol}:${tf}`
  if (key in cache) return cache[key]
  if (key in inFlight) return inFlight[key]

  const { ohlcvTf, start } = tfToParams(tf)

  const p = api.get<OhlcvBar[]>(`/ohlcv/${symbol}/${ohlcvTf}`, { start })
    .then(bars => {
      const pts = bars.length >= 2 ? bars.map(b => b.close) : null
      cache[key] = pts
      delete inFlight[key]
      return pts
    })
    .catch(() => {
      cache[key] = null
      delete inFlight[key]
      return null
    })

  inFlight[key] = p
  return p
}

export function useSparklines() {
  function load(symbol: string): Promise<number[] | null> {
    return fetchSparkPoints(symbol, sparkTf.value)
  }

  async function loadMany(symbols: string[]): Promise<void> {
    await Promise.allSettled(symbols.map(s => fetchSparkPoints(s, sparkTf.value)))
  }

  function invalidateAll() {
    for (const key of Object.keys(cache)) delete cache[key]
  }

  function pointsToSvg(pts: number[]): string {
    const min = Math.min(...pts)
    const max = Math.max(...pts)
    const range = max - min || 1
    const W = 78, H = 28
    return pts
      .map((v, i) => {
        const x = 1 + (i / (pts.length - 1)) * W
        const y = 1 + (1 - (v - min) / range) * H
        return `${x.toFixed(1)},${y.toFixed(1)}`
      })
      .join(' ')
  }

  return { load, loadMany, invalidateAll, pointsToSvg }
}
