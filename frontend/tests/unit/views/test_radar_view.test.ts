import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import RadarView from '@/views/RadarView.vue'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

import { api } from '@/lib/api'
import { useRadarStore } from '@/stores/radar'

async function flushPromises() {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
}

const radarDetailPreviewChartStub = {
  template: '<div class="radar-preview-stub">Preview</div>',
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(res => {
    resolve = res
  })
  return { promise, resolve }
}

const summaryDetection = {
  id: 42,
  run_id: 5,
  instrument_id: 7,
  instrument_symbol: 'AAPL',
  instrument_name: 'Apple',
  timeframe: 'D1',
  setup_type: 'breakout',
  state: 'confirmed',
  state_reason: 'Confirmed breakout. The next objective is the next resistance while price holds above the breakout zone.',
  score: 0.82,
  observed_at: '2026-05-04T10:00:00Z',
  signal_at: '2026-05-04T10:00:00Z',
  context_at: '2026-05-01T10:00:00Z',
  fresh_until: '2026-05-09T10:00:00Z',
  thread_id: 11,
  thread_event_index: 2,
  key_level_price: 112.5,
  entry_price: 112.9,
  invalidation_price: 110.0,
  target_price: 118.5,
  outcome_status: 'open',
  outcome_last_evaluated_at: '2026-05-04T10:00:00Z',
  bars_since_signal: 0,
  max_favorable_excursion_pct: null,
  max_adverse_excursion_pct: null,
  target_hit_at: null,
  invalidated_at: null,
  summary: 'AAPL is showing a breakout setup.',
  invalidation_hint: 'Invalidate if price falls back below 110.',
  score_factors: { normalized_score: 0.82, overlap_confluence: 0.5 },
  created_at: '2026-05-04T10:00:05Z',
  updated_at: '2026-05-04T10:00:05Z',
}

const detailDetection = {
  ...summaryDetection,
  evidence: {
    overlays: [],
    indicator_visuals: [],
    drawing_visuals: [],
    metrics: {
      close: 113.2,
      atr_14: 2.1,
      signal_time: 1777953600,
      context_time: 1771822800,
      avwap: 111.8,
      avwap_anchor_type: 'week52_high',
      avwap_anchor_time: 1767225600,
      avwap_anchor_price: 109.4,
      secondary_avwap: 110.9,
      secondary_avwap_anchor_type: 'all_time_high',
      week52_high: 120.4,
      week52_high_time: 1767225600,
      bb_width: 0.042,
      bb_width_percentile: 0.08,
      inside_keltner: true,
      volatility_squeeze_active: true,
      multi_timeframe_hits: 2,
      entry_price: 112.9,
      invalidation_price: 110.0,
      target_price: 118.5,
      target_source: 'next resistance',
      risk_reward: 2.0,
      state: 'confirmed',
      state_reason: 'Confirmed breakout. The next objective is the next resistance while price holds above the breakout zone.',
    },
    structures: [{ type: 'trendline' }],
  },
  thread: {
    id: 11,
    instrument_id: 7,
    timeframe: 'D1',
    context_role: 'resistance',
    reference_price: 112.5,
    current_setup_type: 'breakout',
    current_state: 'confirmed',
    state_changed_at: '2026-05-04T10:00:00Z',
    started_at: '2026-04-28T10:00:00Z',
    last_seen_at: '2026-05-04T10:00:00Z',
    detection_count: 2,
  },
  thread_history: [
    {
      id: 40,
      setup_type: 'approaching_resistance',
      state: 'developing',
      state_reason: 'Developing near resistance; watch for rejection or failure before treating it as confirmed.',
      score: 0.71,
      observed_at: '2026-05-01T10:00:00Z',
      signal_at: '2026-05-01T10:00:00Z',
      context_at: '2026-04-30T10:00:00Z',
      thread_event_index: 1,
      key_level_price: 112.1,
      entry_price: 112.1,
      invalidation_price: 113.0,
      target_price: 107.4,
      summary: 'AAPL approached resistance.',
      invalidation_hint: 'Close above 113.',
      outcome_status: 'open',
      outcome_last_evaluated_at: '2026-05-01T10:00:00Z',
      bars_since_signal: 0,
      max_favorable_excursion_pct: null,
      max_adverse_excursion_pct: null,
      target_hit_at: null,
      invalidated_at: null,
      created_at: '2026-05-01T10:00:05Z',
      updated_at: '2026-05-01T10:00:05Z',
    },
    {
      id: 42,
      setup_type: 'breakout',
      state: 'confirmed',
      state_reason: 'Confirmed breakout. The next objective is the next resistance while price holds above the breakout zone.',
      score: 0.82,
      observed_at: '2026-05-04T10:00:00Z',
      signal_at: '2026-05-04T10:00:00Z',
      context_at: '2026-05-01T10:00:00Z',
      thread_event_index: 2,
      key_level_price: 112.5,
      entry_price: 112.9,
      invalidation_price: 110.0,
      target_price: 118.5,
      summary: 'AAPL is showing a breakout setup.',
      invalidation_hint: 'Invalidate if price falls back below 110.',
      outcome_status: 'open',
      outcome_last_evaluated_at: '2026-05-04T10:00:00Z',
      bars_since_signal: 0,
      max_favorable_excursion_pct: null,
      max_adverse_excursion_pct: null,
      target_hit_at: null,
      invalidated_at: null,
      created_at: '2026-05-04T10:00:05Z',
      updated_at: '2026-05-04T10:00:05Z',
    },
  ],
}

