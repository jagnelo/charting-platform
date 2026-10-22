import { describe, expect, it, vi } from 'vitest'
import {
  createRendererLifecycleState,
  initializeRenderer,
  rendererConfigurationSignature,
} from '@/lib/uplot/rendererLifecycle'

const configuration = () => ({
  barType: 'candles',
  chartType: 'candles',
  indicators: [],
  localOnly: true,
  logScale: false,
  series: [{ label: 'Close', scale: 'y', stroke: '#64b5f6', width: 1.6 }],
  timeframe: 'D1',
  transform: {},
  volumeProfile: false,
})

describe('uPlot renderer initialization lifecycle', () => {
  it('preserves renderer identity and destroy count for equivalent repeat initialization', async () => {
    const signature = rendererConfigurationSignature(configuration())
    const equivalent = rendererConfigurationSignature({
      volumeProfile: false,
      transform: {},
      timeframe: 'D1',
      series: [{ width: 1.6, stroke: '#64b5f6', scale: 'y', label: 'Close' }],
      logScale: false,
      localOnly: true,
      indicators: [],
      chartType: 'candles',
      barType: 'candles',
    })

    expect(equivalent).toBe(signature)
    const state = createRendererLifecycleState()
    const firstRenderer = { destroy: vi.fn() }
    let renderer: { destroy: ReturnType<typeof vi.fn> } | null = null
    let rebuilds = 0
    let updates = 0
    const rebuild = async () => {
      renderer?.destroy()
      rebuilds += 1
      renderer = rebuilds === 1 ? firstRenderer : { destroy: vi.fn() }
      return true
    }
    const update = () => { updates += 1 }

    await initializeRenderer(state, signature, false, rebuild, update)
    const originalRenderer = renderer
    await initializeRenderer(state, equivalent, true, rebuild, update)

    expect(renderer).toBe(originalRenderer)
    expect(firstRenderer.destroy).not.toHaveBeenCalled()
    expect(rebuilds).toBe(1)
    expect(updates).toBe(1)
  })

  it('does not destroy and restart an identical renderer initialization already in flight', () => {
    const state = createRendererLifecycleState()
    const signature = rendererConfigurationSignature(configuration())
    let resolveBuild: ((rendered: boolean) => void) | undefined
    const rebuild = () => new Promise<boolean>(resolve => { resolveBuild = resolve })
    let rebuilds = 0
    const startRebuild = () => { rebuilds += 1; return rebuild() }

    const first = initializeRenderer(state, signature, false, startRebuild, () => {})
    const second = initializeRenderer(state, signature, true, startRebuild, () => {})
    expect(rebuilds).toBe(1)
    resolveBuild?.(true)

    return Promise.all([first, second]).then(([firstAction, secondAction]) => {
      expect(firstAction).toBe('rebuild')
      expect(secondAction).toBe('skip-pending')
      expect(state.renderedSignature).toBe(signature)
      expect(rebuilds).toBe(1)
    })
  })

  it('rebuilds when a render-affecting chart setting or series changes', () => {
    const baseline = rendererConfigurationSignature(configuration())
    const firstIndicator = { type: 'rsi', params: { length: 14 }, style: { color: '#7e57c2', lineWidth: 1 }, pane: 'separate' }
    const secondIndicator = { type: 'ema', params: { length: 20 }, style: { color: '#26a69a', lineWidth: 2 }, pane: 'main' }
    const changes = [
      { ...configuration(), chartType: 'line' },
      { ...configuration(), barType: 'heikin_ashi' },
      { ...configuration(), logScale: true },
      { ...configuration(), volumeProfile: true },
      { ...configuration(), transform: { brick_size: 2 } },
      { ...configuration(), indicators: [{ ...firstIndicator, params: { length: 21 } }] },
      { ...configuration(), indicators: [{ ...firstIndicator, style: { ...firstIndicator.style, color: '#42a5f5' } }] },
      { ...configuration(), indicators: [firstIndicator, secondIndicator] },
      { ...configuration(), indicators: [secondIndicator, firstIndicator] },
      { ...configuration(), series: [...configuration().series, { label: 'SPY', scale: 'y' }] },
      { ...configuration(), series: [{ ...configuration().series[0], stroke: '#42a5f5' }] },
    ]

    for (const changed of changes) {
      expect(rendererConfigurationSignature(changed)).not.toBe(baseline)
    }
  })

  it('starts the latest configuration when a different signature supersedes pending work', async () => {
    const state = createRendererLifecycleState()
    const initial = rendererConfigurationSignature(configuration())
    const next = rendererConfigurationSignature({ ...configuration(), logScale: true })
    const resolutions = new Map<string, (rendered: boolean) => void>()
    const rebuild = (signature: string) => () => new Promise<boolean>(resolve => {
      resolutions.set(signature, resolve)
    })

    const first = initializeRenderer(state, initial, false, rebuild(initial), () => {})
    const second = initializeRenderer(state, next, false, rebuild(next), () => {})
    resolutions.get(initial)?.(false)
    await first
    expect(state.renderedSignature).toBeNull()
    resolutions.get(next)?.(true)
    expect(await second).toBe('rebuild')
    expect(state.renderedSignature).toBe(next)
  })

  it('rebuilds when the renderer has been destroyed even if its prior signature matches', async () => {
    const state = createRendererLifecycleState()
    const signature = rendererConfigurationSignature(configuration())
    state.renderedSignature = signature
    let rebuilds = 0

    await initializeRenderer(state, signature, false, async () => { rebuilds += 1; return true }, () => {})
    expect(rebuilds).toBe(1)
    expect(state.renderedSignature).toBe(signature)
  })
})
