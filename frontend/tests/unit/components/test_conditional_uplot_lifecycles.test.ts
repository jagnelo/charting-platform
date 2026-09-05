import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import uPlot from 'uplot'
import StudySeriesUPlot from '@/components/workstation/StudySeriesUPlot.vue'
import StudyHistogramUPlot from '@/components/workstation/StudyHistogramUPlot.vue'
import StudyRangeUPlot from '@/components/workstation/StudyRangeUPlot.vue'
import StudyBarsUPlot from '@/components/workstation/StudyBarsUPlot.vue'
import BreadthHistoryUPlot from '@/components/workstation/BreadthHistoryUPlot.vue'
import BenchmarkFamilyBreadthHistoryUPlot from '@/components/workstation/BenchmarkFamilyBreadthHistoryUPlot.vue'
import BenchmarkFamilyConcentrationHistoryUPlot from '@/components/workstation/BenchmarkFamilyConcentrationHistoryUPlot.vue'
import BenchmarkFamilyConcentrationMetricsHistoryUPlot from '@/components/workstation/BenchmarkFamilyConcentrationMetricsHistoryUPlot.vue'
import BenchmarkFamilyRatioHistoryUPlot from '@/components/workstation/BenchmarkFamilyRatioHistoryUPlot.vue'
import CrossFamilyRankingHistoryUPlot from '@/components/workstation/CrossFamilyRankingHistoryUPlot.vue'
import GenericBreadthHistoryUPlot from '@/components/workstation/GenericBreadthHistoryUPlot.vue'

class ResizeObserverMock {
  constructor(_callback: () => void) {}
  observe() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverMock)

