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
  metadata: {},
  versions: [
    {
      id: 8,
      strategy_id: 4,
      version_number: 2,
      definition_snapshot: {
        timeframe: 'D1',
        direction: 'long',
        entry_logic: 'all',
        conditions: [
          {
            left_source: 'indicator',
            left_indicator: 'ema',
            left_period: 21,
            operator: 'gt',
            right_source: 'indicator',
            right_indicator: 'sma',
            right_period: 50,
          },
        ],
        risk: {
          stop_loss_pct: 2,
          take_profit_rr: 2.5,
          max_bars_in_trade: 18,
        },
      },
      parameter_schema: {},
      default_parameters: {},
      universe_config: { symbols: ['AAPL', 'MSFT'] },
      benchmark_config: { symbol: 'SPY' },
      execution_model: { entry: 'next_bar_open' },
      notes: 'Trend-following update',
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
      test_mode: 'backtest',
      status: 'completed',
      timeframe: 'D1',
      started_at: '2026-05-10T10:01:00Z',
      completed_at: '2026-05-10T10:01:01Z',
      date_from: '2026-01-01T00:00:00Z',
      date_to: '2026-05-01T00:00:00Z',
      parameter_values: {},
      universe_config: { symbols: ['AAPL'] },
      benchmark_config: {},
      execution_assumptions: { slippage_bps: 5 },
      engine_run_ref: 'platform:12',
      result_summary: {
        result_kind: 'rules_backtest',
        coverage: { total_bars: 120, instruments_with_data: 1 },
        performance: {
          trade_count: 6,
          net_return_pct: 12.5,
          win_rate: 66.67,
          expectancy_r: 0.72,
          max_drawdown_pct: 3.4,
          profit_factor: 1.8,
        },
        equity_curve: [
          { ts: '2026-01-01T00:00:00Z', equity: 100000 },
          { ts: '2026-02-01T00:00:00Z', equity: 102500 },
          { ts: '2026-03-01T00:00:00Z', equity: 112500 },
        ],
        analytics: {
          drawdown_curve: [
            { ts: '2026-01-01T00:00:00Z', drawdown_pct: 0 },
            { ts: '2026-02-01T00:00:00Z', drawdown_pct: 1.5 },
          ],
          monthly_returns: [
            { period: '2026-01', return_pct: 2.5 },
            { period: '2026-02', return_pct: 4.1 },
          ],
        },
        benchmark: {
          symbol: 'SPY',
          equity_curve: [
            { ts: '2026-01-01T00:00:00Z', equity: 100000 },
            { ts: '2026-02-01T00:00:00Z', equity: 101200 },
          ],
        },
        benchmark_comparison: {
          excess_return_pct: 3.2,
        },
        symbol_performance: [
          { symbol: 'AAPL', net_pnl: 1250.45, trade_count: 2, win_rate: 50, avg_r: 1.1 },
        ],
        optimization: {
          leaderboard: [
            { stop_loss_pct: 2, take_profit_rr: 2.5, max_bars_in_trade: 18, net_pnl: 1250.45, avg_r: 1.1 },
          ],
        },
        trades: [
          {
            instrument_symbol: 'AAPL',
            side: 'long',
            entry_at: '2026-02-02T00:00:00Z',
            exit_at: '2026-02-08T00:00:00Z',
            pnl: 1250.45,
            r_multiple: 1.84,
            exit_reason: 'take_profit',
          },
        ],
      },
      artifact_manifest: { result_kind: 'rules_backtest', supports_execution_stats: true },
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
      if (path === '/strategy-lab/definitions/4') return Promise.resolve(definition)
      if (path === '/watchlists') {
        return Promise.resolve([
          {
            id: 3,
            name: 'Growth',
            is_default: false,
            is_managed: false,
            is_locked: false,
            position: 0,
            items: [{ id: 1, instrument_id: 1, symbol: 'AAPL', position: 0 }],
          },
        ])
      }
      if (path === '/screeners') {
        return Promise.resolve([
          { id: 7, name: 'Momentum Universe' },
        ])
      }
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
          ...definition.runs[0],
          id: 15,
        })
      }
      return Promise.resolve({})
    })
    ;(api.patch as ReturnType<typeof vi.fn>).mockResolvedValue(definition)
  })

  it('loads the visual builder and hides engine branding', async () => {
    const wrapper = mount(StrategyLabView)

    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('Momentum Pilot')
    })

    expect(wrapper.text()).toContain('Strategy Lab')
    expect(wrapper.text()).toContain('Entry logic')
    expect(wrapper.text()).toContain('Backtest')
    expect(wrapper.text()).toContain('12.50%')
    expect(wrapper.text()).toContain('AAPL')
    expect(wrapper.text()).not.toContain('Nautilus')
    expect(api.get).not.toHaveBeenCalledWith('/strategy-lab/engines')
    expect(wrapper.text()).toContain('Benchmark')
    expect(wrapper.text()).toContain('Monthly returns')
  })

  it('creates a strategy from the visual builder without JSON payload editing', async () => {
    const wrapper = mount(StrategyLabView)

    await flushPromises()

    await wrapper.get('.sidebar-header .btn-primary').trigger('click')
    await wrapper.get('input[placeholder="Momentum Continuation"]').setValue('Breakout Stack')
    await wrapper.get('textarea.form-textarea--short').setValue('Trend strategy')
    await wrapper.get('input[placeholder="Add symbol (e.g. AAPL)"]').setValue('NVDA, AMD')
    await wrapper.get('.subsection .btn-secondary').trigger('click')
    await wrapper.get('.detail-header .btn-primary').trigger('click')

    await flushPromises()

    expect(api.post).toHaveBeenCalledWith('/strategy-lab/definitions', expect.objectContaining({
      name: 'Breakout Stack',
      definition_type: 'rules',
      source_type: 'custom',
      initial_version: expect.objectContaining({
        definition_snapshot: expect.objectContaining({
          conditions: expect.any(Array),
          condition_tree: expect.objectContaining({
            type: 'all',
            conditions: expect.any(Array),
          }),
          timeframe: 'D1',
        }),
        universe_config: { symbols: ['NVDA', 'AMD'] },
      }),
    }))
  })

  it('publishes revisions and runs backtests from the current visual state', async () => {
    const wrapper = mount(StrategyLabView)

    await flushPromises()

    const noteInput = wrapper.get('input[placeholder="What changed in this revision?"]')
    await noteInput.setValue('Tighter trend logic')
    await flushPromises()
    await wrapper.get('.detail-header .btn-primary').trigger('click')

    await flushPromises()

    expect(api.patch).toHaveBeenCalledWith('/strategy-lab/definitions/4', expect.objectContaining({
      name: 'Momentum Pilot',
      definition_type: 'rules',
    }))
    expect(api.post).toHaveBeenCalledWith('/strategy-lab/definitions/4/versions', expect.objectContaining({
      definition_snapshot: expect.objectContaining({
        conditions: expect.any(Array),
        condition_tree: expect.objectContaining({
          type: 'all',
        }),
      }),
    }))

    const runButton = wrapper.findAll('button').find(button => button.text() === 'Run backtest')
    expect(runButton).toBeTruthy()
    await runButton!.trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith('/strategy-lab/versions/8/runs', expect.objectContaining({
      test_mode: 'backtest',
      execution_assumptions: expect.objectContaining({
        initial_capital: 100000,
        risk_per_trade_pct: 1,
      }),
    }))
  })

  it('supports walk-forward mode, watchlist universes, and optimization inputs', async () => {
    const wrapper = mount(StrategyLabView)

    await flushPromises()

    await wrapper.get('select').setValue('custom')
    const selects = wrapper.findAll('select')
    await selects[1].setValue('watchlist')
    await flushPromises()
    const watchlistSelect = wrapper.findAll('select').find(node => node.element instanceof HTMLSelectElement && Array.from((node.element as HTMLSelectElement).options).some(option => option.text === 'Growth'))
    expect(watchlistSelect).toBeTruthy()
    await watchlistSelect!.setValue('3')
    await wrapper.findAll('.mode-pill')[1].trigger('click')
    const optimizationCheckbox = wrapper.findAll('input[type="checkbox"]').find(node =>
      node.element instanceof HTMLInputElement
      && node.element.type === 'checkbox'
      && node.element.closest('.subsection')?.textContent?.includes('Parameter sweep')
    )
    expect(optimizationCheckbox).toBeTruthy()
    await optimizationCheckbox!.setValue(true)
    await flushPromises()
    await wrapper.get('input[placeholder="1.5, 2, 2.5, 3"]').setValue('1.5, 2')

    const runButton = wrapper.findAll('button').find(button => button.text() === 'Run walk-forward')
    expect(runButton).toBeTruthy()
    await runButton!.trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith('/strategy-lab/versions/8/runs', expect.objectContaining({
      test_mode: 'walk_forward',
      execution_assumptions: expect.objectContaining({
        optimization: expect.objectContaining({
          enabled: true,
        }),
      }),
    }))
  })

  it('publishes radar replay strategies with screener universes from the visual builder', async () => {
    const wrapper = mount(StrategyLabView)

    await flushPromises()

    await wrapper.get('.sidebar-header .btn-primary').trigger('click')
    await wrapper.get('input[placeholder="Momentum Continuation"]').setValue('Radar Breakout Replay')
    const selects = wrapper.findAll('select')
    await selects[0].setValue('radar')
    await flushPromises()
    await wrapper.findAll('select')[1].setValue('screener')
    await flushPromises()
    const screenerSelect = wrapper.findAll('select').find(node =>
      Array.from((node.element as HTMLSelectElement).options).some(option => option.text === 'Momentum Universe'),
    )
    expect(screenerSelect).toBeTruthy()
    await screenerSelect!.setValue('7')
    const breakoutCheckbox = wrapper.findAll('input[type="checkbox"]').find(node =>
      node.element.closest('.check-pill')?.textContent?.includes('Breakout'),
    )
    expect(breakoutCheckbox).toBeTruthy()
    await breakoutCheckbox!.setValue(true)
    await wrapper.get('.detail-header .btn-primary').trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith('/strategy-lab/definitions', expect.objectContaining({
      source_type: 'radar',
      definition_type: 'signal_source',
      initial_version: expect.objectContaining({
        universe_config: { screener_id: 7 },
        definition_snapshot: expect.objectContaining({
          radar_filters: expect.objectContaining({
            setup_types: ['breakout'],
          }),
        }),
      }),
    }))
  })
})
