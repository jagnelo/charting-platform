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

async function flushPromises() {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
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
  fresh_until: '2026-05-09T10:00:00Z',
  key_level_price: 112.5,
  summary: 'AAPL is showing a breakout setup.',
  invalidation_hint: 'Invalidate if price falls back below 110.',
  score_factors: { normalized_score: 0.82, overlap_confluence: 0.5 },
}

const detailDetection = {
  ...summaryDetection,
  evidence: {
    overlays: [{ kind: 'zone', label: 'Resistance zone', price_low: 110, price_high: 112 }],
    metrics: { close: 113.2, atr_14: 2.1 },
    structures: [],
  },
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

    await wrapper.find('.detail-head .action-btn.primary').trigger('click')
    expect(push).toHaveBeenCalledWith({
      path: '/chart/AAPL',
      query: { radarDetectionId: '42' },
    })
  })
})
