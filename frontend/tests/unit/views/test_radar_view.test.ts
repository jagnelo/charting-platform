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
  score: 0.82,
  observed_at: '2026-05-04T10:00:00Z',
  signal_at: '2026-05-04T10:00:00Z',
  context_at: '2026-05-01T10:00:00Z',
  fresh_until: '2026-05-09T10:00:00Z',
  thread_id: 11,
  thread_event_index: 2,
  key_level_price: 112.5,
  summary: 'AAPL is showing a breakout setup.',
  invalidation_hint: 'Invalidate if price falls back below 110.',
  score_factors: { normalized_score: 0.82, overlap_confluence: 0.5 },
}

const detailDetection = {
  ...summaryDetection,
  evidence: {
    overlays: [{ kind: 'zone', label: 'Resistance zone', price_low: 110, price_high: 112 }],
    metrics: { close: 113.2, atr_14: 2.1, signal_time: 1777953600, context_time: 1771822800 },
    structures: [],
  },
  thread: {
    id: 11,
    instrument_id: 7,
    timeframe: 'D1',
    context_role: 'resistance',
    reference_price: 112.5,
    current_setup_type: 'breakout',
    started_at: '2026-04-28T10:00:00Z',
    last_seen_at: '2026-05-04T10:00:00Z',
    detection_count: 2,
  },
  thread_history: [
    {
      id: 40,
      setup_type: 'approaching_resistance',
      score: 0.71,
      observed_at: '2026-05-01T10:00:00Z',
      signal_at: '2026-05-01T10:00:00Z',
      context_at: '2026-04-30T10:00:00Z',
      thread_event_index: 1,
      key_level_price: 112.1,
      summary: 'AAPL approached resistance.',
      invalidation_hint: 'Close above 113.',
    },
    {
      id: 42,
      setup_type: 'breakout',
      score: 0.82,
      observed_at: '2026-05-04T10:00:00Z',
      signal_at: '2026-05-04T10:00:00Z',
      context_at: '2026-05-01T10:00:00Z',
      thread_event_index: 2,
      key_level_price: 112.5,
      summary: 'AAPL is showing a breakout setup.',
      invalidation_hint: 'Invalidate if price falls back below 110.',
    },
  ],
}

describe('RadarView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
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
      if (path === '/radar/detections') return Promise.resolve([summaryDetection])
      if (path === '/radar/detections/42') return Promise.resolve(detailDetection)
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
      },
    })

    await flushPromises()
    await flushPromises()
    await wrapper.find('tbody tr').trigger('click')
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('Technical Radar')
    expect(wrapper.text()).toContain('AAPL')
    expect(wrapper.text()).toContain('breakout')
    expect(wrapper.text()).toContain('atr 14')
    expect(wrapper.text()).toContain('Setup thread')
    expect(wrapper.text()).toContain('Events')
    expect(wrapper.text()).toContain('Thread 2/2')
    expect(wrapper.text()).toContain('Signal date')
    expect(wrapper.text()).toContain('Context date')
    expect(wrapper.text()).toContain('#1')
    expect(wrapper.text()).toContain('#2')
    expect(wrapper.text()).not.toContain('1777953600.00')
    expect(wrapper.text()).not.toContain('1771822800.00')

    await wrapper.find('.detail-head .action-btn.primary').trigger('click')
    expect(radarStore.pendingChartDetection).toEqual({
      detectionId: 42,
      instrumentId: 7,
      instrumentSymbol: 'AAPL',
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
})