const cases = [
  { name: 'series', component: StudySeriesUPlot, valid: { name: 'Series', timestamps: ['2026-01-01', '2026-01-02'], values: [1, 2] }, invalid: { timestamps: ['not-a-date'], values: [Number.NaN] } },
  { name: 'histogram', component: StudyHistogramUPlot, valid: { name: 'Histogram', bins: [{ start: 0, end: 1, count: 2 }] }, invalid: { bins: [] } },
  { name: 'range', component: StudyRangeUPlot, valid: { name: 'Range', timestamps: ['2026-01-01', '2026-01-02'], lower: [1, 2], upper: [2, 3] }, invalid: { timestamps: ['not-a-date'], lower: [1], upper: [2] } },
  { name: 'bars', component: StudyBarsUPlot, valid: { name: 'Bars', labels: ['A', 'B'], values: [1, -1] }, invalid: { labels: [], values: [] } },
  { name: 'breadth history', component: BreadthHistoryUPlot, valid: { history: { group_key: 'sp500-sectors', points: [{ timestamp: '2026-01-01', above_ma: { ma20: 0.5, ma50: 0.4, ma200: 0.3 }, coverage: {} }] } }, invalid: { history: { group_key: 'sp500-sectors', points: [{ timestamp: 'not-a-date', above_ma: { ma20: Number.NaN, ma50: 0.4, ma200: 0.3 }, coverage: {} }] } } },
  { name: 'benchmark family breadth history', component: BenchmarkFamilyBreadthHistoryUPlot, valid: { history: { family_key: 'sp500', official_index_symbol: 'SPX', timeframe: 'D1', adjustment: 'split_adjusted', limit: 500, roles: [{ role: 'cap_weight', symbol: 'SPY', label: 'Cap weight', verification_state: 'verified', available: true, points: [{ timestamp: '2026-01-01', above_ma: { ma20: 0.5 }, coverage: { ma20: 1 } }], exclusions: [] }], exclusions: [] } }, invalid: { history: { family_key: 'sp500', official_index_symbol: 'SPX', timeframe: 'D1', adjustment: 'split_adjusted', limit: 500, roles: [{ role: 'cap_weight', symbol: 'SPY', label: 'Cap weight', verification_state: 'verified', available: true, points: [{ timestamp: 'not-a-date', above_ma: { ma20: Number.NaN }, coverage: {} }], exclusions: [] }], exclusions: [] } } },
  { name: 'benchmark family concentration history', component: BenchmarkFamilyConcentrationHistoryUPlot, valid: { history: { family_key: 'sp500', official_index_symbol: 'SPX', timeframe: 'D1', adjustment: 'split_adjusted', as_of: null, rank_period: '1M', top_n: 10, limit: 500, roles: [{ role: 'cap_weight', symbol: 'SPY', label: 'Cap weight', verification_state: 'verified', available: true, membership_semantics: 'point_in_time_snapshot', points: [{ timestamp: '2026-01-01', snapshot_id: 1, composition_date: '2026-01-01', known_at: '2026-01-01T00:00:00Z', membership_version: 1, membership_semantics: 'point_in_time_snapshot', weight_method: 'reported', reported_weight_coverage: 1, top_n_weight: 0.3, hhi: 0.1, effective_constituents: 100, eligible_count: 100, covered_count: 100, excluded_count: 0, coverage: 1, mean_return: 0.01, median_return: 0.01, dispersion: 0.02, warnings: [] }], exclusions: [] }], exclusions: [] } }, invalid: { history: { family_key: 'sp500', official_index_symbol: 'SPX', timeframe: 'D1', adjustment: 'split_adjusted', as_of: null, rank_period: '1M', top_n: 10, limit: 500, roles: [{ role: 'cap_weight', symbol: 'SPY', label: 'Cap weight', verification_state: 'verified', available: true, membership_semantics: null, points: [{ timestamp: 'not-a-date', snapshot_id: null, composition_date: null, known_at: null, membership_version: 1, membership_semantics: null, weight_method: 'unavailable', reported_weight_coverage: null, top_n_weight: null, hhi: null, effective_constituents: null, eligible_count: 0, covered_count: 0, excluded_count: 0, coverage: 0, mean_return: null, median_return: null, dispersion: Number.NaN, warnings: [] }], exclusions: [] }], exclusions: [] } } },
  { name: 'benchmark family concentration metrics history', component: BenchmarkFamilyConcentrationMetricsHistoryUPlot, valid: { history: { family_key: 'sp500', official_index_symbol: 'SPX', timeframe: 'D1', adjustment: 'split_adjusted', as_of: null, rank_period: '1M', top_n: 10, limit: 500, roles: [{ role: 'cap_weight', symbol: 'SPY', label: 'Cap weight', verification_state: 'verified', available: true, membership_semantics: 'point_in_time_snapshot', points: [{ timestamp: '2026-01-01', snapshot_id: 1, composition_date: '2026-01-01', known_at: '2026-01-01T00:00:00Z', membership_version: 1, membership_semantics: 'point_in_time_snapshot', weight_method: 'reported', reported_weight_coverage: 1, top_n_weight: 0.3, hhi: 0.1, effective_constituents: 100, eligible_count: 100, covered_count: 100, excluded_count: 0, coverage: 1, mean_return: 0.01, median_return: 0.01, dispersion: 0.02, warnings: [] }], exclusions: [] }], exclusions: [] } }, invalid: { history: { family_key: 'sp500', official_index_symbol: 'SPX', timeframe: 'D1', adjustment: 'split_adjusted', as_of: null, rank_period: '1M', top_n: 10, limit: 500, roles: [{ role: 'cap_weight', symbol: 'SPY', label: 'Cap weight', verification_state: 'verified', available: true, membership_semantics: null, points: [{ timestamp: 'not-a-date', snapshot_id: null, composition_date: null, known_at: null, membership_version: 1, membership_semantics: null, weight_method: 'unavailable', reported_weight_coverage: null, top_n_weight: null, hhi: null, effective_constituents: null, eligible_count: 0, covered_count: 0, excluded_count: 0, coverage: 0, mean_return: null, median_return: null, dispersion: null, warnings: [] }], exclusions: [] }], exclusions: [] } } },
  { name: 'benchmark family ratio history', component: BenchmarkFamilyRatioHistoryUPlot, valid: { ratios: { family_key: 'sp500', official_index_symbol: 'SPX', timeframe: 'D1', adjustment: 'split_adjusted', ratios: [{ role: 'equal_weight', symbol: 'RSP', benchmark_role: 'cap_weight', benchmark: 'SPY', points: [{ timestamp: '2026-01-01', value: 1.02 }], coverage: 1, warnings: [] }], exclusions: [] } }, invalid: { ratios: { family_key: 'sp500', official_index_symbol: 'SPX', timeframe: 'D1', adjustment: 'split_adjusted', ratios: [{ role: 'equal_weight', symbol: 'RSP', benchmark_role: 'cap_weight', benchmark: 'SPY', points: [{ timestamp: 'not-a-date', value: Number.NaN }], coverage: 0, warnings: [] }], exclusions: [] } } },
  { name: 'cross-family ranking history', component: CrossFamilyRankingHistoryUPlot, valid: { history: { timeframe: 'D1', adjustment: 'split_adjusted', rank_period: '1M', limit: 500, rows: [{ family_key: 'sp500', family_name: 'S&P 500', official_index_symbol: 'SPX', symbol: 'SPY', label: 'SPY', available: true, coverage: 1, points: [{ timestamp: '2026-01-01', rank: 1, performance: { '1M': 0.1 }, relative_performance: { '1M': 0.02 } }], warnings: [] }], exclusions: [] } }, invalid: { history: { timeframe: 'D1', adjustment: 'split_adjusted', rank_period: '1M', limit: 500, rows: [{ family_key: 'sp500', family_name: 'S&P 500', official_index_symbol: 'SPX', symbol: 'SPY', label: 'SPY', available: true, coverage: 1, points: [{ timestamp: 'not-a-date', rank: 1, performance: { '1M': 0.1 }, relative_performance: { '1M': Number.NaN } }], warnings: [] }], exclusions: [] } } },
  { name: 'generic breadth history', component: GenericBreadthHistoryUPlot, valid: { history: { definition_version: 1, definition_hash: 'hash', universe: {}, condition: {}, timeframe: 'D1', adjustment: 'split_adjusted', points: [{ timestamp: '2026-01-01', requested_count: 2, eligible_count: 2, pass_count: 1, excluded_count: 0, percentage: 0.5, coverage: 1, members: [], exclusions: [] }] } }, invalid: { history: { definition_version: 1, definition_hash: 'hash', universe: {}, condition: {}, timeframe: 'D1', adjustment: 'split_adjusted', points: [{ timestamp: 'not-a-date', requested_count: 2, eligible_count: 0, pass_count: 0, excluded_count: 2, percentage: Number.NaN, coverage: 0, members: [], exclusions: [] }] } } },
] as const