describe('RadarView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.innerWidth = 1440
    vi.resetAllMocks()
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementation((path: string) => {
      if (path === '/radar/runs') {
        return Promise.resolve([
          {
            id: 5,
            timeframe: 'D1',
            universe_type: 'all',
            status: 'completed',
            started_at: '2026-05-04T09:58:00Z',
            completed_at: '2026-05-04T10:00:00Z',
            evaluated_count: 12,
            detection_count: 3,
            error_summary: null,
            created_at: '2026-05-04T09:58:00Z',
            updated_at: '2026-05-04T10:00:00Z',
          },
        ])
      }
      if (path === '/watchlists') {
        return Promise.resolve([
          {
            id: 9,
            user_id: 1,
            name: 'Priority',
            description: null,
            is_default: false,
            is_managed: false,
            is_locked: false,
            position: 2,
            items: [],
            screener_id: null,
          },
        ])
      }
      if (path === '/baskets') {
        return Promise.resolve([
          {
            id: 44,
            user_id: 1,
            name: 'SPY holdings',
            description: null,
            source_type: 'etf_holdings',
            weighting_scheme: 'market_cap',
            rebalance_frequency: null,
            classification_mode: 'custom',
            sector: null,
            industry: null,
            source_etf_profile_id: null,
            source_snapshot_id: null,
            composition_date: '2026-05-01',
            is_system_managed: true,
            is_read_only: true,
            metadata: {},
            members: [
              {
                id: 1,
                instrument_id: 7,
                symbol: 'AAPL',
                name: 'Apple',
                source_holding_id: null,
                position: 1,
                weight: null,
                label: null,
                notes: null,
                metadata: {},
                created_at: '2026-05-01T00:00:00Z',
                updated_at: '2026-05-01T00:00:00Z',
              },
            ],
            created_at: '2026-05-01T00:00:00Z',
            updated_at: '2026-05-01T00:00:00Z',
          },
        ])
      }
      if (path === '/radar/detections') return Promise.resolve([summaryDetection])
      if (path === '/radar/detections/42') return Promise.resolve(detailDetection)
      if (path === '/radar/instruments/7/history') {
        return Promise.resolve([
          detailDetection,
          {
            ...summaryDetection,
            id: 43,
            timeframe: 'H4',
            setup_type: 'breakout_retest',
            signal_at: '2026-05-04T08:00:00Z',
            outcome_status: 'target_hit',
            bars_since_signal: 4,
            target_hit_at: '2026-05-05T12:00:00Z',
            created_at: '2026-05-05T12:01:00Z',
            updated_at: '2026-05-05T12:01:00Z',
          },
        ])
      }
      if (path === '/radar/outcomes/summary') {
        return Promise.resolve([
          {
            timeframe: 'D1',
            setup_type: 'breakout',
            total: 3,
            open_count: 1,
            target_hit_count: 1,
            invalidated_count: 1,
            stale_count: 0,
            target_hit_rate: 1 / 3,
            invalidated_rate: 1 / 3,
            stale_rate: 0,
            avg_mfe_pct: 5.6,
            avg_mae_pct: -2.1,
          },
        ])
      }
      return Promise.resolve([])
    })
    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 6,
      status: 'completed',
      timeframe: 'D1',
      universe_type: 'all',
      started_at: '2026-05-04T10:05:00Z',
      completed_at: '2026-05-04T10:05:01Z',
      evaluated_count: 12,
      detection_count: 3,
      error_summary: null,
      created_at: '2026-05-04T10:05:00Z',
      updated_at: '2026-05-04T10:05:01Z',
    })
  })

  it('loads detections, shows detail, and opens the detection in chart', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const radarStore = useRadarStore()
    const wrapper = mount(RadarView, {
      global: {
        plugins: [pinia],
        stubs: {
          RadarDetailPreviewChart: radarDetailPreviewChartStub,
        },
      },
    })

    await flushPromises()
    await flushPromises()
    await vi.waitFor(() => {
      expect(wrapper.find('tbody tr').exists()).toBe(true)
    })
    await wrapper.find('tbody tr').trigger('click')
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('Technical Radar')
    expect(wrapper.text()).toContain('AAPL')
    expect(wrapper.text()).toContain('breakout')
    expect(wrapper.text()).toContain('Confirmed')
    expect(wrapper.text()).toContain('ATR 14')
    expect(wrapper.text()).toContain('Why flagged')
    expect(wrapper.text()).toContain('Thread')
    expect(wrapper.text()).toContain('Action plan')
    expect(wrapper.text()).toContain('Reward / risk')
    expect(wrapper.text()).toContain('Events')
    expect(wrapper.text()).toContain('History')
    expect(wrapper.text()).toContain('Timeline')
    expect(wrapper.text()).toContain('Outcome stats')
    expect(wrapper.text()).toContain('Confirmed · Thread 2/2')
    expect(wrapper.text()).toContain('Signal date')
    expect(wrapper.text()).toContain('Context date')
    expect(wrapper.text()).toContain('Detected')
    expect(wrapper.text()).toContain('Recorded 2026-05-04 10:00 UTC')
    expect(wrapper.text()).toContain('Volatility is compressed, so a larger move may be brewing.')
    expect(wrapper.text()).toContain('Primary AVWAP is anchored to 52-week High.')
    expect(wrapper.text()).toContain('AVWAP')
    expect(wrapper.text()).toContain('52-week high')
    expect(wrapper.text()).toContain('All Time High')
    expect(wrapper.text()).toContain('Inside Keltner')
    expect(wrapper.text()).toContain('#1')
    expect(wrapper.text()).toContain('#2')
    expect(wrapper.text()).not.toContain('1777953600.00')
    expect(wrapper.text()).not.toContain('1771822800.00')
    expect(wrapper.text()).not.toContain('week52_high')
    expect(wrapper.text()).not.toContain('all_time_high')

    await wrapper.find('.detail-head .action-btn.primary').trigger('click')
    expect(radarStore.pendingChartDetection).toEqual({
      detectionId: 42,
      instrumentId: 7,
      instrumentSymbol: 'AAPL',
      timeframe: 'D1',
    })
    expect(push).toHaveBeenCalledWith({
      path: '/chart/AAPL',
    })
  })

  it('locks radar interactions while a scan is running', async () => {
    const runResponse = {
      id: 7,
      status: 'completed',
      timeframe: 'D1',
      universe_type: 'all',
      started_at: '2026-05-04T10:06:00Z',
      completed_at: '2026-05-04T10:06:02Z',
      evaluated_count: 12,
      detection_count: 3,
      error_summary: null,
      created_at: '2026-05-04T10:06:00Z',
      updated_at: '2026-05-04T10:06:02Z',
    }
    const pendingRun = deferred<typeof runResponse>()
    ;(api.post as ReturnType<typeof vi.fn>).mockImplementationOnce(() => pendingRun.promise)

    const wrapper = mount(RadarView, {
      global: {
        plugins: [createPinia()],
        stubs: {
          RadarDetailPreviewChart: radarDetailPreviewChartStub,
        },
      },
    })

    await flushPromises()
    await flushPromises()

    const runButton = wrapper.find('.action-btn.primary')
    await runButton.trigger('click')
    await nextTick()

    expect((api.post as ReturnType<typeof vi.fn>).mock.calls).toHaveLength(1)
    expect(wrapper.find('.radar-busy-overlay').exists()).toBe(true)
    expect(wrapper.find('.filter-select').attributes('disabled')).toBeDefined()
    expect(runButton.attributes('disabled')).toBeDefined()

    pendingRun.resolve(runResponse)

    await vi.waitFor(() => {
      expect(wrapper.find('.radar-busy-overlay').exists()).toBe(false)
    })
  })

  it('uses a compact detection list when horizontal space gets tight', async () => {
    window.innerWidth = 1040
    window.dispatchEvent(new Event('resize'))

    const wrapper = mount(RadarView, {
      global: {
        plugins: [createPinia()],
        stubs: {
          RadarDetailPreviewChart: radarDetailPreviewChartStub,
        },
      },
    })

    await flushPromises()
    await flushPromises()
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('AAPL')
    })

    expect(wrapper.find('.detections-card-list').exists()).toBe(true)
    expect(wrapper.find('.detections-table').exists()).toBe(false)
    expect(wrapper.text()).toContain('AAPL')
    expect(wrapper.text()).toContain('Breakout')
  })

  it('passes timeframe filters and executes radar workflows', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(RadarView, {
      global: {
        plugins: [pinia],
        stubs: {
          RadarDetailPreviewChart: radarDetailPreviewChartStub,
        },
      },
    })

    await flushPromises()
    await flushPromises()
    await vi.waitFor(() => {
      expect(wrapper.find('tbody tr').exists()).toBe(true)
    })

    const selects = wrapper.findAll('select.filter-select')
    await selects[1].setValue('H4')
    await flushPromises()

    expect(api.get).toHaveBeenCalledWith('/radar/runs', { limit: 5, timeframe: 'H4' })
    expect(api.get).toHaveBeenCalledWith('/radar/detections', {
      timeframe: 'H4',
      setup_type: undefined,
      state: undefined,
      symbol: undefined,
      min_score: 0.35,
      active_only: true,
    })

    await selects[3].setValue('breakout')
    await flushPromises()

    expect(api.get).toHaveBeenCalledWith('/radar/detections', {
      timeframe: 'H4',
      setup_type: 'breakout',
      state: undefined,
      symbol: undefined,
      min_score: 0.35,
      active_only: true,
    })

    await selects[4].setValue('confirmed')
    await flushPromises()

    expect(api.get).toHaveBeenCalledWith('/radar/detections', {
      timeframe: 'H4',
      setup_type: 'breakout',
      state: 'confirmed',
      symbol: undefined,
      min_score: 0.35,
      active_only: true,
    })

    const activeToggle = wrapper.find('input[type="checkbox"]')
    await activeToggle.setValue(false)
    await flushPromises()

    expect(api.get).toHaveBeenCalledWith('/radar/detections', {
      timeframe: 'H4',
      setup_type: 'breakout',
      state: 'confirmed',
      symbol: undefined,
      min_score: 0.35,
      active_only: false,
    })

    await vi.waitFor(() => {
      expect(wrapper.find('tbody tr').exists()).toBe(true)
    })
    await wrapper.find('tbody tr').trigger('click')
    await flushPromises()
    ;(api.post as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({
        id: 91,
        instrument_id: 7,
        instrument_symbol: 'AAPL',
        instrument_currency: 'USD',
        condition: 'crosses_above',
        threshold_price: 112.9,
        reference_price: 112.9,
        price_field: 'close',
        within_percent: null,
        status: 'active',
        repeat: false,
        show_projection: false,
        notes: 'Radar breakout',
        triggered_at: null,
        trigger_count: 0,
        last_known_price: null,
        created_at: '2026-05-04T10:00:00Z',
        updated_at: '2026-05-04T10:00:00Z',
      })
      .mockResolvedValueOnce({
        watchlist_id: 9,
        watchlist_name: 'Priority',
        item_id: 17,
      })

    const actionButtons = wrapper.findAll('.detail-actions-row .action-btn')
    await actionButtons[0].trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Created crosses above alert on AAPL.')
    await actionButtons[1].trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith('/radar/detections/42/actions/create-price-alert', {})
    expect(api.post).toHaveBeenCalledWith('/radar/detections/42/actions/add-to-watchlist', {})
    expect(wrapper.text()).toContain('Added to Priority.')
  })

  it('runs scans against a selected ETF holdings basket', async () => {
    const wrapper = mount(RadarView, {
      global: {
        plugins: [createPinia()],
        stubs: {
          RadarDetailPreviewChart: radarDetailPreviewChartStub,
        },
      },
    })

    await flushPromises()
    await flushPromises()

    const runButton = wrapper.find('.radar-actions .action-btn.primary')
    const selects = wrapper.findAll('select.filter-select')
    await selects[2].setValue('basket')
    await flushPromises()
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('SPY holdings')
    })

    expect(runButton.attributes('disabled')).toBeDefined()

    const withBasketSelect = wrapper.findAll('select.filter-select')
    await withBasketSelect[3].setValue('44')
    await flushPromises()
    await vi.waitFor(() => {
      expect(runButton.attributes('disabled')).toBeUndefined()
    })

    await runButton.trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith('/radar/run', {
      timeframe: 'D1',
      universe_type: 'basket',
      universe_filter: { basket_id: 44 },
    })
  })
})
