import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SearchBar from '@/components/common/SearchBar.vue'
import StrategyLabView from '@/views/StrategyLabView.vue'

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

import { api } from '@/lib/api'

async function flushPromises() {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
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
        coverage: {
          preview_mode: 'resolved',
          preview_note: null,
          instrument_count: 1,
          instruments_with_data: 1,
          instruments_with_requested_data: 1,
          instruments_with_full_requested_coverage: 1,
          instruments_with_partial_requested_coverage: 0,
          instruments_without_requested_coverage: 0,
          total_bars: 120,
          requested_date_from: '2026-01-01T00:00:00Z',
          requested_date_to: '2026-05-01T00:00:00Z',
          requested_first_bar_at: '2026-01-01T00:00:00Z',
          requested_last_bar_at: '2026-05-01T00:00:00Z',
          any_coverage_from: '2025-10-01T00:00:00Z',
          any_coverage_to: '2026-05-01T00:00:00Z',
          collective_coverage_from: '2025-10-01T00:00:00Z',
          collective_coverage_to: '2026-05-01T00:00:00Z',
          requested_fits_collective_range: true,
          resolved_symbols: ['AAPL'],
          limiting_instruments: [],
          instruments: [
            {
              instrument_id: 1,
              symbol: 'AAPL',
              available_from: '2025-10-01T00:00:00Z',
              available_to: '2026-05-01T00:00:00Z',
              requested_first_bar_at: '2026-01-01T00:00:00Z',
              requested_last_bar_at: '2026-05-01T00:00:00Z',
              total_bars: 220,
              requested_bars: 120,
              requested_status: 'full',
              note: null,
              ipo_date: '1980-12-12',
            },
          ],
        },
        performance: {
          initial_capital: 100000,
          ending_capital: 112500,
          trade_count: 6,
          closed_trade_count: 6,
          open_position_count: 1,
          realized_ending_capital: 112187.55,
          realized_net_return_pct: 12.1876,
          unrealized_pnl: 312.45,
          unrealized_return_pct: 0.3125,
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
          coverage: {
            symbol: 'SPY',
            preview_note: null,
            requested_status: 'full',
            available_from: '2024-01-01T00:00:00Z',
            available_to: '2026-05-01T00:00:00Z',
            requested_first_bar_at: '2026-01-01T00:00:00Z',
            requested_last_bar_at: '2026-05-01T00:00:00Z',
            total_bars: 540,
            requested_bars: 120,
            requested_fits_range: true,
          },
        },
        benchmark_comparison: {
          excess_return_pct: 3.2,
        },
        position_timelines: [
          {
            position_id: 'AAPL-1-2026-02-02T00:00:00Z',
            label: 'AAPL #1',
            symbol: 'AAPL',
            side: 'long',
            entry_at: '2026-02-02T00:00:00Z',
            exit_at: '2026-02-08T00:00:00Z',
            pnl: 1250.45,
            r_multiple: 1.84,
            exit_reason: 'take_profit',
            points: [
              { ts: '2026-02-02T00:00:00Z', value: 0, detail: 'Entry · AAPL LONG · 10.00 @ 100.00', marker: 'entry' },
              { ts: '2026-02-05T00:00:00Z', value: 650.12 },
              { ts: '2026-02-08T00:00:00Z', value: 1250.45, detail: 'Exit · take profit · 112.50 · 1.84R', marker: 'exit' },
            ],
          },
        ],
        symbol_performance: [
          {
            symbol: 'AAPL',
            net_pnl: 1562.9,
            total_pnl: 1562.9,
            realized_pnl: 1250.45,
            unrealized_pnl: 312.45,
            trade_count: 2,
            closed_trade_count: 2,
            open_position_count: 1,
            win_rate: 50,
            avg_r: 1.1,
          },
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
        execution_log: [
          {
            ts: '2026-02-02T00:00:00Z',
            event_type: 'entry',
            position_id: 'AAPL-2026-02-02T00:00:00Z',
            symbol: 'AAPL',
            side: 'long',
            quantity: 10,
            price: 100,
            notional: 1000,
            pnl: null,
            pnl_pct: null,
            r_multiple: null,
            reason: 'entry_signal',
          },
          {
            ts: '2026-02-08T00:00:00Z',
            event_type: 'exit',
            position_id: 'AAPL-2026-02-02T00:00:00Z',
            symbol: 'AAPL',
            side: 'long',
            quantity: 10,
            price: 112.5,
            notional: 1000,
            pnl: 1250.45,
            pnl_pct: 12.5,
            r_multiple: 1.84,
            reason: 'take_profit',
          },
          {
            ts: '2026-03-01T00:00:00Z',
            event_type: 'rejected',
            position_id: 'MSFT-2026-03-01T00:00:00Z',
            symbol: 'MSFT',
            side: 'long',
            quantity: 1,
            price: 300,
            notional: 300,
            pnl: null,
            pnl_pct: null,
            r_multiple: null,
            reason: 'max_concurrent_positions',
          },
        ],
        open_positions: [
          {
            instrument_id: 1,
            instrument_symbol: 'AAPL',
            side: 'long',
            entry_at: '2026-03-10T00:00:00Z',
            current_at: '2026-05-01T00:00:00Z',
            entry_price: 108,
            current_price: 111.1245,
            stop_price: 105.84,
            target_price: 113.4,
            quantity: 1,
            unrealized_pnl: 312.45,
            unrealized_pnl_pct: 2.893,
            r_multiple: 0.72,
            bars_held: 35,
            status: 'open_at_end',
          },
        ],
      },
      artifact_manifest: { result_kind: 'rules_backtest', supports_execution_stats: true },
      warning_log: ['4 trades were rejected by portfolio controls.'],
      error_log: null,
      created_at: '2026-05-10T10:01:00Z',
      updated_at: '2026-05-10T10:01:01Z',
    },
  ],
  created_at: '2026-05-10T10:00:00Z',
  updated_at: '2026-05-10T10:01:01Z',
}

