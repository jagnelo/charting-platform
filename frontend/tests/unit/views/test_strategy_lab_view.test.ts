import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import StrategyLabView from '@/views/StrategyLabView.vue'

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}))

import { api } from '@/lib/api'

async function flushPromises() {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
}

const definition = {
  id: 4,
  user_id: 1,
  name: 'Momentum Pilot',
  description: 'Research baseline',
  source_type: 'custom',
  definition_type: 'rules',
  is_active: true,
  tags: ['momentum'],
  metadata: { owner: 'desk' },
  versions: [
    {
      id: 8,
      strategy_id: 4,
      version_number: 2,
      engine_type: 'platform',
      definition_snapshot: { timeframe: 'D1', logic: 'close > ema50' },
      parameter_schema: {},
      default_parameters: { ema_period: 50 },
      universe_config: { symbols: ['AAPL'] },
      benchmark_config: { symbol: 'SPY' },
      execution_model: { entry: 'next_bar_open' },
      notes: 'v2',
      is_current: true,
      created_at: '2026-05-10T10:00:00Z',
      updated_at: '2026-05-10T10:00:00Z',
    },
  ],
  runs: [
    {
      id: 12,
      strategy_id: 4,
      strategy_version_id: 8,
      requested_by_user_id: 1,
      engine_type: 'platform',
      test_mode: 'backtest',
      status: 'completed',
      timeframe: 'D1',
      started_at: '2026-05-10T10:01:00Z',
      completed_at: '2026-05-10T10:01:01Z',
      date_from: '2026-01-01T00:00:00Z',
      date_to: '2026-05-01T00:00:00Z',
      parameter_values: { ema_period: 50 },
      universe_config: { symbols: ['AAPL'] },
      benchmark_config: {},
      execution_assumptions: { slippage_bps: 5 },
      engine_run_ref: 'platform:12',
      result_summary: {
        result_kind: 'foundation_research_snapshot',
        coverage: { total_bars: 120, instruments_with_data: 1 },
        universe: { resolved_instrument_count: 1, resolved_symbols: ['AAPL'] },
        readiness: { has_coverage: true },
      },
      artifact_manifest: {},
      warning_log: [],
      error_log: null,
      created_at: '2026-05-10T10:01:00Z',
      updated_at: '2026-05-10T10:01:01Z',
    },
  ],
  created_at: '2026-05-10T10:00:00Z',
  updated_at: '2026-05-10T10:01:01Z',
}

describe('StrategyLabView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementation((path: string) => {
      if (path === '/strategy-lab/definitions') return Promise.resolve([definition])
      if (path === '/strategy-lab/engines') {
        return Promise.resolve([
          {
            key: 'platform',
            label: 'Platform Engine',
            is_available: true,
            supports_walk_forward: true,
            supports_paper_forward: true,
            notes: 'ready',
          },
          {
            key: 'nautilus',
            label: 'Nautilus Trader',
            is_available: false,
            supports_walk_forward: true,
            supports_paper_forward: true,
            notes: 'planned',
          },
        ])
      }
      if (path === '/strategy-lab/definitions/4') return Promise.resolve(definition)
      return Promise.resolve([])
    })
    ;(api.post as ReturnType<typeof vi.fn>).mockImplementation((path: string) => {
      if (path === '/strategy-lab/definitions') return Promise.resolve(definition)
      if (path === '/strategy-lab/definitions/4/versions') {
        return Promise.resolve({
          ...definition.versions[0],
          id: 9,
          version_number: 3,
        })
      }
      if (path === '/strategy-lab/versions/8/runs') {
        return Promise.resolve({
          run: {
            ...definition.runs[0],
            id: 15,
          },
          engine: {
            key: 'platform',
            label: 'Platform Engine',
            is_available: true,
            supports_walk_forward: true,
            supports_paper_forward: true,
            notes: 'ready',
          },
        })
      }
      return Promise.resolve({})
    })
    ;(api.patch as ReturnType<typeof vi.fn>).mockResolvedValue(definition)
  })

  it('loads the current definition and renders run detail', async () => {
    const wrapper = mount(StrategyLabView)

    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('Momentum Pilot')
    })

    expect(wrapper.text()).toContain('Strategy Lab')
    expect(wrapper.text()).toContain('Momentum Pilot')
    expect(wrapper.text()).toContain('Platform Engine')
    expect(wrapper.text()).toContain('120 bars')
    expect(wrapper.text()).toContain('Use structured rule objects')
    expect(wrapper.find('option[value="nautilus"]').exists()).toBe(false)
  })

  it('creates a new definition and can run the current version', async () => {
    const wrapper = mount(StrategyLabView)

    await flushPromises()

    await wrapper.get('.sidebar-header .btn-primary').trigger('click')
    await wrapper.get('input[placeholder="Momentum Pilot"]').setValue('Breakout Stack')
    await wrapper.get('textarea.form-textarea--short').setValue('New definition')
    await wrapper.get('.detail-header .btn-primary').trigger('click')

    await flushPromises()

    expect(api.post).toHaveBeenCalledWith('/strategy-lab/definitions', expect.objectContaining({
      name: 'Breakout Stack',
      initial_version: expect.any(Object),
    }))

    await wrapper.get('.panel .btn-primary').trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith('/strategy-lab/versions/8/runs', expect.objectContaining({
      test_mode: 'backtest',
    }))
  })
})
