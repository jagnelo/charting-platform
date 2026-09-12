import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost, loadWatchlistSources, loadWatchlists, resolveWatchlistSource, createWatchlist, addItem, loadUserSettings, toggleFollowedSource, togglePinnedSource, invalidateQueries } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn(), loadWatchlistSources: vi.fn(), loadWatchlists: vi.fn(), resolveWatchlistSource: vi.fn(), createWatchlist: vi.fn(), addItem: vi.fn(), loadUserSettings: vi.fn(), toggleFollowedSource: vi.fn(), togglePinnedSource: vi.fn(), invalidateQueries: vi.fn() }))
const defaultSources = vi.hoisted(() => [{ source_id: 'market-group:sp500', source_kind: 'index_membership', name: 'S&P 500', locked: true, can_follow: true, can_clone: true, can_edit_membership: false, member_count: 2, provenance: {} }])
const sourceState = vi.hoisted(() => ({
  sources: defaultSources,
  watchlists: [],
  loading: false,
  error: '',
}))

vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: apiPost, delete: vi.fn() } }))
vi.mock('@tanstack/vue-query', () => ({ useQueryClient: () => ({ invalidateQueries }) }))
vi.mock('@/stores/watchlist', () => ({ useWatchlistStore: () => ({ watchlistSources: sourceState.sources, watchlistSourcesLoading: sourceState.loading, watchlistSourcesError: sourceState.error, watchlists: sourceState.watchlists, loadWatchlistSources, loadWatchlists, resolveWatchlistSource, createWatchlist, addItem }) }))
vi.mock('@/stores/userSettings', () => ({ useUserSettingsStore: () => ({ followedSourceIds: [], pinnedSourceIds: [], loadSettings: loadUserSettings, toggleFollowedSource, togglePinnedSource }) }))

import MarketMapTool from '@/components/workstation/MarketMapTool.vue'

const response = {
  source: sourceState.sources[0],
  group_by: 'sector_industry', period: '1D', period_start: '2026-08-06T00:00:00Z', period_end: '2026-08-07T00:00:00Z', timeframe: 'D1', adjustment: 'split_adjusted', area_metric: 'market_cap', color_metric: 'return', membership_version: 'market-group:sp500:current', calculation_version: 'market-map-v1', cache_key: 'cache', freshness: 'current', freshness_detail: { requested: 2, current: 2, stale: 0, other: 0 }, requested_count: 2, evaluated_count: 2, coverage: 1, warnings: [], exclusions: [], nodes: [{ node_id: 'root', level: 'root', label: 'All members', group_path: [], member_count: 2, covered_count: 2, area_total: 150, color_value: 0.1, coverage: 1, aggregation_method: 'area_weighted_mean', warnings: [] }, { node_id: 'group:Technology', parent_id: 'root', level: 'sector', label: 'Technology', group_path: ['Technology'], member_count: 2, covered_count: 2, area_total: 150, color_value: 0.1, coverage: 1, aggregation_method: 'area_weighted_mean', warnings: [] }],
  cache_hit: true, cached_at: '2026-08-07T15:30:00Z', cells: [{ instrument_id: 1, symbol: 'NVDA', name: 'NVIDIA', sector: 'Technology', industry: 'Semiconductors', classification_provenance: { kind: 'point_in_time_profile_snapshot', provider_name: 'controlled-fixture', observed_at: '2026-08-07T00:00:00Z' }, group_path: ['Technology', 'Semiconductors'], area_value: 100, color_value: 0.1, return_value: 0.1, observation_time: '2026-08-07T00:00:00Z', coverage: 1, warnings: [] }, { instrument_id: 2, symbol: 'MSFT', name: 'Microsoft', sector: 'Technology', industry: 'Software', group_path: ['Technology', 'Software'], area_value: 50, color_value: -0.02, return_value: -0.02, observation_time: '2026-08-07T00:00:00Z', coverage: 1, warnings: [] }],
}