const coveragePreviewResponse = {
  timeframe: 'D1',
  requested_date_from: '2026-01-01T00:00:00Z',
  requested_date_to: '2026-05-01T00:00:00Z',
  universe: {
    preview_mode: 'resolved',
    preview_note: null,
    instrument_count: 2,
    instruments_with_data: 2,
    instruments_with_requested_data: 2,
    instruments_with_full_requested_coverage: 1,
    instruments_with_partial_requested_coverage: 1,
    instruments_without_requested_coverage: 0,
    total_bars: 220,
    requested_first_bar_at: '2026-01-01T00:00:00Z',
    requested_last_bar_at: '2026-05-01T00:00:00Z',
    any_coverage_from: '2025-08-01T00:00:00Z',
    any_coverage_to: '2026-05-01T00:00:00Z',
    collective_coverage_from: '2026-02-15T00:00:00Z',
    collective_coverage_to: '2026-05-01T00:00:00Z',
    requested_fits_collective_range: false,
    resolved_symbols: ['AAPL', 'MSFT'],
    limiting_instruments: [
      {
        instrument_id: 2,
        symbol: 'MSFT',
        available_from: '2026-02-15T00:00:00Z',
        available_to: '2026-05-01T00:00:00Z',
        requested_first_bar_at: '2026-02-15T00:00:00Z',
        requested_last_bar_at: '2026-05-01T00:00:00Z',
        total_bars: 55,
        requested_bars: 55,
        requested_status: 'partial',
        note: 'Coverage begins after the requested start; earlier local history may be missing.',
        ipo_date: null,
      },
    ],
    instruments: [
      {
        instrument_id: 1,
        symbol: 'AAPL',
        available_from: '2025-10-01T00:00:00Z',
        available_to: '2026-05-01T00:00:00Z',
        requested_first_bar_at: '2026-01-01T00:00:00Z',
        requested_last_bar_at: '2026-05-01T00:00:00Z',
        total_bars: 165,
        requested_bars: 120,
        requested_status: 'full',
        note: null,
        ipo_date: '1980-12-12',
      },
      {
        instrument_id: 2,
        symbol: 'MSFT',
        available_from: '2026-02-15T00:00:00Z',
        available_to: '2026-05-01T00:00:00Z',
        requested_first_bar_at: '2026-02-15T00:00:00Z',
        requested_last_bar_at: '2026-05-01T00:00:00Z',
        total_bars: 55,
        requested_bars: 55,
        requested_status: 'partial',
        note: 'Coverage begins after the requested start; earlier local history may be missing.',
        ipo_date: null,
      },
    ],
  },
  benchmark: {
    symbol: 'SPY',
    preview_note: 'Coverage begins after the requested start; earlier local history may be missing.',
    requested_status: 'partial',
    available_from: '2026-02-01T00:00:00Z',
    available_to: '2026-05-01T00:00:00Z',
    requested_first_bar_at: '2026-02-01T00:00:00Z',
    requested_last_bar_at: '2026-05-01T00:00:00Z',
    total_bars: 75,
    requested_bars: 75,
    requested_fits_range: false,
  },
  warnings: [],
}