describe('conditional uPlot lifecycle contracts', () => {
  beforeEach(() => vi.mocked(uPlot).mockClear())

  it.each(cases)('$name renders its initial conditional chart host', async ({ component, valid }) => {
    const wrapper = mount(component, { props: valid as any })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1))
    expect(wrapper.element.querySelector('[class$="__host"]')).not.toBeNull()
  })

  it.each(cases)('$name destroys its chart when the conditional data disappears', async ({ component, valid, invalid }) => {
    const wrapper = mount(component, { props: valid as any })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1))
    const chart = vi.mocked(uPlot).mock.results[0]?.value
    await wrapper.setProps(invalid as any)
    await vi.waitFor(() => expect(chart.destroy).toHaveBeenCalledTimes(1))
    expect(wrapper.get('[role="status"]').attributes('aria-live')).toBe('polite')
    expect(wrapper.get('[role="status"]').attributes('aria-atomic')).toBe('true')
    wrapper.unmount()
  })

  it('rejects malformed range timestamps before creating uPlot', async () => {
    const wrapper = mount(StudyRangeUPlot, {
      props: { name: 'Range', timestamps: ['not-a-date'], lower: [1], upper: [2] },
    })
    await nextTick()
    expect(vi.mocked(uPlot)).not.toHaveBeenCalled()
    expect(wrapper.get('[role="status"]').text()).toContain('no aligned finite bounds')
  })

  it('refreshes a histogram current marker without recreating its uPlot instance', async () => {
    const wrapper = mount(StudyHistogramUPlot, {
      props: { name: 'Histogram', bins: [{ start: 0, end: 1, count: 2 }], current: 0.25 },
    })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1))
    const chart = vi.mocked(uPlot).mock.results[0]?.value
    chart.setData.mockClear()
    await wrapper.setProps({ current: 0.75 })
    await vi.waitFor(() => expect(chart.setData).toHaveBeenCalledTimes(1))
    expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('aligns benchmark-family role histories without forward-filling gaps', async () => {
    const wrapper = mount(BenchmarkFamilyBreadthHistoryUPlot, {
      props: {
        history: {
          family_key: 'sp500', official_index_symbol: 'SPX', timeframe: 'D1', adjustment: 'split_adjusted', limit: 500,
          roles: [
            { role: 'cap_weight', symbol: 'SPY', label: 'Cap weight', verification_state: 'verified', available: true, points: [{ timestamp: '2026-01-01', above_ma: { ma20: 0.5 }, coverage: { ma20: 1 } }, { timestamp: '2026-01-02', above_ma: { ma20: 0.6 }, coverage: { ma20: 1 } }], exclusions: [] },
            { role: 'equal_weight', symbol: 'RSP', label: 'Equal weight', verification_state: 'verified', available: true, points: [{ timestamp: '2026-01-02', above_ma: { ma20: 0.4 }, coverage: { ma20: 1 } }], exclusions: [] },
          ], exclusions: [],
        },
      },
    })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1))
    const call = vi.mocked(uPlot).mock.calls[0] as any
    expect(call[1][0]).toHaveLength(2)
    expect(call[1][1]).toEqual([0.5, 0.6])
    expect(call[1][2]).toEqual([null, 0.4])
    wrapper.unmount()
  })

  it('aligns benchmark-family concentration dispersion without forward-filling gaps', async () => {
    const wrapper = mount(BenchmarkFamilyConcentrationHistoryUPlot, {
      props: {
        history: {
          family_key: 'sp500', official_index_symbol: 'SPX', timeframe: 'D1', adjustment: 'split_adjusted', as_of: null, rank_period: '1M', top_n: 10, limit: 500,
          roles: [
            { role: 'cap_weight', symbol: 'SPY', label: 'Cap weight', verification_state: 'verified', available: true, membership_semantics: 'point_in_time_snapshot', points: [{ timestamp: '2026-01-01', snapshot_id: 1, composition_date: '2026-01-01', known_at: '2026-01-01T00:00:00Z', membership_version: 1, membership_semantics: 'point_in_time_snapshot', weight_method: 'reported', reported_weight_coverage: 1, top_n_weight: 0.3, hhi: 0.1, effective_constituents: 100, eligible_count: 100, covered_count: 100, excluded_count: 0, coverage: 1, mean_return: 0.01, median_return: 0.01, dispersion: 0.02, warnings: [] }, { timestamp: '2026-01-02', snapshot_id: 1, composition_date: '2026-01-01', known_at: '2026-01-01T00:00:00Z', membership_version: 1, membership_semantics: 'point_in_time_snapshot', weight_method: 'reported', reported_weight_coverage: 1, top_n_weight: 0.3, hhi: 0.1, effective_constituents: 100, eligible_count: 100, covered_count: 100, excluded_count: 0, coverage: 1, mean_return: 0.02, median_return: 0.02, dispersion: 0.04, warnings: [] }], exclusions: [] },
            { role: 'equal_weight', symbol: 'RSP', label: 'Equal weight', verification_state: 'verified', available: true, membership_semantics: 'point_in_time_snapshot', points: [{ timestamp: '2026-01-02', snapshot_id: 2, composition_date: '2026-01-01', known_at: '2026-01-01T00:00:00Z', membership_version: 1, membership_semantics: 'point_in_time_snapshot', weight_method: 'reported', reported_weight_coverage: 1, top_n_weight: 0.2, hhi: 0.1, effective_constituents: 100, eligible_count: 100, covered_count: 100, excluded_count: 0, coverage: 1, mean_return: 0.02, median_return: 0.02, dispersion: 0.03, warnings: [] }], exclusions: [] },
          ], exclusions: [],
        },
      },
    })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1))
    const call = vi.mocked(uPlot).mock.calls[0] as any
    expect(call[1][0]).toHaveLength(2)
    expect(call[1][1]).toEqual([0.02, 0.04])
    expect(call[1][2]).toEqual([null, 0.03])
    wrapper.unmount()
  })

  it('aligns benchmark-family concentration metrics without forward-filling gaps', async () => {
    const wrapper = mount(BenchmarkFamilyConcentrationMetricsHistoryUPlot, {
      props: {
        history: {
          family_key: 'sp500', official_index_symbol: 'SPX', timeframe: 'D1', adjustment: 'split_adjusted', as_of: null, rank_period: '1M', top_n: 10, limit: 500,
          roles: [
            { role: 'cap_weight', symbol: 'SPY', label: 'Cap weight', verification_state: 'verified', available: true, membership_semantics: 'point_in_time_snapshot', points: [{ timestamp: '2026-01-01', snapshot_id: 1, composition_date: '2026-01-01', known_at: '2026-01-01T00:00:00Z', membership_version: 1, membership_semantics: 'point_in_time_snapshot', weight_method: 'reported', reported_weight_coverage: 1, top_n_weight: 0.3, hhi: 0.1, effective_constituents: 100, eligible_count: 100, covered_count: 100, excluded_count: 0, coverage: 1, mean_return: 0.01, median_return: 0.01, dispersion: 0.02, warnings: [] }, { timestamp: '2026-01-02', snapshot_id: 1, composition_date: '2026-01-01', known_at: '2026-01-01T00:00:00Z', membership_version: 1, membership_semantics: 'point_in_time_snapshot', weight_method: 'reported', reported_weight_coverage: 1, top_n_weight: 0.31, hhi: 0.11, effective_constituents: 100, eligible_count: 100, covered_count: 100, excluded_count: 0, coverage: 1, mean_return: 0.02, median_return: 0.02, dispersion: 0.04, warnings: [] }], exclusions: [] },
            { role: 'equal_weight', symbol: 'RSP', label: 'Equal weight', verification_state: 'verified', available: true, membership_semantics: 'point_in_time_snapshot', points: [{ timestamp: '2026-01-02', snapshot_id: 2, composition_date: '2026-01-01', known_at: '2026-01-01T00:00:00Z', membership_version: 1, membership_semantics: 'point_in_time_snapshot', weight_method: 'reported', reported_weight_coverage: 1, top_n_weight: 0.2, hhi: 0.09, effective_constituents: 100, eligible_count: 100, covered_count: 100, excluded_count: 0, coverage: 1, mean_return: 0.02, median_return: 0.02, dispersion: 0.03, warnings: [] }], exclusions: [] },
          ], exclusions: [],
        },
      },
    })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1))
    const call = vi.mocked(uPlot).mock.calls[0] as any
    expect(call[1][0]).toHaveLength(2)
    expect(call[1][1]).toEqual([0.3, 0.31])
    expect(call[1][2]).toEqual([0.1, 0.11])
    expect(call[1][3]).toEqual([null, 0.2])
    expect(call[1][4]).toEqual([null, 0.09])
    wrapper.unmount()
  })

  it('aligns cross-family relative performance without forward-filling gaps', async () => {
    const wrapper = mount(CrossFamilyRankingHistoryUPlot, {
      props: { history: { timeframe: 'D1', adjustment: 'split_adjusted', rank_period: '1M', limit: 500, rows: [
        { family_key: 'sp500', family_name: 'S&P 500', official_index_symbol: 'SPX', symbol: 'SPY', label: 'SPY', available: true, coverage: 1, points: [{ timestamp: '2026-01-01', rank: 1, performance: { '1M': 0.1 }, relative_performance: { '1M': 0.02 } }, { timestamp: '2026-01-02', rank: 1, performance: { '1M': 0.11 }, relative_performance: { '1M': 0.03 } }], warnings: [] },
        { family_key: 'nasdaq100', family_name: 'Nasdaq 100', official_index_symbol: 'NDX', symbol: 'QQQ', label: 'QQQ', available: true, coverage: 1, points: [{ timestamp: '2026-01-02', rank: 2, performance: { '1M': 0.09 }, relative_performance: { '1M': -0.01 } }], warnings: [] },
      ], exclusions: [] } },
    })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1))
    const call = vi.mocked(uPlot).mock.calls[0] as any
    expect(call[1][0]).toHaveLength(2)
    expect(call[1][1]).toEqual([0.02, 0.03])
    expect(call[1][2]).toEqual([null, -0.01])
    wrapper.unmount()
  })

  it('aligns family ratio histories without forward-filling gaps', async () => {
    const wrapper = mount(BenchmarkFamilyRatioHistoryUPlot, {
      props: {
        ratios: {
          family_key: 'sp500', official_index_symbol: 'SPX', timeframe: 'D1', adjustment: 'split_adjusted',
          ratios: [
            { role: 'equal_weight', symbol: 'RSP', benchmark_role: 'cap_weight', benchmark: 'SPY', points: [{ timestamp: '2026-01-01', value: 1.02 }, { timestamp: '2026-01-02', value: 1.03 }], coverage: 1, warnings: [] },
            { role: 'value', symbol: 'IVE', benchmark_role: 'cap_weight', benchmark: 'SPY', points: [{ timestamp: '2026-01-02', value: 0.99 }], coverage: 0.5, warnings: [] },
          ], exclusions: [],
        },
      },
    })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1))
    const call = vi.mocked(uPlot).mock.calls[0] as any
    expect(call[1][0]).toHaveLength(2)
    expect(call[1][1]).toEqual([1.02, 1.03])
    expect(call[1][2]).toEqual([null, 0.99])
    wrapper.unmount()
  })
})