describe('MarketMapTool', () => {
  beforeEach(() => {
    apiPost.mockReset()
    apiGet.mockReset()
    loadWatchlistSources.mockReset()
    loadWatchlists.mockReset()
    resolveWatchlistSource.mockReset()
    createWatchlist.mockReset()
    addItem.mockReset()
    loadUserSettings.mockReset()
    toggleFollowedSource.mockReset()
    togglePinnedSource.mockReset()
    invalidateQueries.mockReset()
    sourceState.sources = [...defaultSources]
    sourceState.watchlists = []
    apiPost.mockResolvedValue(response)
    apiGet.mockResolvedValue([])
  })

  it('persists follow and pin preferences without changing locked source membership', async () => {
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    expect(loadUserSettings).toHaveBeenCalled()
    await wrapper.get('[aria-label="Follow S&P 500"]').trigger('click')
    await wrapper.get('[aria-label="Pin S&P 500"]').trigger('click')

    expect(toggleFollowedSource).toHaveBeenCalledWith('market-group:sp500')
    expect(togglePinnedSource).toHaveBeenCalledWith('market-group:sp500')
    expect(wrapper.text()).toContain('Locked source')
    expect(wrapper.find('[aria-label="Market Map universe"]').element.value).toBe('market-group:sp500')
  })

  it('persists a selected subset as a durable locked explicit source with parent lineage', async () => {
    apiPost.mockImplementation((path: string) => path === '/watchlists/sources/explicit'
      ? Promise.resolve({
          ...sourceState.sources[0],
          source_id: 'explicit-list:selection-test',
          source_kind: 'explicit',
          name: 'Saved technology leaders',
          locked: true,
          member_count: 1,
        })
      : Promise.resolve(response))
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    await wrapper.get('.market-map-tool__tile').trigger('click')
    await wrapper.get('[aria-label="Market Map locked source name"]').setValue('Saved technology leaders')
    await wrapper.get('[aria-label="Save selected members as locked source"]').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/watchlists/sources/explicit', {
      name: 'Saved technology leaders',
      instrument_ids: [1],
      parent_source_id: 'market-group:sp500',
      parent_membership_version: 'market-group:sp500:current',
    })
    expect(loadWatchlistSources).toHaveBeenCalled()
    expect(wrapper.text()).toContain('saved as locked source Saved technology leaders')
  })

  it('does not continue locked-source publication after the Market Map unmounts', async () => {
    let resolveSave: ((value: unknown) => void) | undefined
    const saveResult = new Promise(resolve => { resolveSave = resolve })
    apiPost.mockImplementation((path: string) => path === '/watchlists/sources/explicit' ? saveResult : Promise.resolve(response))

    const wrapper = mount(MarketMapTool)
    await flushPromises()
    await wrapper.get('.market-map-tool__tile').trigger('click')
    await wrapper.get('[aria-label="Market Map locked source name"]').setValue('Detached source')
    await wrapper.get('[aria-label="Save selected members as locked source"]').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/watchlists/sources/explicit', expect.objectContaining({ name: 'Detached source' }))
    const sourceLoadsBeforeUnmount = loadWatchlistSources.mock.calls.length
    wrapper.unmount()

    resolveSave?.({ ...sourceState.sources[0], source_id: 'explicit-list:detached', name: 'Detached source', source_kind: 'explicit' })
    await flushPromises()

    expect(loadWatchlistSources).toHaveBeenCalledTimes(sourceLoadsBeforeUnmount)
  })

  it('does not continue selected-member watchlist publication after the Market Map unmounts', async () => {
    let resolveCreate: ((value: unknown) => void) | undefined
    const createResult = new Promise(resolve => { resolveCreate = resolve })
    createWatchlist.mockReturnValue(createResult)

    const wrapper = mount(MarketMapTool)
    await flushPromises()
    await wrapper.get('.market-map-tool__tile').trigger('click')
    await wrapper.get('[aria-label="Market Map new watchlist name"]').setValue('Detached selection')
    await wrapper.get('.market-map-tool__selection-actions button').trigger('click')
    await flushPromises()

    expect(createWatchlist).toHaveBeenCalledWith('Detached selection')
    wrapper.unmount()

    resolveCreate?.({ id: 14, name: 'Detached selection', is_managed: false, is_locked: false, items: [] })
    await flushPromises()

    expect(addItem).not.toHaveBeenCalled()
  })

  it('clones the complete canonical locked source with membership provenance', async () => {
    resolveWatchlistSource.mockResolvedValue({
      source: { ...sourceState.sources[0], composition_date: '2026-08-07', membership_version: 'sp500:2026-08-07' },
      members: [
        { instrument_id: 1, position: 0, relationship_type: 'constituent', effective_at: '2026-08-07T00:00:00Z', known_at: '2026-08-07T00:00:00Z' },
        { instrument_id: 2, position: 1, relationship_type: 'constituent', effective_at: '2026-08-07T00:00:00Z', known_at: '2026-08-07T00:00:00Z' },
      ],
      exclusions: [],
    })
    createWatchlist.mockResolvedValue({ id: 11, name: 'S&P 500 snapshot 2026-08-07', is_managed: false, is_locked: false, items: [] })
    addItem.mockResolvedValue({ id: 110, instrument_id: 1 })
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    await wrapper.get('[aria-label="Clone S&P 500 snapshot"]').trigger('click')
    await flushPromises()

    expect(resolveWatchlistSource).toHaveBeenCalledWith('market-group:sp500', null)
    expect(createWatchlist).toHaveBeenCalledWith(
      'S&P 500 snapshot 2026-08-07',
      expect.stringContaining('membership_version=sp500:2026-08-07'),
    )
    expect(addItem).toHaveBeenCalledWith(11, 1)
    expect(addItem).toHaveBeenCalledWith(11, 2)
    expect(wrapper.get('[aria-label="Market Map source preferences"] [role="status"]').text()).toContain('2/2 members cloned')
  })

  it('stops sequential source clone writes after the Market Map unmounts', async () => {
    resolveWatchlistSource.mockResolvedValue({
      source: { ...sourceState.sources[0], membership_version: 'sp500:teardown' },
      members: [
        { instrument_id: 1, position: 0, relationship_type: 'constituent' },
        { instrument_id: 2, position: 1, relationship_type: 'constituent' },
      ],
      exclusions: [],
    })
    createWatchlist.mockResolvedValue({ id: 13, name: 'S&P 500 snapshot teardown', is_managed: false, is_locked: false, items: [] })
    let resolveFirstAdd: ((value: unknown) => void) | undefined
    const firstAdd = new Promise(resolve => { resolveFirstAdd = resolve })
    addItem.mockReturnValue(firstAdd)

    const wrapper = mount(MarketMapTool)
    await flushPromises()
    await wrapper.get('[aria-label="Clone S&P 500 snapshot"]').trigger('click')
    await flushPromises()

    expect(addItem).toHaveBeenCalledWith(13, 1)
    wrapper.unmount()

    resolveFirstAdd?.({ id: 131, instrument_id: 1 })
    await flushPromises()

    expect(addItem).toHaveBeenCalledTimes(1)
  })

  it('invalidates a pending source clone when the active universe changes', async () => {
    const previousSources = sourceState.sources
    sourceState.sources = [
      ...previousSources,
      { ...previousSources[0], source_id: 'watchlist:7', source_kind: 'personal' as const, name: 'Personal candidates', locked: false },
    ]
    let resolveMembers: ((value: unknown) => void) | undefined
    const membersResult = new Promise(resolve => { resolveMembers = resolve })
    resolveWatchlistSource.mockReturnValue(membersResult)

    const wrapper = mount(MarketMapTool)
    await flushPromises()
    await wrapper.get('[aria-label="Clone S&P 500 snapshot"]').trigger('click')
    await flushPromises()

    await wrapper.get('[aria-label="Market Map universe"]').setValue('watchlist:7')
    await flushPromises()
    resolveMembers?.({ source: sourceState.sources[0], members: [{ instrument_id: 1 }], exclusions: [] })
    await flushPromises()

    expect(createWatchlist).not.toHaveBeenCalled()
    expect(wrapper.get('[aria-label="Clone Personal candidates snapshot"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
    sourceState.sources = previousSources
  })

  it('keeps failed clone members retryable without hiding the partial copy', async () => {
    resolveWatchlistSource.mockResolvedValue({
      source: { ...sourceState.sources[0], membership_version: 'sp500:retry' },
      members: [
        { instrument_id: 1, position: 0, relationship_type: 'constituent' },
        { instrument_id: 2, position: 1, relationship_type: 'constituent' },
      ],
      exclusions: [],
    })
    createWatchlist.mockResolvedValue({ id: 12, name: 'S&P 500 snapshot retry', is_managed: false, is_locked: false, items: [] })
    addItem.mockResolvedValueOnce({ id: 121, instrument_id: 1 }).mockResolvedValueOnce(null)
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    await wrapper.get('[aria-label="Clone S&P 500 snapshot"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[aria-label="Market Map source preferences"] [role="status"]').text()).toContain('1/2 members cloned')
    expect(wrapper.get('[aria-label="Retry failed source clone members"]')).toBeTruthy()

    addItem.mockResolvedValueOnce({ id: 122, instrument_id: 2 })
    await wrapper.get('[aria-label="Retry failed source clone members"]').trigger('click')
    await flushPromises()

    expect(addItem).toHaveBeenCalledTimes(3)
    expect(wrapper.get('[aria-label="Market Map source preferences"] [role="status"]').text()).toContain('2/2 members cloned')
    expect(wrapper.find('[aria-label="Retry failed source clone members"]').exists()).toBe(false)
  })

  it('groups index, ETF, and editable sources while using one locked-source map contract', async () => {
    const previousSources = sourceState.sources
    sourceState.sources = [
      ...previousSources,
      {
        ...previousSources[0],
        source_id: 'benchmark-family:sp500:cap_weight',
        source_kind: 'index_membership',
        name: 'S&P 500 — Cap weight constituents',
        member_count: 500,
        provenance: { availability: 'available', membership_semantics: 'etf_proxy_holdings' },
      },
      {
        ...previousSources[0],
        source_id: 'etf-holdings:SPY',
        source_kind: 'etf_holdings',
        name: 'SPY holdings',
        member_count: 500,
        provenance: { availability: 'available', membership_semantics: 'etf_proxy_holdings' },
      },
      {
        ...previousSources[0],
        source_id: 'watchlist:7',
        source_kind: 'personal',
        name: 'My candidates',
        locked: false,
        member_count: 12,
        provenance: { availability: 'available' },
      },
    ]
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'benchmark-family:sp500:cap_weight' } } })
    await flushPromises()

    const universe = wrapper.get('[aria-label="Market Map universe"]')
    expect(universe.find('optgroup[label="Index and managed universes"] option[value="benchmark-family:sp500:cap_weight"]').exists()).toBe(true)
    expect(universe.find('optgroup[label="ETF holdings"] option[value="etf-holdings:SPY"]').exists()).toBe(true)
    expect(universe.find('optgroup[label="Personal watchlists"] option[value="watchlist:7"]').exists()).toBe(true)
    expect(wrapper.find('.market-map-tool__source-kind').text()).toContain('Index and managed universes · 500 members')
    expect(apiPost).toHaveBeenCalledWith('/analysis/market-map', expect.objectContaining({ source_id: 'benchmark-family:sp500:cap_weight' }))
    expect(wrapper.text()).toContain('Locked source')

    wrapper.unmount()
    sourceState.sources = previousSources
  })

  it('surfaces canonical benchmark role readiness beside the Market Map', async () => {
    const previousSources = sourceState.sources
    sourceState.sources = [{
      ...previousSources[0],
      source_id: 'benchmark-family:sp500:cap_weight',
      source_kind: 'index_membership',
      name: 'S&P 500 — Cap weight constituents',
      member_count: 500,
      provenance: { availability: 'available', membership_semantics: 'etf_proxy_holdings' },
    }]
    apiGet.mockImplementation((path: string) => path === '/analysis/benchmark-families/sp500/coverage'
      ? Promise.resolve({
          family_key: 'sp500', name: 'S&P 500', official_index_symbol: 'SPX', official_index_name: 'S&P 500 Index', as_of: '2026-07-01T00:00:00Z', membership_version: 42, universe_provenance: { coverage_semantics: 'role_independent_dated_holdings_snapshots', membership_semantics: 'official_index_when_entitled_or_explicitly_labelled_proxy', point_in_time: true }, coverage: 0.25, freshness: 'coverage_limited', exclusions: [{ code: 'unresolved_member', message: 'Member could not be resolved.' }],
          roles: [
            { role: 'cap_weight', symbol: 'SPY', label: 'Cap weight', available: true, status: 'available', holdings_route_provider: 'sec', holdings_route_status: 'configured', history_route_status: 'sec_filing_reconstruction', history_route_provider: 'sec', history_route_policy: 'latest_sec_filing_report_on_or_before_requested_date', history_route_source_url: 'https://data.sec.gov/submissions/CIK0001067839.json', holdings_refresh_status: 'partial', holdings_refresh_last_checked_at: '2026-07-03T12:00:00Z', holdings_refresh_last_failure_at: '2026-07-04T12:00:00Z', holdings_refresh_composition_date: '2026-06-30', holdings_refresh_failure_reason: 'issuer endpoint unavailable', snapshots: [{ snapshot_id: 7, composition_date: '2026-06-30', as_of_date: '2026-07-01', known_at: '2026-07-02T12:00:00Z', timing_provenance: { composition_date: 'provider_reported', as_of_date: 'provider_reported', known_at: 'provider_reported', published_at: 'provider_reported' }, provenance: 'issuer snapshot', source_provider: 'sec', source_quality: 'issuer_disclosed', completeness_status: 'partial', row_count: 101, resolved_count: 21, unresolved_count: 80 }], continuity_status: 'gapped', continuity_gap_count: 1, continuity_max_interval_days: 76, continuity_gaps: [{ from_date: '2026-03-31', to_date: '2026-06-15', interval_days: 76 }], continuity_snapshot_limit_reached: false, entitlement_status: 'verified', entitlement_provider: 'sec', entitlement_live_probe_status: 'passed', entitlement_revision: 7, entitlement_effective_at: '2026-07-01T00:00:00Z', entitlement_review_due_at: '2026-10-01T00:00:00Z', member_bar_history: { status: 'partial', placeholder_member_count: 80, unresolved_member_count: 0, timeframes: [{ timeframe: 'D1', member_count: 101, covered_member_count: 21, coverage_percent: 20.8, analysis_ready_member_count: 21, analysis_ready_percent: 20.8, bar_count: 1000, provider_member_count: 21, derived_member_count: 1, provider_only_member_count: 20, derived_only_member_count: 0, mixed_member_count: 1, provider_bar_count: 1000, derived_bar_count: 1, source_lineage: 'provider_and_derived', adjustment_provenance: { mode: 'split_adjusted', source_kind: 'mixed_provider_and_derived', factor_status: 'rebuildable_provider_factors', factor_version: 'afv1-family', factor_versioned_member_count: 21, factor_opaque_member_count: 0, factor_unavailable_member_count: 0, contract_version: 1 }, oldest: '2025-01-01T00:00:00Z', newest: '2026-06-30T00:00:00Z', required_bar_count: 252 }, { timeframe: 'W1', member_count: 101, covered_member_count: 0, coverage_percent: 0, analysis_ready_member_count: 0, analysis_ready_percent: 0, bar_count: 0, required_bar_count: 52 }, { timeframe: 'MN', member_count: 101, covered_member_count: 0, coverage_percent: 0, analysis_ready_member_count: 0, analysis_ready_percent: 0, bar_count: 0, required_bar_count: 24 }] }, point_in_time_supported: true, member_count: 101, placeholder_member_count: 80, weighted_member_count: 101, classification_status: 'partial', classified_member_count: 21, weights_status: 'ready', history_ready: false, composite_readiness_status: 'partial', composite_readiness_reasons: ['member_bar_history_incomplete'] },
            { role: 'equal_weight', symbol: 'RSP', label: 'Equal weight', available: true, status: 'no_snapshot', member_bar_history: { status: 'no_snapshot', placeholder_member_count: 0, timeframes: [] }, point_in_time_supported: false, member_count: 0, placeholder_member_count: 0, weighted_member_count: 0, weights_status: 'unavailable', classified_member_count: 0, classification_status: 'unavailable', history_ready: false, composite_readiness_status: 'pending', composite_readiness_reasons: ['no_dated_holdings'] },
            { role: 'value', symbol: null, label: 'Value', available: false, status: 'mapping_unavailable', member_bar_history: { status: 'unavailable', placeholder_member_count: 0, timeframes: [] }, point_in_time_supported: false, member_count: 0, placeholder_member_count: 0, weighted_member_count: 0, weights_status: 'unavailable', classified_member_count: 0, classification_status: 'unavailable', history_ready: false, composite_readiness_status: 'unavailable', composite_readiness_reasons: ['benchmark_role_mapping_unavailable'] },
            { role: 'growth', symbol: null, label: 'Growth', available: false, status: 'mapping_unavailable', member_bar_history: { status: 'unavailable', placeholder_member_count: 0, timeframes: [] }, point_in_time_supported: false, member_count: 0, placeholder_member_count: 0, weighted_member_count: 0, weights_status: 'unavailable', classified_member_count: 0, classification_status: 'unavailable', history_ready: false, composite_readiness_status: 'unavailable', composite_readiness_reasons: ['benchmark_role_mapping_unavailable'] },
          ],
        }).then(response => ({
          ...response,
          roles: response.roles.map((role, index) => index === 0 ? { ...role, holdings_route_adapter_key: 'sec_issuer_holdings', entitlement_capabilities: { history: 'partial', holdings: 'supported', weights: 'supported', classification: 'pending' }, observed_cadence_status: 'observed_cadence', observed_cadence_sample_count: 1, observed_cadence_median_interval_days: 76, observed_cadence_min_interval_days: 76, observed_cadence_max_interval_days: 76 } : role),
        }))
      : Promise.resolve([]))

    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'benchmark-family:sp500:cap_weight' } } })
    await flushPromises()

    const readiness = wrapper.get('[aria-label="Benchmark family canonical readiness"]')
    expect(readiness.text()).toContain('25% of roles have dated holdings')
    expect(readiness.text()).toContain('Cap weight (SPY)')
    expect(readiness.text()).toContain('21/101 D1 analysis-ready')
    expect(readiness.text()).toContain('History: D1 21/101 ready · 21 covered · 1000 bars · floor 252 · range 2025-01-01 → 2026-06-30 · W1 0/101 ready · 0 covered · 0 bars · floor 52 · MN 0/101 ready · 0 covered · 0 bars · floor 24')
    expect(readiness.text()).toContain('Route: configured · sec · adapter sec_issuer_holdings · Refresh: partial')
    expect(readiness.text()).toContain('Refresh: partial · checked 2026-07-03 · reason issuer endpoint unavailable')
    expect(readiness.text()).toContain('Refresh: partial · checked 2026-07-03 · reason issuer endpoint unavailable · failed 2026-07-04 · composition 2026-06-30')
    expect(readiness.text()).toContain('Members: 101 · Weighted: 101 (ready) · Classified: 21 (partial) · Point-in-time: supported')
    expect(readiness.get('[aria-label="Benchmark family canonical identity evidence"]').text()).toContain('Cap weight SPY · verification not reported · adapter unmapped · snapshot 2026-06-30 · as-of 2026-07-01 · known 2026-07-02 · provenance issuer snapshot · source quality issuer_disclosed · completeness partial · rows 101 · resolved 21 · unresolved 80 · continuity gapped · 1 gap · max 76d · intervals 2026-03-31 to 2026-06-15 (76d) · observed cadence measured · 1 interval · median 76d · min 76d · max 76d · capabilities classification=pending, history=partial, holdings=supported, weights=supported')
    expect(readiness.get('[aria-label="Benchmark family canonical identity evidence"]').text()).toContain('Canonical family provenance: sp500 · S&P 500 · official index SPX (S&P 500 Index) · as-of 2026-07-01 · membership version 42 · coverage 25% · freshness coverage_limited · universe coverage semantics=role_independent_dated_holdings_snapshots · membership semantics=official_index_when_entitled_or_explicitly_labelled_proxy · point in time=true · exclusions 1 · unresolved_member')
    expect(readiness.get('[aria-label="Benchmark family canonical identity evidence"]').text()).toContain('Cap weight SPY · verification not reported · adapter unmapped · snapshot 2026-06-30 · as-of 2026-07-01 · known 2026-07-02 · provenance issuer snapshot · source quality issuer_disclosed · completeness partial · rows 101 · resolved 21 · unresolved 80 · continuity gapped · 1 gap · max 76d · intervals 2026-03-31 to 2026-06-15 (76d) · observed cadence measured · 1 interval · median 76d · min 76d · max 76d · capabilities classification=pending, history=partial, holdings=supported, weights=supported')
    expect(readiness.get('[aria-label="Benchmark family canonical identity evidence"]').text()).toContain('availability available · status available · members 101 · placeholders 80 · unresolved 0 · weighted 101 (ready) · classified 21 (partial) · point-in-time supported · history incomplete · bars D1 21/101 analysis-ready · 21 covered · 1000 bars · floor 252 · lineage provider and derived · members provider 21, derived 1 · member split provider-only 20, derived-only 0, mixed 1')
    expect(readiness.get('[aria-label="Benchmark family canonical identity evidence"]').text()).toContain('factors rebuildable provider factors (afv1-family) · members versioned 21, opaque 0, unavailable 0 · range 2025-01-01 to 2026-06-30')
    expect(readiness.get('[aria-label="Benchmark family canonical identity evidence"]').text()).toContain('history route sec filing reconstruction · sec · latest sec filing report on or before requested date · source https://data.sec.gov/submissions/CIK0001067839.json')
    expect(readiness.text()).toContain('Entitlement: verified · sec · probe passed')
    expect(readiness.text()).toContain('Entitlement: verified · sec · probe passed · rev 7 · effective 2026-07-01 · review due 2026-10-01')
    expect(readiness.text()).toContain('Latest disclosure: 2026-06-30 · as-of 2026-07-01 · known 2026-07-02 · 21/101 resolved · sec · timing as of date=provider reported, composition date=provider reported, known at=provider reported, published at=provider reported')
    expect(readiness.text()).toContain('Observed continuity: gapped · 1 gap')
    expect(readiness.get('[aria-label="Benchmark family canonical identity evidence"]').text()).toContain('observed cadence measured · 1 interval · median 76d · min 76d · max 76d')
    expect(readiness.text()).toContain('member_bar_history_incomplete')
    expect(readiness.text()).toContain('Value')
    expect(apiGet).toHaveBeenCalledWith('/analysis/benchmark-families/sp500/coverage', { limit: 256 })

    wrapper.unmount()
    sourceState.sources = previousSources
  })

  it('explicitly bootstraps an arbitrary ETF into the locked source catalog', async () => {
    const previousSources = sourceState.sources
    const pendingEtf = {
      ...previousSources[0],
      source_id: 'etf-holdings:QQQ',
      source_kind: 'etf_holdings' as const,
      name: 'QQQ holdings',
      member_count: 0,
      provenance: { availability: 'profile_not_loaded' },
    }
    sourceState.sources = [...previousSources, pendingEtf]
    apiPost.mockImplementation((path: string) => path === '/etf-holdings/QQQ/bootstrap'
      ? Promise.resolve({ profile: { symbol: 'QQQ' }, latest_snapshot: null, refresh_succeeded: false, message: 'No local holdings snapshot yet.' })
      : Promise.resolve(response))

    const wrapper = mount(MarketMapTool)
    await flushPromises()
    await wrapper.get('[aria-label="ETF universe symbol"]').setValue('qqq')
    await wrapper.get('[aria-label="Load ETF constituent universe"]').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/etf-holdings/QQQ/bootstrap', {})
    expect(wrapper.get('[aria-label="Market Map universe"]').element.value).toBe('etf-holdings:QQQ')
    expect(wrapper.find('[aria-label="Add ETF constituent universe"] [role="status"]').text()).toContain('membership is pending hydration')

    wrapper.unmount()
    sourceState.sources = previousSources
  })

  it('does not continue an ETF bootstrap after the Market Map unmounts', async () => {
    const previousSources = sourceState.sources
    const pendingEtf = {
      ...previousSources[0],
      source_id: 'etf-holdings:QQQ',
      source_kind: 'etf_holdings' as const,
      name: 'QQQ holdings',
      member_count: 0,
      provenance: { availability: 'profile_not_loaded' },
    }
    sourceState.sources = [...previousSources, pendingEtf]
    let resolveBootstrap: ((value: unknown) => void) | undefined
    const bootstrapResult = new Promise(resolve => { resolveBootstrap = resolve })
    apiPost.mockImplementation((path: string) => path === '/etf-holdings/QQQ/bootstrap'
      ? bootstrapResult
      : Promise.resolve(response))

    const wrapper = mount(MarketMapTool)
    await flushPromises()
    await wrapper.get('[aria-label="ETF universe symbol"]').setValue('qqq')
    await wrapper.get('[aria-label="Load ETF constituent universe"]').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/etf-holdings/QQQ/bootstrap', {})
    const sourceLoadsBeforeUnmount = loadWatchlistSources.mock.calls.length
    wrapper.unmount()

    resolveBootstrap?.({ profile: { symbol: 'QQQ' }, latest_snapshot: null, refresh_succeeded: false, message: 'No local holdings snapshot yet.' })
    await flushPromises()

    expect(loadWatchlistSources).toHaveBeenCalledTimes(sourceLoadsBeforeUnmount)
    sourceState.sources = previousSources
  })

  it('rejects malformed ETF symbols before any bootstrap request', async () => {
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    await wrapper.get('[aria-label="ETF universe symbol"]').setValue('not a ticker')
    await wrapper.get('[aria-label="Load ETF constituent universe"]').trigger('click')
    await flushPromises()

    expect(apiPost.mock.calls.some(([path]) => String(path).includes('/etf-holdings/'))).toBe(false)
    expect(wrapper.get('[aria-label="Add ETF constituent universe"] [role="alert"]').text()).toContain('canonical ETF symbol')
  })

  it('shows source history readiness and queues an explicit refresh without changing membership', async () => {
    const historyStatus = {
      source_id: 'market-group:sp500',
      source_kind: 'index_membership',
      name: 'S&P 500',
      locked: true,
      membership_version: 'v1',
      max_instruments: 5000,
      available_instrument_count: 2,
      selected_instrument_count: 2,
      limited: false,
      excluded_count: 0,
      effective_at: '2026-01-01T00:00:00Z',
      known_at: '2026-01-02T00:00:00Z',
      timing_provenance: { effective_at: 'provider_reported', known_at: 'provider_reported' },
      published_at: '2026-01-03T00:00:00Z',
      cadence: 'month_end',
      parser_version: 'sec-v2',
      source_identifier: 'issuer-feed',
      overall_status: 'partial',
      analysis_ready: false,
      analysis_ready_status: 'partial',
      member_disposition: { canonical: 1, placeholder: 2, unresolved: 3, excluded: 4 },
      timeframes: [{ timeframe: 'D1', member_count: 2, covered_member_count: 1, coverage_percent: 50, analysis_ready_member_count: 0, analysis_ready_percent: 0, required_bar_count: 252, bar_count: 3, provider_member_count: 1, derived_member_count: 1, provider_only_member_count: 0, derived_only_member_count: 0, mixed_member_count: 1, provider_bar_count: 2, derived_bar_count: 1, source_lineage: 'provider_and_derived', adjustment_provenance: { mode: 'split_adjusted', source_kind: 'mixed_provider_and_derived', factor_status: 'mixed_provider_native_opaque_and_inherited_from_canonical_d1', factor_version: null, contract_version: 1 }, oldest: '2025-01-01T00:00:00Z', newest: '2026-06-30T00:00:00Z', in_progress_count: 0, complete_count: 1, failed_count: 0, pending_count: 1 }],
    }
    const historyRun = { id: 42, source_ids: ['market-group:sp500'], timeframes: ['D1'], max_instruments: 5000, available_instrument_count: 2, selected_instrument_count: 2, queued_count: 1, already_queued_count: 1, status: 'running', cancel_requested: false, progress: { complete: 1, in_progress: 1 }, created_at: '2026-08-19T00:00:00Z', updated_at: '2026-08-19T00:00:00Z' }
    apiGet.mockImplementation((path: string) => path.includes('/history-status/') ? Promise.resolve(historyStatus) : path.includes('/history-refresh-runs/') ? Promise.resolve(historyRun) : Promise.resolve([]))
    apiPost.mockImplementation((path: string) => {
      if (path === '/analysis/market-map') return Promise.resolve(response)
      if (path === '/watchlists/sources/history-refresh') return Promise.resolve({ run_id: 42, source_ids: ['market-group:sp500'], timeframes: ['D1'], max_instruments: 5000, available_instrument_count: 2, selected_instrument_count: 2, limited: false, queued: 1, already_queued: 1, queue_unavailable: false })
      return Promise.resolve({ ...historyRun, status: 'canceled', cancel_requested: true, progress: { ...historyRun.progress, status: 'canceled' } })
    })

    const wrapper = mount(MarketMapTool)
    await flushPromises()

    expect(wrapper.find('[aria-label="Market Map history readiness"]').text()).toContain('partial')
    expect(wrapper.find('[aria-label="Market Map history readiness"]').text()).toContain('analysis partial')
    expect(wrapper.find('[aria-label="Market Map history readiness"]').text()).toContain('1/2 D1 members covered')
    expect(wrapper.find('[aria-label="Market Map history readiness"]').text()).toContain('analysis-ready 0/2 (floor 252)')
    expect(wrapper.find('[aria-label="Market Map history readiness"]').text()).toContain('3 bars · range 2025-01-01 → 2026-06-30')
    expect(wrapper.get('[aria-label="Market Map history member disposition evidence"]').text()).toContain('canonical 1, excluded 4, placeholder 2, unresolved 3')
    expect(wrapper.get('[aria-label="Market Map history membership timing evidence"]').text()).toContain('effective 2026-01-01T00:00:00Z · known 2026-01-02T00:00:00Z · published 2026-01-03T00:00:00Z · cadence month_end · parser sec-v2 · source issuer-feed · provenance effective at=provider reported, known at=provider reported')
    expect(wrapper.get('[aria-label="Market Map history adjustment provenance evidence"]').text()).toContain('D1 split adjusted · source mixed provider and derived · factor mixed provider native opaque and inherited from canonical d1 · factor version not reported')
    expect(wrapper.get('[aria-label="Market Map history lineage evidence"]').text()).toContain('D1 provider and derived · members provider 1, derived 1 · provider-only 0, derived-only 0, mixed 1 · bars provider 2, derived 1')
    await wrapper.get('[aria-label="Refresh Market Map history"]').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/watchlists/sources/history-refresh', {
      source_ids: ['market-group:sp500'],
      timeframes: ['D1'],
      max_instruments: 5000,
    })
    expect(wrapper.find('[aria-label="Market Map history readiness"]').text()).toContain('2 history jobs queued')
    expect(wrapper.find('[aria-label="Market Map history readiness"]').text()).toContain('Run 42 · running · 1/2')
    await wrapper.get('[aria-label="Cancel Market Map history refresh"]').trigger('click')
    await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('/watchlists/history-refresh-runs/42/cancel', {})
    expect(wrapper.find('[aria-label="Market Map history readiness"]').text()).toContain('History refresh canceled')
    expect(wrapper.text()).toContain('Locked source')
  })

  it('bounds system-source history readiness and refresh to a custom map end', async () => {
    const historyStatus = {
      source_id: 'market-group:sp500',
      source_kind: 'index_membership',
      name: 'S&P 500',
      locked: true,
      membership_version: 'v1',
      as_of: '2026-08-07T23:59:59Z',
      max_instruments: 5000,
      available_instrument_count: 2,
      selected_instrument_count: 2,
      limited: false,
      excluded_count: 0,
      overall_status: 'ready',
      timeframes: [{ timeframe: 'D1', member_count: 2, covered_member_count: 2, coverage_percent: 100, bar_count: 6, in_progress_count: 0, complete_count: 2, failed_count: 0, pending_count: 0 }],
    }
    apiGet.mockImplementation((path: string) => path.includes('/history-status/') ? Promise.resolve(historyStatus) : Promise.resolve([]))
    apiPost.mockImplementation((path: string) => path === '/analysis/market-map'
      ? Promise.resolve(response)
      : Promise.resolve({ run_id: 77, source_ids: ['market-group:sp500'], timeframes: ['D1'], as_of: '2026-08-07T23:59:59Z', max_instruments: 5000, available_instrument_count: 2, selected_instrument_count: 2, limited: false, queued: 2, already_queued: 0, queue_unavailable: false }))

    const wrapper = mount(MarketMapTool, {
      props: { configuration: { source_id: 'market-group:sp500', period: 'CUSTOM', start_date: '2026-08-01', end_date: '2026-08-07' } },
    })
    await flushPromises()

    const statusCall = apiGet.mock.calls.find(([path]) => String(path).includes('/history-status/'))
    expect(statusCall?.[1]).toEqual({ timeframes: ['D1'], max_instruments: 5000, as_of: '2026-08-07T23:59:59Z' })
    expect(apiPost.mock.calls.find(([path]) => path === '/analysis/market-map')?.[1]).toEqual(expect.objectContaining({ end: '2026-08-07T23:59:59Z' }))

    await wrapper.get('[aria-label="Refresh Market Map history"]').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/watchlists/sources/history-refresh', {
      source_ids: ['market-group:sp500'],
      timeframes: ['D1'],
      max_instruments: 5000,
      as_of: '2026-08-07T23:59:59Z',
    })
  })

  it('does not publish a late history refresh after the Market Map unmounts', async () => {
    let resolveRefresh: ((value: unknown) => void) | undefined
    const refreshResult = new Promise(resolve => { resolveRefresh = resolve })
    apiPost.mockImplementation((path: string) => {
      if (path === '/analysis/market-map') return Promise.resolve(response)
      if (path === '/watchlists/sources/history-refresh') return refreshResult
      return Promise.resolve({})
    })

    const wrapper = mount(MarketMapTool)
    await flushPromises()
    await wrapper.get('[aria-label="Refresh Market Map history"]').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/watchlists/sources/history-refresh', {
      source_ids: ['market-group:sp500'],
      timeframes: ['D1'],
      max_instruments: 5000,
    })
    wrapper.unmount()

    resolveRefresh?.({ run_id: 42, source_ids: ['market-group:sp500'], timeframes: ['D1'], max_instruments: 5000, available_instrument_count: 2, selected_instrument_count: 2, limited: false, queued: 2, already_queued: 0, queue_unavailable: false })
    await flushPromises()

    expect(apiGet.mock.calls.some(([path]) => String(path).includes('/history-refresh-runs/42'))).toBe(false)
  })

  it('ignores stale history readiness responses after the source changes', async () => {
    const previousSources = sourceState.sources
    sourceState.sources = [
      { ...previousSources[0], source_id: 'market-group:sp500', name: 'S&P 500', source_kind: 'index_membership' },
      { ...previousSources[0], source_id: 'watchlist:7', name: 'Personal candidates', source_kind: 'personal', locked: false },
    ]
    let resolveStale: ((value: unknown) => void) | undefined
    const staleResponse = new Promise(resolve => { resolveStale = resolve })
    const currentStatus = {
      source_id: 'watchlist:7',
      source_kind: 'personal',
      name: 'Personal candidates',
      locked: false,
      membership_version: 'watchlist:7:v2',
      max_instruments: 5000,
      available_instrument_count: 1,
      selected_instrument_count: 1,
      limited: false,
      excluded_count: 0,
      overall_status: 'ready',
      analysis_ready: true,
      analysis_ready_status: 'ready',
      timeframes: [{ timeframe: 'D1', member_count: 1, covered_member_count: 1, coverage_percent: 100, analysis_ready_member_count: 1, analysis_ready_percent: 100, required_bar_count: 252, bar_count: 252, in_progress_count: 0, complete_count: 1, failed_count: 0, pending_count: 0 }],
    }
    apiGet.mockImplementation((path: string) => {
      if (path.includes('/history-status/') && (path.includes('market-group%3Asp500') || path.includes('market-group:sp500'))) return staleResponse
      if (path.includes('/history-status/') && (path.includes('watchlist%3A7') || path.includes('watchlist:7'))) return Promise.resolve(currentStatus)
      return Promise.resolve([])
    })

    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500' } } })
    await flushPromises()
    await wrapper.get('[aria-label="Market Map universe"]').setValue('watchlist:7')
    await flushPromises()

    expect(wrapper.get('[aria-label="Market Map history readiness"]').text()).toContain('analysis ready')

    resolveStale?.({
      source_id: 'market-group:sp500',
      source_kind: 'index_membership',
      name: 'S&P 500',
      locked: true,
      membership_version: 'sp500:v1',
      max_instruments: 5000,
      available_instrument_count: 1,
      selected_instrument_count: 1,
      limited: false,
      excluded_count: 0,
      overall_status: 'partial',
      analysis_ready: false,
      analysis_ready_status: 'partial',
      timeframes: [{ timeframe: 'D1', member_count: 1, covered_member_count: 0, coverage_percent: 0, analysis_ready_member_count: 0, analysis_ready_percent: 0, required_bar_count: 252, bar_count: 0, in_progress_count: 0, complete_count: 0, failed_count: 0, pending_count: 1 }],
    })
    await flushPromises()

    expect(wrapper.get('[aria-label="Market Map history readiness"]').text()).toContain('analysis ready')
    expect(wrapper.get('[aria-label="Market Map history readiness"]').text()).not.toContain('analysis partial')
    expect(wrapper.get('[aria-label="Market Map history readiness"]').text()).not.toContain('S&P 500')
    wrapper.unmount()
    sourceState.sources = previousSources
  })

  it('ignores stale benchmark coverage responses after the historical cutoff changes', async () => {
    const previousSources = sourceState.sources
    sourceState.sources = [{
      ...previousSources[0],
      source_id: 'benchmark-family:sp500:cap_weight',
      source_kind: 'index_membership',
      name: 'S&P 500 — Cap weight constituents',
      provenance: { availability: 'available' },
    }]
    let resolveStale: ((value: unknown) => void) | undefined
    const staleResponse = new Promise(resolve => { resolveStale = resolve })
    const currentResponse = {
      family_key: 'sp500',
      name: 'Current S&P 500 coverage',
      official_index_symbol: 'SPX',
      official_index_name: 'S&P 500 Index',
      as_of: '2026-08-07T23:59:59Z',
      membership_version: 2,
      universe_provenance: {},
      coverage: 0.5,
      roles: [],
      exclusions: [],
      freshness: 'coverage_limited',
    }
    apiGet.mockImplementation((path: string, params?: Record<string, unknown>) => {
      if (path === '/analysis/benchmark-families/sp500/coverage') {
        return params?.as_of ? Promise.resolve(currentResponse) : staleResponse
      }
      return Promise.resolve([])
    })

    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'benchmark-family:sp500:cap_weight' } } })
    await flushPromises()
    await wrapper.get('[aria-label="Market Map period"]').setValue('CUSTOM')
    await wrapper.get('[aria-label="Market Map custom end date"]').setValue('2026-08-07')
    await flushPromises()

    expect(wrapper.get('[aria-label="Benchmark family canonical readiness"]').text()).toContain('Current S&P 500 coverage')
    resolveStale?.({
      ...currentResponse,
      name: 'Stale S&P 500 coverage',
      as_of: null,
      membership_version: 1,
    })
    await flushPromises()

    expect(wrapper.get('[aria-label="Benchmark family canonical readiness"]').text()).toContain('Current S&P 500 coverage')
    expect(wrapper.get('[aria-label="Benchmark family canonical readiness"]').text()).not.toContain('Stale S&P 500 coverage')
    wrapper.unmount()
    sourceState.sources = previousSources
  })

  it('keeps unmapped family legs unavailable but lets mapped pending sources remain followable', async () => {
    const previousSources = sourceState.sources
    const pendingSource = {
      ...previousSources[0],
      source_id: 'benchmark-family:sp500:value-pending',
      source_kind: 'index_membership' as const,
      name: 'S&P 500 — Value pending',
      member_count: 0,
      provenance: { availability: 'holdings_snapshot_not_loaded' },
    }
    sourceState.sources = [
      ...previousSources,
      pendingSource,
      {
        ...previousSources[0],
        source_id: 'benchmark-family:sp500:value',
        source_kind: 'index_membership',
        name: 'S&P 500 — Value',
        provenance: { availability: 'unavailable' },
      },
    ]
    apiPost.mockResolvedValue({
      ...response,
      source: pendingSource,
      requested_count: 0,
      evaluated_count: 0,
      coverage: 0,
      color_coverage: 0,
      area_coverage: 0,
      nodes: [],
      cells: [],
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: pendingSource.source_id } } })
    await flushPromises()

    const pendingOption = wrapper.find(`option[value="${pendingSource.source_id}"]`)
    expect(pendingOption.attributes('disabled')).toBeUndefined()
    expect(pendingOption.text()).toContain('Pending membership')
    expect(wrapper.find('[aria-label="Market Map source preferences"] [role="status"]').text()).toContain('remains followable')
    await wrapper.get(`[aria-label="Follow ${pendingSource.name}"]`).trigger('click')
    expect(toggleFollowedSource).toHaveBeenCalledWith(pendingSource.source_id)

    const option = wrapper.find('option[value="benchmark-family:sp500:value"]')
    expect(option.attributes('disabled')).toBeDefined()
    expect(option.text()).toContain('Unavailable')

    wrapper.unmount()
    sourceState.sources = previousSources
  })

  it('loads a locked source, renders tiles, persists controls, and publishes a selected symbol', async () => {
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/analysis/market-map', expect.objectContaining({ source_id: 'market-group:sp500', group_by: 'sector_industry' }))
    expect(wrapper.text()).toContain('Locked source')
    expect(wrapper.text()).toContain('Cached result')
    expect(wrapper.text()).toContain('Combined 100%')
    expect(wrapper.text()).toContain('Colour 100%')
    expect(wrapper.text()).toContain('Area 100%')
    expect(wrapper.text()).toContain('NVDA')
    expect(wrapper.text()).not.toContain('Choose a managed index/ETF universe')
    expect(wrapper.findAll('.market-map-tool__tile')).toHaveLength(2)

    await wrapper.get('select[aria-label="Market Map grouping"]').setValue('sector')
    await flushPromises()
    expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual(expect.objectContaining({ group_by: 'sector' }))

    await wrapper.get('select[aria-label="Market Map timeframe"]').setValue('W1')
    await flushPromises()
    expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual(expect.objectContaining({ timeframe: 'W1' }))
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()
    expect(apiPost).toHaveBeenLastCalledWith('/analysis/market-map', expect.objectContaining({ timeframe: 'W1' }))

    await wrapper.get('.market-map-tool__tile').trigger('click')
    expect(wrapper.emitted('select')).toEqual([['NVDA', 1]])
    await wrapper.get('.market-map-tool__tile').trigger('mouseenter')
    expect(wrapper.find('.market-map-tool__hover').text()).toContain('NVDA')
    expect(wrapper.find('.market-map-tool__hover').text()).toContain('Classification snapshot · controlled-fixture · observed 2026-08-07')
    await wrapper.findAll('.market-map-tool__tile')[1].trigger('click', { shiftKey: true })
    expect(wrapper.findAll('.market-map-tool__tile--selected')).toHaveLength(2)
    expect(wrapper.emitted('select')).toEqual([['NVDA', 1], ['MSFT', 2]])
    await wrapper.get('[aria-label="Open selected members in chart"]').trigger('click')
    expect(wrapper.emitted('select')).toEqual([['NVDA', 1], ['MSFT', 2], ['NVDA', 1]])
    await wrapper.get('[aria-label="Compare selected members in chart"]').trigger('click')
    expect(wrapper.emitted('compare')).toEqual([[['NVDA', 'MSFT']]])
    await wrapper.get('[aria-label="Open selected members in relative strength"]').trigger('click')
    expect(wrapper.emitted('ratio')).toEqual([[['NVDA', 'MSFT']]])

    await wrapper.get('select[aria-label="Market Map sort order"]').setValue('symbol_asc')
    expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual(expect.objectContaining({ sort_by: 'symbol_asc' }))
  })

  it('switches a 10,000-member arbitrary universe to one canvas without proportional tile DOM', async () => {
    const largeResponse = {
      ...response,
      requested_count: 10000,
      evaluated_count: 10000,
      freshness_detail: { requested: 10000, current: 10000, stale: 0, other: 0 },
      cells: Array.from({ length: 10000 }, (_, index) => ({
        ...response.cells[0],
        instrument_id: index + 1,
        symbol: `SYM${index + 1}`,
        name: `Synthetic ${index + 1}`,
        group_path: ['Technology'],
        area_value: 1,
        color_value: index % 2 === 0 ? 0.01 : -0.01,
      })),
    }
    apiPost.mockResolvedValue(largeResponse)
    const context = {
      setTransform: vi.fn(),
      clearRect: vi.fn(),
      fillRect: vi.fn(),
      strokeRect: vi.fn(),
      fillText: vi.fn(),
      fillStyle: '',
      strokeStyle: '',
      lineWidth: 1,
      font: '',
      textAlign: 'center',
      textBaseline: 'middle',
    }
    const canvasContext = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context as unknown as CanvasRenderingContext2D)
    const previousAnimationFrame = window.requestAnimationFrame
    const previousCancelAnimationFrame = window.cancelAnimationFrame
    const animationFrames: FrameRequestCallback[] = []
    Object.defineProperty(window, 'requestAnimationFrame', { configurable: true, value: (callback: FrameRequestCallback) => { animationFrames.push(callback); return animationFrames.length } })
    Object.defineProperty(window, 'cancelAnimationFrame', { configurable: true, value: vi.fn() })

    const wrapper = mount(MarketMapTool)
    await flushPromises()
    await wrapper.vm.$nextTick()
    window.dispatchEvent(new Event('resize'))
    for (const callback of animationFrames.splice(0)) callback(0)

    expect(wrapper.find('canvas.market-map-tool__canvas-map').exists()).toBe(true)
    expect(wrapper.find('canvas.market-map-tool__canvas-map').attributes('aria-label')).toBe('10000 Market Map members')
    const canvasSummaryId = wrapper.find('canvas.market-map-tool__canvas-map').attributes('aria-describedby')
    expect(canvasSummaryId).toBeTruthy()
    expect(wrapper.find(`#${canvasSummaryId}`).text()).toContain('market map for 1D D1')
    expect(wrapper.find(`#${canvasSummaryId}`).text()).toContain('10000 visible members')
    expect(wrapper.findAll('.market-map-tool__tile')).toHaveLength(0)
    expect(wrapper.find('.market-map-tool__canvas-hint').text()).toContain('canvas rendering')
    expect(context.fillRect).toHaveBeenCalled()
    expect(Math.max(...context.strokeRect.mock.invocationCallOrder)).toBeGreaterThan(Math.max(...context.fillRect.mock.invocationCallOrder))

    const previousSetPointerCapture = HTMLElement.prototype.setPointerCapture
    const previousHasPointerCapture = HTMLElement.prototype.hasPointerCapture
    const previousReleasePointerCapture = HTMLElement.prototype.releasePointerCapture
    Object.defineProperty(HTMLElement.prototype, 'setPointerCapture', { configurable: true, value: vi.fn() })
    Object.defineProperty(HTMLElement.prototype, 'hasPointerCapture', { configurable: true, value: vi.fn(() => true) })
    Object.defineProperty(HTMLElement.prototype, 'releasePointerCapture', { configurable: true, value: vi.fn() })
    vi.spyOn(HTMLCanvasElement.prototype, 'getBoundingClientRect').mockReturnValue({ left: 0, top: 0, width: 100, height: 100, right: 100, bottom: 100, x: 0, y: 0, toJSON: () => ({}) } as DOMRect)
    await wrapper.get('[aria-label="Zoom in Market Map"]').trigger('click')
    const viewport = wrapper.get('.market-map-tool__tiles')
    await viewport.trigger('pointerdown', { pointerId: 1, clientX: 1, clientY: 1 })
    await viewport.trigger('pointermove', { pointerId: 1, clientX: 20, clientY: 20 })
    await viewport.trigger('pointerup', { pointerId: 1, clientX: 20, clientY: 20 })
    await wrapper.get('canvas.market-map-tool__canvas-map').trigger('click', { clientX: 0, clientY: 0 })
    expect(wrapper.emitted('select')).toBeUndefined()
    await wrapper.get('[aria-label="Find Large Market Map member"]').setValue('SYM1501')
    await wrapper.get('[aria-label="Find Large Market Map member"]').trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('select')).toEqual([['SYM1501', 1501]])

    wrapper.unmount()
    canvasContext.mockRestore()
    vi.restoreAllMocks()
    Object.defineProperty(HTMLElement.prototype, 'setPointerCapture', { configurable: true, value: previousSetPointerCapture })
    Object.defineProperty(HTMLElement.prototype, 'hasPointerCapture', { configurable: true, value: previousHasPointerCapture })
    Object.defineProperty(HTMLElement.prototype, 'releasePointerCapture', { configurable: true, value: previousReleasePointerCapture })
    Object.defineProperty(window, 'requestAnimationFrame', { configurable: true, value: previousAnimationFrame })
    Object.defineProperty(window, 'cancelAnimationFrame', { configurable: true, value: previousCancelAnimationFrame })
  })

  it('shows empty and failed map states without hiding the source controls', async () => {
    apiPost.mockRejectedValue(new Error('map unavailable'))
    const wrapper = mount(MarketMapTool)
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toContain('map unavailable')
    expect(wrapper.find('select[aria-label="Market Map universe"]').exists()).toBe(true)
  })

  it('drills hierarchy and controls the map viewport without changing the source', async () => {
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    await wrapper.find('.market-map-tool__nodes button').trigger('click')
    expect(wrapper.find('.market-map-tool__breadcrumbs').text()).toContain('Technology')
    expect(wrapper.find('.market-map-tool__tiles').exists()).toBe(true)

    await wrapper.get('[aria-label="Zoom in Market Map"]').trigger('click')
    expect(wrapper.find('[aria-live="polite"]').text()).toBe('125%')
    await wrapper.get('[aria-label="Reset Market Map viewport"]').trigger('click')
    expect(wrapper.find('[aria-live="polite"]').text()).toBe('100%')
    expect(apiPost.mock.calls.length).toBeGreaterThan(0)
  })

  it('publishes an additive selection into a new personal watchlist', async () => {
    createWatchlist.mockResolvedValue({ id: 9, name: 'XLK leaders', is_managed: false, is_locked: false, items: [] })
    addItem.mockResolvedValue({ id: 90, instrument_id: 1 })
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    await wrapper.get('.market-map-tool__tile').trigger('click')
    await wrapper.get('.market-map-tool__tile:nth-child(2)').trigger('click', { shiftKey: true })
    await wrapper.get('[aria-label="Market Map new watchlist name"]').setValue('XLK leaders')
    const saveButton = wrapper.findAll('button').find(button => button.text() === 'Save selection')
    expect(saveButton).toBeDefined()
    await saveButton!.trigger('click')
    await flushPromises()

    expect(createWatchlist).toHaveBeenCalledWith('XLK leaders')
    expect(addItem).toHaveBeenCalledWith(9, 1)
    expect(addItem).toHaveBeenCalledWith(9, 2)
    expect(wrapper.find('[role="status"]').text()).toContain('2 selected members saved')
  })

  it('publishes the canonical source and selected members into breadth and Study Lab', async () => {
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    await wrapper.get('.market-map-tool__tile').trigger('click')
    await wrapper.get('[aria-label="Open selected members in Market Breadth"]').trigger('click')
    await wrapper.get('[aria-label="Open selected members in Study Lab"]').trigger('click')

    expect(wrapper.emitted('publishAnalysis')).toEqual([
      [{ target: 'breadth', sourceId: 'market-group:sp500', selectedIds: [1], selectedSymbols: ['NVDA'], scope: 'selection' }],
      [{ target: 'study_lab', sourceId: 'market-group:sp500', selectedIds: [1], selectedSymbols: ['NVDA'], scope: 'selection' }],
    ])
  })

  it('opens the full canonical source without requiring a tile selection', async () => {
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    await wrapper.get('[aria-label="Open full source in Market Breadth"]').trigger('click')
    await wrapper.get('[aria-label="Open full source in Study Lab"]').trigger('click')

    expect(wrapper.emitted('publishAnalysis')).toEqual([
      [{ target: 'breadth', sourceId: 'market-group:sp500', selectedIds: [], selectedSymbols: [], scope: 'full' }],
      [{ target: 'study_lab', sourceId: 'market-group:sp500', selectedIds: [], selectedSymbols: [], scope: 'full' }],
    ])
  })

  it('saves and reopens a named snapshot without changing the source contract', async () => {
    const snapshot = { id: 12, name: 'Morning leaders', source_id: 'market-group:sp500', membership_version: 'v1', cache_key: 'a'.repeat(64), snapshot_hash: 'b'.repeat(64), created_at: '2026-08-07T15:30:00Z', updated_at: '2026-08-07T15:30:00Z', map: response }
    apiPost.mockReset()
    apiPost.mockImplementation((path: string) => Promise.resolve(path === '/analysis/market-map' ? response : snapshot))
    apiGet.mockImplementation((path: string) => Promise.resolve(path.includes('/snapshots/12') ? snapshot : []))
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    await wrapper.get('[aria-label="Market Map snapshot name"]').setValue('Morning leaders')
    const saveSnapshotButton = wrapper.findAll('button').find(button => button.text() === 'Save snapshot')
    expect(saveSnapshotButton).toBeDefined()
    await saveSnapshotButton!.trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/analysis/market-map/snapshots', { name: 'Morning leaders', cache_key: response.cache_key })
    expect(wrapper.text()).toContain('Snapshot · Morning leaders')
    expect(wrapper.get('[aria-label="Market Map snapshot"]').element.value).toBe('12')
  })

  it('ignores stale snapshot responses after a newer snapshot selection', async () => {
    const older = { id: 12, name: 'Older leaders', source_id: 'market-group:sp500', membership_version: 'v1', cache_key: 'a'.repeat(64), snapshot_hash: 'b'.repeat(64), created_at: '2026-08-07T15:30:00Z', updated_at: '2026-08-07T15:30:00Z', map: response }
    const newer = { ...older, id: 13, name: 'Newer leaders', cache_key: 'c'.repeat(64), snapshot_hash: 'd'.repeat(64) }
    let resolveOlder!: (value: typeof older) => void
    const olderResult = new Promise<typeof older>(resolve => { resolveOlder = resolve })
    apiGet.mockImplementation((path: string) => {
      if (path === '/analysis/market-map/snapshots') return Promise.resolve([{ id: older.id, name: older.name }, { id: newer.id, name: newer.name }])
      if (path === '/analysis/market-map/snapshots/12') return olderResult
      if (path === '/analysis/market-map/snapshots/13') return Promise.resolve(newer)
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool)
    await vi.waitFor(() => expect(wrapper.get('[aria-label="Market Map snapshot"] option[value="12"]').exists()).toBe(true))

    const snapshotSelect = wrapper.get('[aria-label="Market Map snapshot"]')
    await snapshotSelect.setValue('12')
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/analysis/market-map/snapshots/12'))
    snapshotSelect.element.removeAttribute('disabled')
    await snapshotSelect.setValue('13')
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/analysis/market-map/snapshots/13'))
    await vi.waitFor(() => expect(wrapper.text()).toContain('Snapshot · Newer leaders'))

    resolveOlder(older)
    await flushPromises()

    expect(wrapper.text()).toContain('Snapshot · Newer leaders')
    expect(wrapper.text()).not.toContain('Snapshot · Older leaders')
    wrapper.unmount()
  })

  it('refreshes the live map after leaving a loaded snapshot', async () => {
    const snapshot = { id: 12, name: 'Morning leaders', source_id: 'market-group:sp500', membership_version: 'v1', cache_key: 'saved-cache', snapshot_hash: 'b'.repeat(64), created_at: '2026-08-07T15:30:00Z', updated_at: '2026-08-07T15:30:00Z', map: { ...response, cache_key: 'saved-cache' } }
    const refreshed = { ...response, cache_key: 'live-cache' }
    let mapRuns = 0
    apiGet.mockImplementation((path: string) => {
      if (path === '/analysis/market-map/snapshots') return Promise.resolve([{ id: snapshot.id, name: snapshot.name }])
      if (path === '/analysis/market-map/snapshots/12') return Promise.resolve(snapshot)
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string) => {
      if (path === '/analysis/market-map') {
        mapRuns += 1
        return Promise.resolve(mapRuns === 1 ? response : refreshed)
      }
      return Promise.resolve(snapshot)
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500' } } })
    await vi.waitFor(() => expect(mapRuns).toBe(1))

    const snapshotSelect = wrapper.get('[aria-label="Market Map snapshot"]')
    await snapshotSelect.setValue('12')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Snapshot · Morning leaders'))
    await snapshotSelect.setValue('')

    await vi.waitFor(() => expect(mapRuns).toBe(2))
    await vi.waitFor(() => expect(wrapper.text()).toContain('Cached result'))
    expect(wrapper.text()).not.toContain('Snapshot · Morning leaders')
    expect(apiPost).toHaveBeenLastCalledWith('/analysis/market-map', expect.objectContaining({ source_id: 'market-group:sp500' }))
    expect(wrapper.get('[aria-label="Market Map snapshot"]').element.value).toBe('')
    wrapper.unmount()
  })

  it('does not publish a snapshot save after a newer map refresh', async () => {
    const saved = { id: 14, name: 'Prior map', source_id: 'market-group:sp500', membership_version: 'v1', cache_key: response.cache_key, snapshot_hash: 'e'.repeat(64), created_at: '2026-08-07T15:30:00Z', updated_at: '2026-08-07T15:30:00Z', map: response }
    let resolveSave!: (value: typeof saved) => void
    const saveResult = new Promise<typeof saved>(resolve => { resolveSave = resolve })
    let mapRuns = 0
    apiGet.mockResolvedValue([])
    apiPost.mockImplementation((path: string) => {
      if (path === '/analysis/market-map') {
        mapRuns += 1
        return Promise.resolve(mapRuns === 1 ? response : { ...response, cache_key: 'refreshed-map-cache' })
      }
      if (path === '/analysis/market-map/snapshots') return saveResult
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500' } } })
    await vi.waitFor(() => expect(mapRuns).toBeGreaterThan(0))
    await flushPromises()
    const initialMapRuns = mapRuns

    await wrapper.get('[aria-label="Market Map snapshot name"]').setValue('Prior map')
    await wrapper.findAll('button').find(button => button.text() === 'Save snapshot')!.trigger('click')
    await vi.waitFor(() => expect(apiPost).toHaveBeenCalledWith('/analysis/market-map/snapshots', { name: 'Prior map', cache_key: response.cache_key }))

    await wrapper.get('.market-map-tool__run').trigger('click')
    await vi.waitFor(() => expect(mapRuns).toBe(initialMapRuns + 1))
    resolveSave(saved)
    await flushPromises()

    expect(wrapper.get('[aria-label="Market Map snapshot"]').element.value).toBe('')
    expect(wrapper.text()).not.toContain('Snapshot · Prior map')
    wrapper.unmount()
  })

  it('exports the current source-agnostic map cells as CSV', async () => {
    const createObjectURL = vi.fn(() => 'blob:market-map')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL })
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    const exportButton = wrapper.findAll('button').find(button => button.text() === 'Export CSV')
    expect(exportButton).toBeDefined()
    await exportButton!.trigger('click')

    expect(createObjectURL).toHaveBeenCalledOnce()
    expect(anchorClick).toHaveBeenCalledOnce()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:market-map')
    anchorClick.mockRestore()
    vi.unstubAllGlobals()
  })

  it('authors a breadth condition and sends it as the map colour definition', async () => {
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, color_metric: body?.color_metric, condition: body?.condition })
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500' } } })
    await flushPromises()

    await wrapper.get('select[aria-label="Market Map colour metric"]').setValue('breadth')
    await wrapper.get('input[aria-label="Market Map breadth moving average period"]').setValue('3')
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()

    const request = apiPost.mock.calls.map(call => call[1]).find(body => body?.color_metric === 'breadth')
    expect(request).toEqual(expect.objectContaining({
      color_metric: 'breadth',
      condition: { kind: 'above_moving_average', params: { period: 3, average: 'sma', comparator: 'above' } },
    }))
  })

  it('saves the current breadth condition as an immutable Study Lab definition', async () => {
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/market-map') return Promise.resolve(response)
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 91 }] })
      return Promise.resolve(body ?? {})
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500' } } })
    await flushPromises()

    await wrapper.get('select[aria-label="Market Map colour metric"]').setValue('breadth')
    await wrapper.get('[aria-label="Market Map breadth definition name"]').setValue('SPY within one percent of highs')
    await wrapper.get('[aria-label="Save as Study Lab definition"]').trigger('click')
    await flushPromises()

    const request = apiPost.mock.calls.find(call => call[0] === '/code/assets')?.[1] as Record<string, any>
    expect(request).toEqual(expect.objectContaining({ kind: 'study', name: 'SPY within one percent of highs' }))
    expect(request.initial_version.output_contract).toBe('study')
    expect(request.initial_version.source).toContain('research.breadth_condition')
    expect(request.initial_version.default_parameters).toEqual(expect.objectContaining({ source_id: 'market-group:sp500' }))
    expect(wrapper.text()).toContain('Saved immutable Study Lab definition.')
    expect(invalidateQueries).toHaveBeenCalled()
  })

  it('does not publish a reusable breadth definition after the Market Map unmounts', async () => {
    let resolveDefinition: ((value: unknown) => void) | undefined
    const definitionResult = new Promise(resolve => { resolveDefinition = resolve })
    apiPost.mockImplementation((path: string) => {
      if (path === '/analysis/market-map') return Promise.resolve(response)
      if (path === '/code/assets') return definitionResult
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500' } } })
    await flushPromises()

    await wrapper.get('select[aria-label="Market Map colour metric"]').setValue('breadth')
    await wrapper.get('[aria-label="Market Map breadth definition name"]').setValue('Detached breadth definition')
    await wrapper.get('[aria-label="Save as Study Lab definition"]').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({ name: 'Detached breadth definition' }))
    wrapper.unmount()

    resolveDefinition?.({ versions: [{ id: 92 }] })
    await flushPromises()

    expect(invalidateQueries).not.toHaveBeenCalled()
  })

  it('supports the reusable nested breadth condition editor for heatmap colours', async () => {
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, color_metric: body?.color_metric, condition: body?.condition })
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500' } } })
    await flushPromises()

    await wrapper.get('select[aria-label="Market Map colour metric"]').setValue('breadth')
    await wrapper.get('input[aria-label="Use advanced Market Map breadth condition editor"]').setValue(true)
    await wrapper.get('select[aria-label="Breadth condition type 1"]').setValue('within_52_week_high')
    await wrapper.get('select[aria-label="Breadth 52-week direction 1"]').setValue('low')
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()

    const request = apiPost.mock.calls.map(call => call[1]).find(body => body?.color_metric === 'breadth')
    expect(request).toEqual(expect.objectContaining({
      color_metric: 'breadth',
      condition: { kind: 'within_52_week_high', params: { direction: 'low', threshold: 0.01, lookback: 252 } },
    }))
  })

  it('authors a cross-sectional percentile breadth colour target', async () => {
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, color_metric: body?.color_metric, condition: body?.condition })
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500' } } })
    await flushPromises()

    await wrapper.get('select[aria-label="Market Map colour metric"]').setValue('breadth')
    await wrapper.get('input[aria-label="Use advanced Market Map breadth condition editor"]').setValue(true)
    await wrapper.get('select[aria-label="Breadth condition type 1"]').setValue('percentile')
    await wrapper.get('select[aria-label="Breadth percentile scope 1"]').setValue('cross_sectional')
    await wrapper.get('select[aria-label="Breadth percentile field 1"]').setValue('return')
    await wrapper.get('input[aria-label="Breadth percentile target 1"]').setValue('0.8')
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()

    const request = apiPost.mock.calls.map(call => call[1]).find(body => body?.color_metric === 'breadth' && body?.condition?.kind === 'percentile')
    expect(request).toEqual(expect.objectContaining({
      color_metric: 'breadth',
      condition: { kind: 'percentile', target_scope: 'cross_sectional', params: { field: 'return', period: 252, operator: 'gte', percentile: 0.8 } },
    }))
  })

  it('serializes a mixed member and cross-sectional breadth tree for the heatmap', async () => {
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, color_metric: body?.color_metric, condition: body?.condition })
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500' } } })
    await flushPromises()

    await wrapper.get('select[aria-label="Market Map colour metric"]').setValue('breadth')
    await wrapper.get('input[aria-label="Use advanced Market Map breadth condition editor"]').setValue(true)
    await wrapper.get('select[aria-label="Breadth condition type 1"]').setValue('percentile')
    await wrapper.get('select[aria-label="Breadth percentile scope 1"]').setValue('cross_sectional')
    await wrapper.get('button.breadth-condition-tree__wrap').trigger('click')
    await wrapper.get('.breadth-condition-tree__footer button').trigger('click')
    await wrapper.get('select[aria-label="Breadth condition type 1.2"]').setValue('comparison')
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()

    const request = apiPost.mock.calls.map(call => call[1]).find(body => body?.color_metric === 'breadth' && body?.condition?.kind === 'all')
    expect(request?.condition).toEqual({
      kind: 'all',
      params: {
        conditions: [
          { kind: 'percentile', target_scope: 'cross_sectional', params: { field: 'close', period: 252, operator: 'gte', percentile: 0.8 } },
          { kind: 'comparison', params: { field: 'close', operator: 'gte', threshold: 0 } },
        ],
      },
    })
  })

  it('runs a completed isolated Python output before colouring the map', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/code/assets') return Promise.resolve([{ kind: 'condition', name: 'Momentum score', versions: [{ id: 17, version_number: 2, output_contract: 'series' }] }])
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/breadth/python') return Promise.resolve({ run_id: 42 })
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, color_metric: body?.color_metric, python_run_id: body?.python_run_id })
      return Promise.resolve([])
    })
    apiGet.mockImplementation((path: string) => {
      if (path === '/code/assets') return Promise.resolve([{ kind: 'condition', name: 'Momentum score', versions: [{ id: 17, version_number: 2, output_contract: 'series' }] }])
      if (path === '/analysis/breadth/python/runs/42') return Promise.resolve({ status: 'completed' })
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500', color_metric: 'python', python_code_version_id: 17 } } })
    await flushPromises()
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()
    const request = apiPost.mock.calls.map(call => call[1]).find(body => body?.color_metric === 'python')
    expect(request).toEqual(expect.objectContaining({ color_metric: 'python', python_run_id: 42 }))

    await wrapper.get('select[aria-label="Market Map colour metric"]').setValue('return')
    await wrapper.get('select[aria-label="Market Map area metric"]').setValue('python')
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()
    const areaRequest = apiPost.mock.calls.map(call => call[1]).find(body => body?.area_metric === 'python')
    expect(areaRequest).toEqual(expect.objectContaining({ area_metric: 'python', python_run_id: 42 }))
  })

  it('ignores stale Python run resolution after the source changes', async () => {
    const previousSources = sourceState.sources
    sourceState.sources = [
      ...previousSources,
      { ...previousSources[0], source_id: 'market-group:nasdaq', name: 'Nasdaq 100' },
    ]
    let resolveFirstStatus!: (value: { status: string }) => void
    const firstStatus = new Promise<{ status: string }>(resolve => { resolveFirstStatus = resolve })
    let pythonQueue = 0
    apiGet.mockImplementation((path: string) => {
      if (path === '/code/assets') return Promise.resolve([{ kind: 'condition', name: 'Momentum score', versions: [{ id: 17, version_number: 2, output_contract: 'series' }] }])
      if (path === '/analysis/breadth/python/runs/1') return firstStatus
      if (path === '/analysis/breadth/python/runs/2') return Promise.resolve({ status: 'completed' })
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/breadth/python') return Promise.resolve({ run_id: ++pythonQueue })
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, source: { ...response.source, source_id: body?.source_id }, color_metric: body?.color_metric, python_run_id: body?.python_run_id })
      return Promise.resolve([])
    })

    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500', color_metric: 'python', python_code_version_id: 17 } } })
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/analysis/breadth/python/runs/1'))

    await wrapper.get('[aria-label="Market Map universe"]').setValue('market-group:nasdaq')
    await vi.waitFor(() => expect(apiPost.mock.calls.filter(([path]) => path === '/analysis/breadth/python')).toHaveLength(2))
    await vi.waitFor(() => expect(apiPost.mock.calls.filter(([path, body]) => path === '/analysis/market-map' && body?.source_id === 'market-group:nasdaq')).toHaveLength(1))

    resolveFirstStatus({ status: 'completed' })
    await flushPromises()

    expect(apiPost.mock.calls.filter(([path]) => path === '/analysis/market-map')).toHaveLength(1)
    expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual(expect.objectContaining({ python_run_id: 2, source_id: 'market-group:nasdaq' }))
    wrapper.unmount()
    sourceState.sources = previousSources
  })

  it('ignores a late Python asset response after unmount', async () => {
    let resolveAssets!: (value: Array<{ kind: string; name: string; versions: Array<{ id: number; version_number: number; output_contract: 'series' }> }>) => void
    const assets = new Promise<Array<{ kind: string; name: string; versions: Array<{ id: number; version_number: number; output_contract: 'series' }> }>>(resolve => { resolveAssets = resolve })
    apiGet.mockImplementation((path: string) => {
      if (path === '/code/assets') return assets
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { color_metric: 'python' } } })
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/code/assets'))

    wrapper.unmount()
    resolveAssets([{ kind: 'condition', name: 'Late asset', versions: [{ id: 17, version_number: 1, output_contract: 'series' }] }])
    await flushPromises()

    expect((wrapper.vm as any).pythonAssets).toEqual([])
  })

  it('runs a Python breadth condition tree before colouring the map', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/code/assets') return Promise.resolve([{ kind: 'condition', name: 'Momentum score', versions: [{ id: 17, version_number: 1, output_contract: 'series' }] }])
      if (path === '/analysis/breadth/python/runs/42') return Promise.resolve({ status: 'completed' })
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/breadth/python') return Promise.resolve({ run_id: 42 })
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, color_metric: body?.color_metric, condition: body?.condition, python_run_id: body?.python_run_id })
      return Promise.resolve([])
    })

    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500' } } })
    await flushPromises()

    await wrapper.get('select[aria-label="Market Map colour metric"]').setValue('breadth')
    await wrapper.get('input[aria-label="Use advanced Market Map breadth condition editor"]').setValue(true)
    await wrapper.get('select[aria-label="Breadth condition type 1"]').setValue('python_series')
    await wrapper.get('[aria-label="Breadth Python series condition asset 1"]').setValue('17')
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()

    const pythonRequest = apiPost.mock.calls.find(call => call[0] === '/analysis/breadth/python')?.[1] as Record<string, any>
    expect(pythonRequest).toEqual(expect.objectContaining({
      code_version_id: 17,
      output_contract: 'boolean',
      condition_tree: { kind: 'python_series', params: expect.objectContaining({ code_version_id: 17 }) },
    }))
    const mapRequest = apiPost.mock.calls.find(call => call[0] === '/analysis/market-map' && call[1]?.color_metric === 'breadth')?.[1]
    expect(mapRequest).toEqual(expect.objectContaining({ color_metric: 'breadth', python_run_id: 42 }))
  })

  it('passes a canonical reference universe to Python breadth comparisons', async () => {
    const previousSources = sourceState.sources
    sourceState.sources = [
      ...previousSources,
      { ...previousSources[0], source_id: 'watchlist:reference', source_kind: 'personal', name: 'Reference group', locked: false },
    ]
    apiGet.mockImplementation((path: string) => {
      if (path === '/code/assets') return Promise.resolve([
        { kind: 'condition', name: 'Momentum score', versions: [{ id: 17, version_number: 1, output_contract: 'series' }] },
        { kind: 'condition', name: 'Reference score', versions: [{ id: 18, version_number: 1, output_contract: 'series' }] },
      ])
      if (path === '/analysis/breadth/python/runs/42') return Promise.resolve({ status: 'completed' })
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/breadth/python') return Promise.resolve({ run_id: 42 })
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, color_metric: body?.color_metric, condition: body?.condition, python_run_id: body?.python_run_id })
      return Promise.resolve([])
    })

    const wrapper = mount(MarketMapTool, {
      props: {
        configuration: {
          source_id: 'market-group:sp500',
          color_metric: 'breadth',
          advanced_breadth_editor: true,
          reference_source_id: 'watchlist:reference',
          condition: {
            kind: 'python_series_comparison',
            params: {
              left_code_version_id: 17,
              right_code_version_id: 18,
              right_scope: 'benchmark',
              relation: 'difference',
              operator: 'gte',
              threshold: 0,
            },
          },
        },
      },
    })
    await flushPromises()
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()

    const request = apiPost.mock.calls.find(call => call[0] === '/analysis/breadth/python')?.[1]
    expect(request).toEqual(expect.objectContaining({
      reference_universe: { kind: 'watchlist', key: 'watchlist:reference', point_in_time: true },
    }))
    expect(request).not.toHaveProperty('benchmark')
    wrapper.unmount()
    sourceState.sources = previousSources
  })

  it('uses the same Python breadth source contract for derived and explicit watchlists', async () => {
    const previousSources = sourceState.sources
    sourceState.sources = [{ ...previousSources[0], source_id: 'combo:tech-leaders', source_kind: 'combo', name: 'Tech leaders', locked: true }]
    apiGet.mockImplementation((path: string) => {
      if (path === '/code/assets') return Promise.resolve([{ kind: 'condition', name: 'Momentum score', versions: [{ id: 17, version_number: 1, output_contract: 'boolean' }] }])
      if (path === '/analysis/breadth/python/runs/42') return Promise.resolve({ status: 'completed' })
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/breadth/python') return Promise.resolve({ run_id: 42 })
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, source: { ...response.source, source_id: body?.source_id }, color_metric: body?.color_metric, python_run_id: body?.python_run_id })
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'combo:tech-leaders', color_metric: 'python', python_code_version_id: 17 } } })
    await flushPromises()
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()
    const request = apiPost.mock.calls.find(call => call[0] === '/analysis/breadth/python')?.[1]
    expect(request).toEqual(expect.objectContaining({ universe: { kind: 'watchlist', key: 'combo:tech-leaders', point_in_time: true } }))
    wrapper.unmount()
    sourceState.sources = previousSources
  })

  it('uses the same Python breadth source contract for benchmark-family legs', async () => {
    const previousSources = sourceState.sources
    sourceState.sources = [{
      ...previousSources[0],
      source_id: 'benchmark-family:sp500:cap_weight',
      source_kind: 'index_membership',
      name: 'S&P 500 — Cap weight',
      locked: true,
    }]
    apiGet.mockImplementation((path: string) => {
      if (path === '/code/assets') return Promise.resolve([{ kind: 'condition', name: 'Momentum score', versions: [{ id: 17, version_number: 1, output_contract: 'boolean' }] }])
      if (path === '/analysis/breadth/python/runs/42') return Promise.resolve({ status: 'completed' })
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/breadth/python') return Promise.resolve({ run_id: 42 })
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, source: { ...response.source, source_id: body?.source_id }, color_metric: body?.color_metric, python_run_id: body?.python_run_id })
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'benchmark-family:sp500:cap_weight', color_metric: 'python', python_code_version_id: 17 } } })
    await flushPromises()
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()
    const request = apiPost.mock.calls.find(call => call[0] === '/analysis/breadth/python')?.[1]
    expect(request).toEqual(expect.objectContaining({
      universe: { kind: 'watchlist', key: 'benchmark-family:sp500:cap_weight', point_in_time: true },
    }))
    wrapper.unmount()
    sourceState.sources = previousSources
  })

  it('authors a provider numeric area field and persists its selection', async () => {
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500' } } })
    await flushPromises()

    await wrapper.get('select[aria-label="Market Map area metric"]').setValue('field')
    await wrapper.get('select[aria-label="Market Map provider numeric area field"]').setValue('beta')
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()

    const request = apiPost.mock.calls.map(call => call[1]).find(body => body?.area_metric === 'field')
    expect(request).toEqual(expect.objectContaining({ area_metric: 'field', area_field: 'beta' }))
    expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual(expect.objectContaining({ area_metric: 'field', area_field: 'beta' }))
  })

  it('sends an arbitrary completed-session custom period for any watchlist source', async () => {
    const wrapper = mount(MarketMapTool, {
      props: {
        configuration: {
          source_id: 'market-group:sp500',
          period: 'CUSTOM',
          start_date: '2026-01-05',
          end_date: '2026-02-06',
        },
      },
    })
    await flushPromises()

    const request = apiPost.mock.calls.map(call => call[1]).find(body => body?.period === 'CUSTOM')
    expect(request).toEqual(expect.objectContaining({
      period: 'CUSTOM',
      start: '2026-01-05',
      end: '2026-02-06T23:59:59Z',
    }))
    await wrapper.get('[aria-label="Market Map custom start date"]').setValue('2026-01-06')
    expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual(expect.objectContaining({
      period: 'CUSTOM',
      start_date: '2026-01-06',
      end_date: '2026-02-06',
    }))
  })

  it('resolves explicit symbols to canonical IDs before building an ephemeral map source', async () => {
    apiGet.mockImplementation((path: string) => {
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/instruments/resolve-canonical') {
        expect(body).toEqual({ symbols: ['NVDA', 'MSFT'] })
        return Promise.resolve({ resolved: [{ symbol: 'NVDA', instrument_id: 1 }, { symbol: 'MSFT', instrument_id: 2 }], missing: [] })
      }
      return Promise.resolve(response)
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { explicit_symbols: 'NVDA, MSFT' } } })
    await flushPromises()

    const request = apiPost.mock.calls.map(call => call[1]).find(body => body?.source_id?.startsWith('explicit:'))
    expect(request).toEqual(expect.objectContaining({ source_id: 'explicit:1,2' }))
    expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual(expect.objectContaining({
      explicit_symbols: 'NVDA, MSFT',
      source_id: 'explicit:1,2',
    }))
  })

  it('saves the complete explicit canonical selection as a personal watchlist', async () => {
    const explicitResponse = {
      ...response,
      source: { ...response.source, source_id: 'explicit:1,2', source_kind: 'explicit', name: 'Explicit symbols (2)', can_follow: false, can_clone: false, provenance: { instrument_ids: [1, 2] } },
    }
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/instruments/resolve-canonical') return Promise.resolve({ resolved: [{ symbol: 'NVDA', instrument_id: 1 }, { symbol: 'MSFT', instrument_id: 2 }], missing: [] })
      if (path === '/analysis/market-map') return Promise.resolve(explicitResponse)
      return Promise.resolve(response)
    })
    createWatchlist.mockResolvedValue({ id: 12, name: 'My explicit set', is_managed: false, is_locked: false, items: [] })
    addItem.mockResolvedValue({ id: 120, instrument_id: 1 })
    const wrapper = mount(MarketMapTool, { props: { configuration: { explicit_symbols: 'NVDA, MSFT' } } })
    await flushPromises()

    await wrapper.get('[aria-label="Explicit source watchlist name"]').setValue('My explicit set')
    await wrapper.findAll('button').find(button => button.text() === 'Save as watchlist')!.trigger('click')
    await flushPromises()

    expect(createWatchlist).toHaveBeenCalledWith('My explicit set')
    expect(addItem).toHaveBeenCalledWith(12, 1)
    expect(addItem).toHaveBeenCalledWith(12, 2)
    expect(wrapper.find('[role="status"]').text()).toContain('2 canonical members saved as My explicit set')
  })

  it('does not continue explicit-symbol watchlist publication after the Market Map unmounts', async () => {
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/instruments/resolve-canonical') return Promise.resolve({ resolved: [{ symbol: 'NVDA', instrument_id: 1 }, { symbol: 'MSFT', instrument_id: 2 }], missing: [] })
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, source: { ...response.source, source_id: 'explicit:1,2', source_kind: 'explicit', provenance: { instrument_ids: [1, 2] } } })
      return Promise.resolve(response)
    })
    let resolveCreate: ((value: unknown) => void) | undefined
    const createResult = new Promise(resolve => { resolveCreate = resolve })
    createWatchlist.mockReturnValue(createResult)

    const wrapper = mount(MarketMapTool, { props: { configuration: { explicit_symbols: 'NVDA, MSFT' } } })
    await flushPromises()
    await wrapper.get('[aria-label="Explicit source watchlist name"]').setValue('Detached explicit')
    await wrapper.findAll('button').find(button => button.text() === 'Save as watchlist')!.trigger('click')
    await flushPromises()

    expect(createWatchlist).toHaveBeenCalledWith('Detached explicit')
    wrapper.unmount()

    resolveCreate?.({ id: 15, name: 'Detached explicit', is_managed: false, is_locked: false, items: [] })
    await flushPromises()

    expect(addItem).not.toHaveBeenCalled()
  })

  it('authors an event predicate for Market Map breadth colouring', async () => {
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, color_metric: body?.color_metric, condition: body?.condition })
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500' } } })
    await flushPromises()

    await wrapper.get('select[aria-label="Market Map colour metric"]').setValue('breadth')
    await wrapper.get('select[aria-label="Market Map breadth condition"]').setValue('event')
    await wrapper.get('select[aria-label="Market Map breadth event type"]').setValue('dividend')
    await wrapper.get('input[aria-label="Market Map breadth event lookback"]').setValue('5')
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()

    const request = apiPost.mock.calls.map(call => call[1]).find(body => body?.color_metric === 'breadth' && body?.condition?.kind === 'event')
    expect(request).toEqual(expect.objectContaining({
      condition: { kind: 'event', params: { event_type: 'dividend', lookback_days: 5, include_estimates: false } },
    }))
  })

  it('uses a canonical reference source for relative-return map colouring', async () => {
    sourceState.sources.push({ source_id: 'watchlist:reference', source_kind: 'personal', name: 'Reference group', locked: false, can_follow: true, can_clone: true, can_edit_membership: true, member_count: 2, provenance: {} })
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, color_metric: body?.color_metric, reference_source_id: body?.reference_source_id, reference_source: sourceState.sources[1], reference_series_method: 'derived_equal_weight_return_index' })
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500', color_metric: 'relative_return', reference_source_id: 'watchlist:reference' } } })
    await flushPromises()
    await wrapper.get('[aria-label="Market Map reference universe"]').setValue('watchlist:reference')
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()

    const request = apiPost.mock.calls.map(call => call[1]).find(body => body?.color_metric === 'relative_return')
    expect(request).toEqual(expect.objectContaining({ reference_source_id: 'watchlist:reference', reference_symbol: null }))
  })
})