describe('StrategyLabView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
    window.localStorage.removeItem('strategyLab.sections.v1')
    window.localStorage.removeItem('strategyLab.sidebar.v1')
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementation((path: string, params?: any) => {
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
      if (path === '/instruments/search') {
        const q = String(params?.q ?? '').trim().toUpperCase()
        return Promise.resolve(q ? [{ symbol: q, name: `${q} Inc.`, exchange: 'NASDAQ', type: 'Equity' }] : [])
      }
      if (path.startsWith('/instruments/') && path !== '/instruments/search') {
        return Promise.resolve({
          symbol: decodeURIComponent(path.split('/').pop() ?? '').toUpperCase(),
        })
      }
      return Promise.resolve([])
    })
    ;(api.post as ReturnType<typeof vi.fn>).mockImplementation((path: string) => {
      if (path === '/strategy-lab/coverage-preview') return Promise.resolve(clone(coveragePreviewResponse))
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
    ;(api.patch as ReturnType<typeof vi.fn>).mockImplementation((path: string, payload?: any) => {
      if (path === '/strategy-lab/definitions/4') {
        return Promise.resolve({
          ...clone(definition),
          name: payload?.name ?? definition.name,
          description: payload?.description ?? definition.description,
          tags: payload?.tags ?? definition.tags,
          is_active: payload?.is_active ?? definition.is_active,
        })
      }
      if (path === '/strategy-lab/versions/8') {
        return Promise.resolve({
          ...clone(definition).versions[0],
          definition_snapshot: payload?.definition_snapshot ?? definition.versions[0].definition_snapshot,
          parameter_schema: payload?.parameter_schema ?? definition.versions[0].parameter_schema,
          default_parameters: payload?.default_parameters ?? definition.versions[0].default_parameters,
          universe_config: payload?.universe_config ?? definition.versions[0].universe_config,
          benchmark_config: payload?.benchmark_config ?? definition.versions[0].benchmark_config,
          execution_model: payload?.execution_model ?? definition.versions[0].execution_model,
          notes: payload?.notes ?? definition.versions[0].notes,
        })
      }
      return Promise.resolve(clone(definition))
    })
    ;(api.delete as ReturnType<typeof vi.fn>).mockResolvedValue({})
  })

  function mountView() {
    return mount(StrategyLabView, {
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })
  }

  function findSearchBar(wrapper: ReturnType<typeof mount>, placeholder: string) {
    const component = wrapper.findAllComponents(SearchBar).find(node => node.props('placeholder') === placeholder)
    expect(component).toBeTruthy()
    return component!
  }

  async function ensurePanelExpanded(wrapper: ReturnType<typeof mount>, title: string) {
    const panel = wrapper.findAll('.panel').find(node =>
      node.find('h3').text().trim() === title,
    )
    expect(panel).toBeTruthy()
    if (!panel!.find('.panel-body').exists()) {
      await panel!.get('.panel-head-heading').trigger('click')
      await flushPromises()
    }
    expect(panel!.find('.panel-body').exists()).toBe(true)
    return panel!
  }

  function findFieldByLabel(wrapper: ReturnType<typeof mount>, label: string) {
    return wrapper.findAll('.field').find(node =>
      node.find('.field-label').exists() && node.find('.field-label').text().trim().startsWith(label),
    )
  }

  async function commitPicker(wrapper: ReturnType<typeof mount>, placeholder: string, value: string) {
    const component = findSearchBar(wrapper, placeholder)
    const input = component.get('input')
    await input.setValue(value)
    await new Promise(resolve => setTimeout(resolve, 280))
    await flushPromises()
    const results = component.findAll('.result-item')
    expect(results.length).toBeGreaterThan(0)
    await results[0].trigger('click')
    await flushPromises()
  }

  async function addTechnicalCondition(wrapper: ReturnType<typeof mount>) {
    const addButton = wrapper.findAll('button').find(button => button.text().includes('Add technical condition'))
    expect(addButton).toBeTruthy()
    await addButton!.trigger('click')
    await flushPromises()
  }

  it('loads the visual builder and hides engine branding', async () => {
    const wrapper = mountView()

    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('Momentum Pilot')
    })

    await ensurePanelExpanded(wrapper, 'Research runs')

    expect(wrapper.text()).toContain('Strategy Lab')
    expect(wrapper.text()).toContain('Entry logic')
    expect(wrapper.text()).toContain('Backtest')
    expect(wrapper.text()).toContain('12.50%')
    expect(wrapper.text()).toContain('AAPL')
    expect(wrapper.text()).not.toContain('Nautilus')
    expect(api.get).not.toHaveBeenCalledWith('/strategy-lab/engines')
    expect(wrapper.text()).toContain('Benchmark')
    expect(wrapper.text()).toContain('Return breakdown')
    expect(wrapper.text()).toContain('Position evolution')
    expect(wrapper.text()).toContain('Portfolio capital')
    expect(wrapper.text()).toContain('Execution log')
    expect(wrapper.text()).toContain('6 closed')
    expect(wrapper.text()).toContain('1 open')
    expect(wrapper.text()).toContain('Realized return')
    expect(wrapper.text()).toContain('Realized')
    expect(wrapper.text()).toContain('Unrealized')
    expect(wrapper.text()).toContain('$312.45')
    expect(wrapper.text()).toContain('+0.31%')
    expect(wrapper.text()).toContain('Open At End')
    expect(wrapper.text()).toContain('Run End Mark')
    expect(wrapper.text()).toContain('Rejected')
    expect(wrapper.text()).toContain('Max Concurrent Positions')
    expect(wrapper.text()).not.toContain('4 trades were rejected by portfolio controls.')
    expect(wrapper.text()).toContain('$1,250.45')
    expect(wrapper.text()).toContain('+12.50%')
    const positionEvolutionChart = wrapper
      .findAllComponents({ name: 'StrategyResultChart' })
      .find(component => component.props('label') === 'Per-position evolution')
    const drawdownChart = wrapper
      .findAllComponents({ name: 'StrategyResultChart' })
      .find(component => component.props('label') === 'Drawdown curve')
    expect(positionEvolutionChart).toBeTruthy()
    expect(drawdownChart).toBeTruthy()
    expect(positionEvolutionChart!.props('currency')).toBe(true)
    expect(positionEvolutionChart!.props('percent')).toBe(false)
    expect(drawdownChart!.props('showLegend')).toBe(true)
    const drawdownSeries = drawdownChart!.props('series') as Array<{ points: Array<{ value: number }> }>
    expect(drawdownSeries).toHaveLength(2)
    for (const series of drawdownSeries) {
      for (const point of series.points) {
        expect(point.value).toBeLessThanOrEqual(0)
      }
    }
    await wrapper.get('button[aria-label="Show position evolution in percent"]').trigger('click')
    await nextTick()
    expect(positionEvolutionChart!.props('currency')).toBe(false)
    expect(positionEvolutionChart!.props('percent')).toBe(true)
    expect(wrapper.findAll('button[aria-label="Export"]')).toHaveLength(1)
    expect(wrapper.find('button[aria-label="Export summary"]').exists()).toBe(false)
    expect(wrapper.find('button[aria-label="Export trades CSV"]').exists()).toBe(false)
    await wrapper.get('button[aria-label="Export"]').trigger('click')
    expect(wrapper.text()).toContain('Export summary')
    expect(wrapper.text()).toContain('Export trades CSV')
    expect(wrapper.find('button[aria-label="Show monthly returns"]').exists()).toBe(true)
    expect(wrapper.find('button[aria-label="Show quarterly returns"]').exists()).toBe(true)
    expect(wrapper.find('button[aria-label="Show yearly returns"]').exists()).toBe(true)
  })

  it('filters and sorts the execution log by individual columns', async () => {
    const wrapper = mountView()

    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('Momentum Pilot')
    })
    await ensurePanelExpanded(wrapper, 'Research runs')

    const table = wrapper.get('.trade-table-wrap')
    expect(table.find('input[aria-label="Filter execution log by Symbol"]').exists()).toBe(false)
    await table.get('button[aria-label="Filter execution log by Symbol"]').trigger('click')
    await flushPromises()
    const symbolFilter = table.get('input[aria-label="Filter execution log by Symbol"]')
    await symbolFilter.trigger('pointerdown')
    await flushPromises()
    expect(table.find('input[aria-label="Filter execution log by Symbol"]').exists()).toBe(true)

    await symbolFilter.setValue('MSFT')
    await flushPromises()

    expect(table.text()).toContain('MSFT')
    expect(table.text()).toContain('Rejected')
    expect(table.text()).toContain('Max Concurrent Positions')
    expect(table.text()).not.toContain('AAPL')
    expect(table.get('button[aria-label="Edit active execution log by Symbol"]').classes()).toContain('trade-table__filter-button--active')

    await symbolFilter.setValue('')
    document.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await flushPromises()
    expect(table.find('input[aria-label="Filter execution log by Symbol"]').exists()).toBe(false)

    await table.get('button[aria-label="Filter execution log by Time"]').trigger('click')
    await flushPromises()
    const timeFilter = table.get('input[aria-label="Filter execution log by Time"]')
    await timeFilter.setValue('08/02 00')
    await flushPromises()

    expect(table.text()).toContain('Take Profit')
    expect(table.text()).not.toContain('Max Concurrent Positions')

    await timeFilter.setValue('')
    await table.get('button[aria-label="Sort execution log by Time"]').trigger('click')
    await flushPromises()

    const firstRow = table.findAll('tbody tr')[0]
    expect(firstRow.text()).toContain('Open At End')
    expect(firstRow.text()).toContain('Run End Mark')
  })

  it('shows coverage preview during run prep and detailed coverage in results', async () => {
    const wrapper = mountView()

    await flushPromises()
    await ensurePanelExpanded(wrapper, 'Research runs')

    expect(api.post).toHaveBeenCalledWith('/strategy-lab/coverage-preview', expect.objectContaining({
      timeframe: 'D1',
      universe_config: { symbols: ['AAPL', 'MSFT'] },
      benchmark_config: { symbol: 'SPY' },
    }))
    expect(wrapper.text()).toContain('Coverage preview')
    expect(wrapper.text()).toContain('Shared universe')
    expect(wrapper.text()).toContain('Coverage issues')

    const instrumentCoverageToggle = wrapper
      .findAll('button')
      .find(button => button.text().includes('Coverage issues'))
    expect(instrumentCoverageToggle).toBeTruthy()
    await instrumentCoverageToggle!.trigger('click')
    await nextTick()

    expect(wrapper.text()).toContain('MSFT')
    expect(wrapper.text()).toContain('Requested strategy range')
    expect(wrapper.text()).toContain('earlier local history may be missing')
  })

  it('supports collapsing the strategy sidebar', async () => {
    const wrapper = mountView()

    await flushPromises()

    await wrapper.get('.sidebar-toggle-strip').trigger('click')
    expect(wrapper.get('.strategy-sidebar').classes()).toContain('strategy-sidebar--collapsed')

    await wrapper.get('.sidebar-toggle-strip').trigger('click')
    expect(wrapper.get('.strategy-sidebar').classes()).not.toContain('strategy-sidebar--collapsed')
  })

  it('shows the benchmark coverage note with an explicit year when benchmark data starts later', async () => {
    const delayedBenchmarkDefinition = clone(definition)
    delayedBenchmarkDefinition.runs[0].result_summary.benchmark.equity_curve = [
      { ts: '2026-01-02T05:00:00Z', equity: 100000 },
      { ts: '2026-02-01T00:00:00Z', equity: 101200 },
    ]
    delayedBenchmarkDefinition.runs[0].result_summary.benchmark.coverage = {
      symbol: 'SPY',
      preview_note: 'Coverage begins after the requested start; earlier benchmark bars are unavailable for this run.',
      requested_status: 'partial',
      available_from: '2026-01-02T05:00:00Z',
      available_to: '2026-05-01T00:00:00Z',
      requested_first_bar_at: '2026-01-02T05:00:00Z',
      requested_last_bar_at: '2026-05-01T00:00:00Z',
      total_bars: 119,
      requested_bars: 119,
      requested_fits_range: false,
    }

    ;(api.get as ReturnType<typeof vi.fn>).mockImplementation((path: string, params?: any) => {
      if (path === '/strategy-lab/definitions') return Promise.resolve([delayedBenchmarkDefinition])
      if (path === '/strategy-lab/definitions/4') return Promise.resolve(delayedBenchmarkDefinition)
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
      if (path === '/instruments/search') {
        const q = String(params?.q ?? '').trim().toUpperCase()
        return Promise.resolve(q ? [{ symbol: q, name: `${q} Inc.`, exchange: 'NASDAQ', type: 'Equity' }] : [])
      }
      if (path.startsWith('/instruments/') && path !== '/instruments/search') {
        return Promise.resolve({
          symbol: decodeURIComponent(path.split('/').pop() ?? '').toUpperCase(),
        })
      }
      return Promise.resolve([])
    })

    const wrapper = mountView()

    await flushPromises()

    expect(wrapper.text()).toContain('Benchmark coverage starts on 02/01/2026, 05:00')
  })

  it('defaults section expansion based on whether the strategy already has runs', async () => {
    const wrapper = mountView()

    await flushPromises()

    const panels = wrapper.findAll('.panel')
    expect(panels[0].find('.panel-body').exists()).toBe(false)
    expect(panels[1].find('.panel-body').exists()).toBe(false)
    expect(panels[2].find('.panel-body').exists()).toBe(false)
    expect(panels[3].find('.panel-body').exists()).toBe(false)
    expect(panels[4].find('.panel-body').exists()).toBe(false)
    expect(panels[5].find('.panel-body').exists()).toBe(true)

    await wrapper.get('.sidebar-new-btn').trigger('click')
    await flushPromises()

    const newPanels = wrapper.findAll('.panel')
    expect(newPanels[0].find('.panel-body').exists()).toBe(true)
    expect(newPanels[1].find('.panel-body').exists()).toBe(true)
    expect(newPanels[2].find('.panel-body').exists()).toBe(true)
    expect(newPanels[3].find('.panel-body').exists()).toBe(true)
    expect(newPanels[4].find('.panel-body').exists()).toBe(true)
    expect(newPanels[5].find('.panel-body').exists()).toBe(false)
  })

  it('supports collapsing sections from the title as well as the chevron', async () => {
    const wrapper = mountView()

    await flushPromises()

    const resultsPanel = wrapper.findAll('.panel')[5]
    expect(resultsPanel.find('.panel-body').exists()).toBe(true)

    await resultsPanel.get('.panel-head-heading').trigger('click')
    await flushPromises()

    expect(resultsPanel.find('.panel-body').exists()).toBe(false)
    expect(resultsPanel.get('.panel-toggle').attributes('aria-expanded')).toBe('false')
  })

  it('does not preselect a comparison run by default', async () => {
    const multiRunDefinition = clone(definition)
    multiRunDefinition.runs = [
      ...multiRunDefinition.runs,
      {
        ...clone(definition.runs[0]),
        id: 13,
        created_at: '2026-05-10T09:55:00Z',
        started_at: '2026-05-10T09:55:00Z',
        completed_at: '2026-05-10T09:55:01Z',
      },
    ]

    ;(api.get as ReturnType<typeof vi.fn>).mockImplementation((path: string, params?: any) => {
      if (path === '/strategy-lab/definitions') return Promise.resolve([multiRunDefinition])
      if (path === '/strategy-lab/definitions/4') return Promise.resolve(multiRunDefinition)
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
      if (path === '/screeners') return Promise.resolve([{ id: 7, name: 'Momentum Universe' }])
      if (path === '/instruments/search') {
        const q = String(params?.q ?? '').trim().toUpperCase()
        return Promise.resolve(q ? [{ symbol: q, name: `${q} Inc.`, exchange: 'NASDAQ', type: 'Equity' }] : [])
      }
      if (path.startsWith('/instruments/') && path !== '/instruments/search') {
        return Promise.resolve({
          symbol: decodeURIComponent(path.split('/').pop() ?? '').toUpperCase(),
        })
      }
      return Promise.resolve([])
    })

    const wrapper = mountView()
    await flushPromises()

    const compareSelectByLabel = wrapper.findAll('select').find(node =>
      node.element.closest('label')?.textContent?.includes('Compare against'),
    )
    expect(compareSelectByLabel).toBeTruthy()
    const compareSelect = compareSelectByLabel!.element as HTMLSelectElement
    expect(compareSelect.selectedIndex).toBe(0)
    expect(compareSelect.options[0]?.text).toBe('No comparison')
  })

  it('creates a strategy from the visual builder without JSON payload editing', async () => {
    const wrapper = mountView()

    await flushPromises()

    await wrapper.get('.sidebar-new-btn').trigger('click')
    await wrapper.get('input[placeholder="Momentum Continuation"]').setValue('Breakout Stack')
    await wrapper.get('textarea.form-textarea--short').setValue('Trend strategy')
    await addTechnicalCondition(wrapper)
    const tagInput = wrapper.get('input[placeholder="Add or reuse tags"]')
    await tagInput.setValue('breakout')
    await tagInput.trigger('keydown.enter')
    await flushPromises()
    await commitPicker(wrapper, 'Add symbol (e.g. AAPL)', 'NVDA')
    await commitPicker(wrapper, 'Add symbol (e.g. AAPL)', 'AMD')
    await wrapper.get('.detail-header .btn-primary').trigger('click')

    await flushPromises()

    expect(api.post).toHaveBeenCalledWith('/strategy-lab/definitions', expect.objectContaining({
      name: 'Breakout Stack',
      definition_type: 'rules',
      source_type: 'custom',
      tags: ['breakout'],
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

  it('allows publishing screener-style fundamental conditions from the visual builder', async () => {
    const wrapper = mountView()

    await flushPromises()

    await wrapper.get('.sidebar-new-btn').trigger('click')
    await wrapper.get('input[placeholder="Momentum Continuation"]').setValue('Fundamental Rotation')
    await commitPicker(wrapper, 'Add symbol (e.g. AAPL)', 'AAPL')
    await addTechnicalCondition(wrapper)

    const conditionTypeSelect = wrapper.findAll('select').find(node =>
      Array.from((node.element as HTMLSelectElement).options).some(option => option.text === 'Fundamental Filter'),
    )
    expect(conditionTypeSelect).toBeTruthy()
    await conditionTypeSelect!.setValue('fundamental_filter')
    await flushPromises()

    const textConditionInput = wrapper.findAll('.tech-cond-card input.form-input').find(node =>
      node.element instanceof HTMLInputElement && node.element.type === 'text',
    )
    expect(textConditionInput).toBeTruthy()
    await textConditionInput!.setValue('Technology')

    await wrapper.get('.detail-header .btn-primary').trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith('/strategy-lab/definitions', expect.objectContaining({
      initial_version: expect.objectContaining({
        definition_snapshot: expect.objectContaining({
          conditions: expect.arrayContaining([
            expect.objectContaining({
              type: 'fundamental_filter',
              field: 'sector',
              op: 'eq',
              value: 'Technology',
            }),
          ]),
        }),
      }),
    }))
  })

  it('allows creating a new strategy once name and universe are set, even before adding conditions', async () => {
    const wrapper = mountView()

    await flushPromises()

    await wrapper.get('.sidebar-new-btn').trigger('click')
    await wrapper.get('input[placeholder="Momentum Continuation"]').setValue('Blank Draft')
    await commitPicker(wrapper, 'Add symbol (e.g. AAPL)', 'AAPL')
    await flushPromises()

    const createButton = wrapper.findAll('button').find(button => button.text() === 'Create strategy')
    expect(createButton).toBeTruthy()
    expect(createButton!.attributes('disabled')).toBeUndefined()

    await createButton!.trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith('/strategy-lab/definitions', expect.objectContaining({
      name: 'Blank Draft',
      initial_version: expect.objectContaining({
        definition_snapshot: expect.objectContaining({
          conditions: [],
          condition_tree: expect.objectContaining({
            type: 'all',
            conditions: [],
          }),
        }),
        universe_config: { symbols: ['AAPL'] },
      }),
    }))
  })

  it('keeps the sidebar card tags in sync with live draft tags', async () => {
    const wrapper = mountView()

    await flushPromises()
    await ensurePanelExpanded(wrapper, 'Strategy profile')

    const tagInput = wrapper.get('.tag-picker .tag-input')
    await tagInput.setValue('swing test')
    await tagInput.trigger('keydown.enter')
    await flushPromises()

    const sidebarTags = wrapper.findAll('.definition-item.active .definition-tag').map(node => node.text())
    expect(sidebarTags).toContain('momentum')
    expect(sidebarTags).toContain('swing-test')
  })

  it('shows clear creation blockers for a new incomplete strategy', async () => {
    const wrapper = mountView()

    await flushPromises()
    await wrapper.get('.sidebar-new-btn').trigger('click')
    await flushPromises()

    expect(wrapper.get('input[placeholder="Momentum Continuation"]').classes()).toContain('form-input--invalid')
    const universeSelect = wrapper.findAll('select').find(node =>
      Array.from((node.element as HTMLSelectElement).options).some(option => option.text === 'Manual symbols'),
    )
    expect(universeSelect).toBeTruthy()
    expect(universeSelect!.classes()).toContain('form-select--invalid')
    expect(wrapper.text()).toContain('Name Required')
    expect(wrapper.text()).toContain('Universe type Required')
    expect(wrapper.text()).not.toContain('Condition 1')
    const createButton = wrapper.findAll('button').find(button => button.text() === 'Create strategy')
    expect(createButton).toBeTruthy()
    expect(createButton!.attributes('disabled')).toBeDefined()
  })

  it('allows radar strategies to use radar outputs as the default universe', async () => {
    const wrapper = mountView()

    await flushPromises()
    await wrapper.get('.sidebar-new-btn').trigger('click')
    await wrapper.get('input[placeholder="Momentum Continuation"]').setValue('Radar Native Replay')
    await wrapper.findAll('select')[0].setValue('radar')
    await flushPromises()

    expect(wrapper.text()).not.toContain('Universe type Required')
    expect(wrapper.text()).toContain('Using Radar outputs.')

    await wrapper.get('.detail-header .btn-primary').trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith('/strategy-lab/definitions', expect.objectContaining({
      source_type: 'radar',
      initial_version: expect.objectContaining({
        universe_config: {},
      }),
    }))
  })

  it('publishes only resolved benchmark symbols and limits subset runs to selected universe symbols', async () => {
    const wrapper = mountView()

    await flushPromises()
    await ensurePanelExpanded(wrapper, 'Strategy profile')
    await ensurePanelExpanded(wrapper, 'Entry logic')

    await commitPicker(wrapper, 'SPY', 'QQQ')

    const noteInput = wrapper.get('input[placeholder="What changed in this revision?"]')
    await noteInput.setValue('Benchmark update')
    await wrapper.get('.detail-header .btn-primary').trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith('/strategy-lab/definitions/4/versions', expect.objectContaining({
      benchmark_config: { symbol: 'QQQ' },
    }))

    wrapper.unmount()
    setActivePinia(createPinia())
    const subsetWrapper = mountView()
    await flushPromises()
    await ensurePanelExpanded(subsetWrapper, 'Research runs')
    ;(subsetWrapper.get('.advanced-toggle').element as HTMLButtonElement).click()
    await flushPromises()

    const subsetToggle = subsetWrapper.get('.advanced-panel .field--checkbox input[type="checkbox"]')
    await subsetToggle.setValue(true)
    await flushPromises()

    const subsetTrigger = subsetWrapper.findAll('button').find(button => button.text().includes('Select at least one symbol'))
    expect(subsetTrigger).toBeTruthy()
    await subsetTrigger!.trigger('click')
    await flushPromises()

    const subsetOptions = subsetWrapper.findAll('.multi-select-option')
    expect(subsetOptions.map(node => node.text())).toEqual(expect.arrayContaining(['AAPL', 'MSFT']))
    const msftOption = subsetOptions.find(node => node.text().includes('MSFT'))
    expect(msftOption).toBeTruthy()
    await msftOption!.get('input').setValue(true)
    await flushPromises()

    const runButton = subsetWrapper.findAll('button').find(button => button.text() === 'Run backtest')
    expect(runButton).toBeTruthy()
    await runButton!.trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith('/strategy-lab/versions/8/runs', expect.objectContaining({
      universe_config: { symbols: ['MSFT'] },
    }))
  })

  it('publishes revisions and runs backtests from the current visual state', async () => {
    const wrapper = mountView()

    await flushPromises()
    await ensurePanelExpanded(wrapper, 'Entry logic')
    await ensurePanelExpanded(wrapper, 'Research runs')

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
        commission_model: 'fixed_round_trip',
        commission_value: null,
        close_open_positions_at_end: false,
      }),
    }))
  })

  it('saves the current draft version including conditions and run defaults', async () => {
    const wrapper = mountView()

    await flushPromises()
    await ensurePanelExpanded(wrapper, 'Entry logic')
    await ensurePanelExpanded(wrapper, 'Risk')
    await ensurePanelExpanded(wrapper, 'Research runs')

    await addTechnicalCondition(wrapper)
    const stopModelSelect = wrapper.findAll('select').find(node =>
      Array.from((node.element as HTMLSelectElement).options).some(option => option.text === 'ATR multiple'),
    )
    const sizingModelSelect = wrapper.findAll('select').find(node =>
      Array.from((node.element as HTMLSelectElement).options).some(option => option.text === 'Fixed cash'),
    )
    expect(stopModelSelect).toBeTruthy()
    expect(sizingModelSelect).toBeTruthy()
    await stopModelSelect!.setValue('atr')
    await sizingModelSelect!.setValue('fixed_cash')
    await flushPromises()
    const atrPeriodField = findFieldByLabel(wrapper, 'ATR period')
    const atrMultipleField = findFieldByLabel(wrapper, 'ATR multiple')
    const fixedCashField = findFieldByLabel(wrapper, 'Cash per position')
    expect(atrPeriodField).toBeTruthy()
    expect(atrMultipleField).toBeTruthy()
    expect(fixedCashField).toBeTruthy()
    await atrPeriodField!.get('input').setValue('21')
    await atrMultipleField!.get('input').setValue('2.5')
    await fixedCashField!.get('input').setValue('15000')
    const dateInputs = wrapper.findAll('input[type="date"]')
    expect(dateInputs).toHaveLength(2)
    await dateInputs[0].setValue('2026-02-01')
    await dateInputs[1].setValue('2026-04-30')
    const capitalInput = wrapper.findAll('input.form-input').find(node =>
      node.element instanceof HTMLInputElement && node.element.type === 'number' && node.element.value === '100000',
    )
    expect(capitalInput).toBeTruthy()
    await capitalInput!.setValue('250000')
    const closeAtEndField = findFieldByLabel(wrapper, 'Close open positions at run end')
    expect(closeAtEndField).toBeTruthy()
    await closeAtEndField!.get('input').setValue(true)

    const saveButton = wrapper.get('button[aria-label="Save profile"]')
    await saveButton.trigger('click')
    await flushPromises()

    expect(api.patch).toHaveBeenCalledWith('/strategy-lab/versions/8', expect.objectContaining({
      definition_snapshot: expect.objectContaining({
        conditions: expect.any(Array),
        risk: expect.objectContaining({
          stop_model: 'atr',
          stop_atr_period: 21,
          stop_atr_multiple: 2.5,
          position_sizing_mode: 'fixed_cash',
          position_sizing_value: 15000,
        }),
      }),
      execution_model: expect.objectContaining({
        run_defaults: expect.objectContaining({
          date_from: '2026-02-01',
          date_to: '2026-04-30',
          initial_capital: 250000,
          commission_model: 'fixed_round_trip',
          commission_value: null,
          close_open_positions_at_end: true,
        }),
      }),
    }))
  })

  it('persists and hydrates sweep-capable input modes for saved versions', async () => {
    const persistedDefinition = clone(definition)
    persistedDefinition.versions[0].execution_model = {
      entry: 'next_bar_open',
      run_defaults: {
        parameter_sweeps: {
          stop_loss_pct: {
            mode: 'list',
            single: 2,
            list: [1.5, 2],
            range: { start: 1.5, end: 2, step: 0.5 },
          },
          take_profit_rr: {
            mode: 'range',
            single: 2.5,
            list: [],
            range: { start: 1, end: 3, step: 0.5 },
          },
          max_bars_in_trade: {
            mode: 'single',
            single: 18,
            list: [],
            range: { start: 18, end: 18, step: 1 },
          },
        },
      },
    }

    ;(api.get as ReturnType<typeof vi.fn>).mockImplementation((path: string, params?: any) => {
      if (path === '/strategy-lab/definitions') return Promise.resolve([persistedDefinition])
      if (path === '/strategy-lab/definitions/4') return Promise.resolve(persistedDefinition)
      if (path === '/watchlists') return Promise.resolve([])
      if (path === '/screeners') return Promise.resolve([])
      if (path === '/instruments/search') {
        const q = String(params?.q ?? '').trim().toUpperCase()
        return Promise.resolve(q ? [{ symbol: q, name: `${q} Inc.`, exchange: 'NASDAQ', type: 'Equity' }] : [])
      }
      if (path.startsWith('/instruments/') && path !== '/instruments/search') {
        return Promise.resolve({ symbol: decodeURIComponent(path.split('/').pop() ?? '').toUpperCase() })
      }
      return Promise.resolve([])
    })

    const wrapper = mountView()
    await flushPromises()
    await ensurePanelExpanded(wrapper, 'Risk')
    await ensurePanelExpanded(wrapper, 'Exits')

    expect(wrapper.find('.sweep-indicator--list').exists()).toBe(true)
    expect(findFieldByLabel(wrapper, 'Stop loss %')!.text()).toContain('1.5')
    expect(findFieldByLabel(wrapper, 'Stop loss %')!.text()).toContain('2')
    const targetField = findFieldByLabel(wrapper, 'Target (R)')!
    expect(targetField.find('.sweep-value-input__range').exists()).toBe(true)
    expect(targetField.findAll('input').map(input => (input.element as HTMLInputElement).value)).toEqual(['1', '3', '0.5'])

    await wrapper.get('button[aria-label="Save profile"]').trigger('click')
    await flushPromises()

    expect(api.patch).toHaveBeenCalledWith('/strategy-lab/versions/8', expect.objectContaining({
      execution_model: expect.objectContaining({
        run_defaults: expect.objectContaining({
          parameter_sweeps: expect.objectContaining({
            stop_loss_pct: expect.objectContaining({
              mode: 'list',
              list: [1.5, 2],
            }),
            take_profit_rr: expect.objectContaining({
              mode: 'range',
              range: { start: 1, end: 3, step: 0.5 },
            }),
          }),
        }),
      }),
    }))
  })

  it('serializes blank optional strategy controls as disabled null values', async () => {
    const wrapper = mountView()

    await flushPromises()
    await ensurePanelExpanded(wrapper, 'Risk')
    await ensurePanelExpanded(wrapper, 'Exits')
    await ensurePanelExpanded(wrapper, 'Research runs')

    await findFieldByLabel(wrapper, 'Break-even after R')!.get('input').setValue('')
    await findFieldByLabel(wrapper, 'Trail distance (R)')!.get('input').setValue('')
    await findFieldByLabel(wrapper, 'Target (R)')!.get('input').setValue('')
    await findFieldByLabel(wrapper, 'Max bars in trade')!.get('input').setValue('')
    await findFieldByLabel(wrapper, 'Slippage (bps)')!.get('input').setValue('')
    await findFieldByLabel(wrapper, 'Commission per round-trip')!.get('input').setValue('')

    const saveButton = wrapper.get('button[aria-label="Save profile"]')
    await saveButton.trigger('click')
    await flushPromises()

    expect(api.patch).toHaveBeenCalledWith('/strategy-lab/versions/8', expect.objectContaining({
      definition_snapshot: expect.objectContaining({
        risk: expect.objectContaining({
          break_even_rr: null,
          trailing_stop_rr: null,
        }),
        exits: expect.objectContaining({
          take_profit_rr: null,
          max_bars_in_trade: null,
        }),
      }),
      execution_model: expect.objectContaining({
        run_defaults: expect.objectContaining({
          slippage_bps: null,
          commission_value: null,
          commission_per_trade: null,
        }),
      }),
    }))
  })

  it('starts a new custom strategy with an empty rule builder until the user adds a condition', async () => {
    const wrapper = mountView()

    await flushPromises()
    await wrapper.get('.sidebar-new-btn').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Root logic')
    expect(wrapper.text()).toContain('Add technical condition')
    expect(wrapper.text()).not.toContain('Condition 1')

    await addTechnicalCondition(wrapper)

    expect(wrapper.text()).toContain('Condition 1')
  })

  it('supports walk-forward mode, watchlist universes, and implicit parameter batches from original inputs', async () => {
    const wrapper = mountView()

    await flushPromises()
    await ensurePanelExpanded(wrapper, 'Strategy profile')
    await ensurePanelExpanded(wrapper, 'Risk')
    await ensurePanelExpanded(wrapper, 'Exits')
    await ensurePanelExpanded(wrapper, 'Research runs')

    await wrapper.get('select').setValue('custom')
    const selects = wrapper.findAll('select')
    await selects[1].setValue('watchlist')
    await flushPromises()
    const watchlistSelect = wrapper.findAll('select').find(node => node.element instanceof HTMLSelectElement && Array.from((node.element as HTMLSelectElement).options).some(option => option.text === 'Growth'))
    expect(watchlistSelect).toBeTruthy()
    await watchlistSelect!.setValue('3')
    await wrapper.findAll('.mode-pill')[1].trigger('click')
    await flushPromises()
    expect(wrapper.text()).not.toContain('Parameter combinations')
    expect(wrapper.text()).not.toContain('Sweep-capable')
    expect(wrapper.findAll('.sweep-indicator')).toHaveLength(3)
    expect(wrapper.text()).not.toContain('Single value, comma list, or range')
    expect(wrapper.text()).toContain('Max bars in trade')
    const stopSweep = wrapper.findAll('.sweep-value-input')[0]
    expect(stopSweep).toBeTruthy()
    await wrapper.findAll('.sweep-indicator')[0].trigger('click')
    expect(stopSweep.find('input[aria-label="Add value to list"]').exists()).toBe(true)
    await stopSweep.trigger('click')
    await flushPromises()
    expect(stopSweep.find('input[aria-label="Add value to list"]').exists()).toBe(true)
    await stopSweep.get('button[aria-label="Remove 2"]').trigger('click')
    const listInput = stopSweep.get('input[aria-label="Add value to list"]')
    await listInput.setValue('1.5')
    await stopSweep.get('button[aria-label="Add list value"]').trigger('click')
    await listInput.setValue('2')
    await stopSweep.get('button[aria-label="Add list value"]').trigger('click')

    const runButton = wrapper.findAll('button').find(button => button.text() === 'Run walk-forward')
    expect(runButton).toBeTruthy()
    await runButton!.trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith('/strategy-lab/versions/8/runs', expect.objectContaining({
      test_mode: 'walk_forward',
      parameter_grid: expect.objectContaining({
        parameters: expect.arrayContaining([
          expect.objectContaining({
            key: 'risk.stop_loss_pct',
            values: [1.5, 2],
          }),
        ]),
      }),
      execution_assumptions: expect.objectContaining({
        optimization: expect.objectContaining({
          enabled: false,
        }),
      }),
    }))
  })

  it('publishes radar replay strategies with screener universes from the visual builder', async () => {
    const wrapper = mountView()

    await flushPromises()

    await wrapper.get('.sidebar-new-btn').trigger('click')
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
    const setupTrigger = wrapper.findAll('.multi-select-trigger')[0]
    expect(setupTrigger).toBeTruthy()
    await setupTrigger!.trigger('click')
    await flushPromises()
    const breakoutCheckbox = wrapper.findAll('.multi-select-menu .multi-select-option').find(node =>
      node.text().includes('Breakout'),
    )?.find('input')
    expect(breakoutCheckbox).toBeTruthy()
    await breakoutCheckbox!.setValue(true)
    await flushPromises()
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

  it('deletes strategies from the current selection', async () => {
    const wrapper = mountView()

    await flushPromises()
    await wrapper.get('.detail-actions .btn-danger').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('Delete Strategy')
    expect(document.body.textContent).toContain('Delete strategy "Momentum Pilot"? This action cannot be undone.')
    const confirmButton = Array.from(document.body.querySelectorAll('button')).find(button =>
      button.textContent?.trim() === 'Delete',
    )
    expect(confirmButton).toBeTruthy()
    ;(confirmButton as HTMLButtonElement).click()
    await flushPromises()

    expect(api.delete).toHaveBeenCalledWith('/strategy-lab/definitions/4')
  })
})
