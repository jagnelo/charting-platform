<template>
  <div class="holdings-view">
    <aside class="holdings-sidebar">
      <div class="sidebar-head">
        <div>
          <h1>ETF Holdings</h1>
          <p>Search an ETF to bootstrap or inspect its holdings snapshots.</p>
        </div>
      </div>

      <div class="search-field">
        <span>ETF instrument</span>
        <SearchBar
          v-model="profileSearch"
          placeholder="Search ETF instrument"
          mode="picker"
          fluid
          :result-types="['ETF', 'Fund']"
          :allow-expressions="false"
          :show-recent="false"
          :show-screener-link="false"
          @select="selectProfileFromSearch"
        />
      </div>

      <div class="profile-list">
        <div v-if="loadingProfiles" class="state-line">Loading ETFs...</div>
        <template v-else>
          <button
            v-for="profile in profiles"
            :key="profile.id"
            type="button"
            class="profile-card"
            :class="{ 'profile-card--active': selectedProfile?.id === profile.id }"
            @click="selectProfile(profile)"
          >
            <span class="profile-card__top">
              <b>{{ profile.symbol }}</b>
              <small>{{ profile.latest_composition_date || 'No date' }}</small>
            </span>
            <span>{{ profile.name }}</span>
            <em>
              <span
                class="capability-pill"
                :class="capabilityClass(profile.holdings_capability)"
              >{{ capabilityLabel(profile.holdings_capability) }}</span>
              · {{ profile.resolved_count }} ready · {{ profile.unresolved_count }} review
            </em>
          </button>
        </template>
      </div>
    </aside>

    <main class="holdings-main">
      <section class="workspace-panel">
        <div class="panel-title-row">
          <div>
            <h2>{{ selectedProfile?.symbol || 'Select an ETF' }}</h2>
            <p v-if="page">
              {{ page.snapshot.etf_name }} · {{ page.snapshot.composition_date }}
            </p>
            <p v-else>Choose an ETF to prepare its holdings workspace and inspect available snapshots.</p>
          </div>
          <div v-if="page" class="panel-meta">
            <span>{{ page.snapshot.source_provider }}</span>
            <span>{{ page.snapshot.source_quality }}</span>
            <span>{{ page.total }} rows</span>
            <span
              class="capability-pill"
              :class="capabilityClass(selectedCapability)"
            >{{ capabilityLabel(selectedCapability) }}</span>
          </div>
        </div>

        <div v-if="loadError" class="notice notice--error">{{ loadError }}</div>

        <div
          v-if="selectedCapability && !selectedCapability.usable_for_current_analysis"
          class="notice notice--capability"
          :class="capabilityClass(selectedCapability)"
          role="status"
        >
          <strong>Current holdings are not verified.</strong>
          {{ selectedCapability.reason }}
          <span v-if="selectedCapability.composition_date">
            Last composition: {{ selectedCapability.composition_date }}.
          </span>
          <span v-if="selectedCapability.failure_class" class="capability-failure-class">
            Last check classification: {{ capabilityFailureLabel(selectedCapability.failure_class) }}.
          </span>
          <span v-if="selectedCapability.symbol_audit?.next_action" class="capability-next-action">
            Next source-review action: {{ selectedCapability.symbol_audit.next_action }}
          </span>
          Historical snapshots remain available, but this data must not be treated as current.
        </div>

        <div v-if="selectedProfile" class="toolbar">
          <label>
            <span>Search rows</span>
            <input
              v-model="holdingsSearch"
              placeholder="Symbol, name, CUSIP, ISIN"
              type="search"
              @input="reloadHoldings"
            />
          </label>
          <label>
            <span>Sort</span>
            <select v-model="sortMode" @change="reloadHoldings">
              <option value="position">Position</option>
              <option value="weight">Weight</option>
              <option value="market_value">Market value</option>
              <option value="shares">Shares</option>
              <option value="symbol">Symbol</option>
              <option value="name">Name</option>
              <option value="resolved">Availability</option>
            </select>
          </label>
          <label>
            <span>Direction</span>
            <select v-model="sortDirection" @change="reloadHoldings">
              <option value="asc">Ascending</option>
              <option value="desc">Descending</option>
            </select>
          </label>
          <label v-if="snapshotOptions.length">
            <span>Snapshot</span>
            <select v-model="selectedSnapshotId" @change="reloadForSnapshotChange">
              <option
                v-for="option in snapshotOptions"
                :key="option.snapshot_id"
                :value="String(option.snapshot_id)"
              >
                {{ option.composition_date }}
              </option>
            </select>
          </label>
        </div>

        <div v-if="page" class="holdings-browser">
          <div class="holdings-table" role="table" aria-label="ETF holdings research table">
            <div class="holding-row holding-row--head" role="row">
              <span>Symbol</span>
              <span>Name</span>
              <span>Weight</span>
              <span>Market value</span>
              <span>Shares</span>
              <span>Status</span>
            </div>
            <button
              v-for="holding in page.holdings"
              :key="holding.id"
              type="button"
              class="holding-row"
              :class="{ 'holding-row--selected': selectedHolding?.id === holding.id }"
              @click="selectedHolding = holding"
            >
              <span>
                <b>{{ holdingSymbol(holding) }}</b>
                <small>{{ holding.holding_type }}</small>
              </span>
              <span>{{ holdingName(holding) }}</span>
              <span>{{ formatWeight(holding.weight) }}</span>
              <span>{{ formatMoney(holding.market_value, holding.currency) }}</span>
              <span>{{ formatQuantity(holding.shares) }}</span>
              <span :class="statusClass(holding)">
                {{ statusLabel(holding) }}
              </span>
            </button>
          </div>

          <aside v-if="selectedHolding" class="holding-detail">
            <div class="detail-title">
              <div>
                <small>Selected holding</small>
                <h3>{{ holdingSymbol(selectedHolding) }}</h3>
                <p>{{ holdingName(selectedHolding) }}</p>
              </div>
              <button type="button" :disabled="!openableSymbol(selectedHolding)" @click="openChart(selectedHolding)">
                Open chart
              </button>
            </div>
            <dl>
              <div>
                <dt>Weight</dt>
                <dd>{{ formatWeight(selectedHolding.weight) }}</dd>
              </div>
              <div>
                <dt>Market value</dt>
                <dd>{{ formatMoney(selectedHolding.market_value, selectedHolding.currency) }}</dd>
              </div>
              <div>
                <dt>Venue</dt>
                <dd>{{ venueLabel(selectedHolding) }}</dd>
              </div>
              <div>
                <dt>CUSIP</dt>
                <dd>{{ selectedHolding.cusip || '—' }}</dd>
              </div>
              <div>
                <dt>ISIN</dt>
                <dd>{{ selectedHolding.isin || '—' }}</dd>
              </div>
              <div>
                <dt>Availability</dt>
                <dd :class="statusClass(selectedHolding)">{{ statusLabel(selectedHolding) }}</dd>
              </div>
            </dl>
          </aside>
        </div>

        <div v-if="page" class="pager">
          <button type="button" :disabled="offset === 0" @click="previousPage">Previous</button>
          <span>{{ offset + 1 }}-{{ pageEnd }} of {{ page.total }}</span>
          <button type="button" :disabled="!page.has_next" @click="nextPage">Next</button>
        </div>

        <section v-if="diff && snapshotOptions.length > 1" class="diff-panel">
          <div class="diff-head">
            <div>
              <h3>Snapshot changes</h3>
              <p>{{ diff.left_snapshot.composition_date }} -> {{ diff.right_snapshot.composition_date }}</p>
            </div>
            <div class="diff-picker">
              <label>
                <span>Compare against</span>
                <select v-model="compareSnapshotId" @change="loadDiff">
                  <option
                    v-for="option in compareOptions"
                    :key="option.snapshot_id"
                    :value="String(option.snapshot_id)"
                  >
                    {{ option.composition_date }}
                  </option>
                </select>
              </label>
            </div>
          </div>

          <div class="diff-summary">
            <span class="diff-chip diff-chip--added">{{ diff.added }} added</span>
            <span class="diff-chip diff-chip--removed">{{ diff.removed }} removed</span>
            <span class="diff-chip diff-chip--changed">{{ diff.changed }} changed</span>
            <span class="diff-chip">{{ diff.unchanged }} unchanged</span>
          </div>

          <div class="diff-metrics">
            <div class="metric-card">
              <small>Gross churn</small>
              <strong>{{ formatWeight(diff.summary.gross_weight_churn) }}</strong>
              <span>Total absolute weight change across the comparison.</span>
            </div>
            <div class="metric-card">
              <small>Added weight</small>
              <strong class="status-added">{{ formatWeight(diff.summary.total_added_weight) }}</strong>
              <span>Fresh exposure introduced in the newer snapshot.</span>
            </div>
            <div class="metric-card">
              <small>Removed weight</small>
              <strong class="status-removed">{{ formatWeight(diff.summary.total_removed_weight) }}</strong>
              <span>Exposure that disappeared versus the older snapshot.</span>
            </div>
            <div class="metric-card">
              <small>Upweights / downweights</small>
              <strong>
                <span class="status-ok">{{ formatWeight(diff.summary.total_increased_weight) }}</span>
                <span class="metric-sep"> / </span>
                <span class="status-bad">{{ formatWeight(diff.summary.total_decreased_weight) }}</span>
              </strong>
              <span>Size changes among continuing holdings.</span>
            </div>
          </div>

          <div class="diff-highlights">
            <section v-if="diff.summary.largest_additions.length" class="highlight-card">
              <header>
                <h4>Largest additions</h4>
                <span>{{ diff.summary.largest_additions.length }}</span>
              </header>
              <button
                v-for="row in diff.summary.largest_additions"
                :key="`addition:${row.key}`"
                type="button"
                class="highlight-row"
              >
                <div>
                  <b>{{ row.symbol }}</b>
                  <small>{{ row.name }}</small>
                </div>
                <strong class="status-added">{{ formatWeight(row.weight_after) }}</strong>
              </button>
            </section>

            <section v-if="diff.summary.largest_removals.length" class="highlight-card">
              <header>
                <h4>Largest removals</h4>
                <span>{{ diff.summary.largest_removals.length }}</span>
              </header>
              <button
                v-for="row in diff.summary.largest_removals"
                :key="`removal:${row.key}`"
                type="button"
                class="highlight-row"
              >
                <div>
                  <b>{{ row.symbol }}</b>
                  <small>{{ row.name }}</small>
                </div>
                <strong class="status-removed">{{ formatWeight(row.weight_before) }}</strong>
              </button>
            </section>

            <section v-if="diff.summary.largest_reweights.length" class="highlight-card">
              <header>
                <h4>Largest reweights</h4>
                <span>{{ diff.summary.largest_reweights.length }}</span>
              </header>
              <button
                v-for="row in diff.summary.largest_reweights"
                :key="`reweight:${row.key}`"
                type="button"
                class="highlight-row"
              >
                <div>
                  <b>{{ row.symbol }}</b>
                  <small>{{ row.name }}</small>
                </div>
                <strong :class="diffDeltaClass(row.weight_delta)">{{ formatSignedWeight(row.weight_delta) }}</strong>
              </button>
            </section>
          </div>

          <div class="diff-table" role="table" aria-label="ETF holdings diff">
            <div class="diff-row diff-row--head" role="row">
              <span>Status</span>
              <span>Symbol</span>
              <span>Name</span>
              <span>Before</span>
              <span>After</span>
              <span>Delta</span>
            </div>
            <div
              v-for="row in diff.rows"
              :key="`${row.status}:${row.key}`"
              class="diff-row"
            >
              <span :class="diffStatusClass(row.status)">{{ row.status }}</span>
              <span><b>{{ row.symbol }}</b></span>
              <span>{{ row.name }}</span>
              <span>{{ formatWeight(row.weight_before) }}</span>
              <span>{{ formatWeight(row.weight_after) }}</span>
              <span :class="diffDeltaClass(row.weight_delta)">{{ formatSignedWeight(row.weight_delta) }}</span>
            </div>
          </div>
        </section>

        <section v-if="weightEvolution && weightEvolution.series.length" class="evolution-panel">
          <div class="diff-head">
            <div>
              <h3>Weight evolution</h3>
              <p>{{ weightEvolution.from_date }} -> {{ weightEvolution.to_date }}</p>
            </div>
            <div class="panel-meta">
              <span>{{ weightEvolution.snapshot_count }} snapshots</span>
              <span>{{ moverCountLabel(weightEvolution.series.length) }}</span>
            </div>
          </div>

          <div class="evolution-list">
            <article
              v-for="series in weightEvolution.series"
              :key="series.key"
              class="evolution-row"
            >
              <div class="evolution-row__label">
                <strong>{{ series.symbol }}</strong>
                <span>{{ series.name }}</span>
              </div>
              <div class="evolution-track" aria-hidden="true">
                <span
                  v-for="point in series.points"
                  :key="`${series.key}:${point.snapshot_id}`"
                  class="evolution-dot"
                  :class="evolutionDotClass(series, point.weight)"
                  :style="{ left: `${evolutionDotOffset(series, point.weight)}%` }"
                />
              </div>
              <div class="evolution-row__meta">
                <span>{{ formatWeight(series.first_weight) }}</span>
                <strong :class="diffDeltaClass(series.weight_delta)">{{ formatSignedWeight(series.weight_delta) }}</strong>
                <span>{{ formatWeight(series.last_weight) }}</span>
              </div>
            </article>
          </div>
        </section>

        <section v-if="transitionTimeline && transitionTimeline.transitions.length" class="transition-panel">
          <div class="diff-head">
            <div>
              <h3>Turnover timeline</h3>
              <p>{{ transitionTimeline.from_date }} -> {{ transitionTimeline.to_date }}</p>
            </div>
            <div class="panel-meta">
              <span>{{ transitionTimeline.snapshot_count }} snapshots</span>
              <span>{{ transitionTimeline.transition_count }} transitions</span>
            </div>
          </div>

          <div class="transition-list">
            <article
              v-for="transition in transitionTimeline.transitions"
              :key="`${transition.left_snapshot.id}:${transition.right_snapshot.id}`"
              class="transition-card"
            >
              <div class="transition-card__head">
                <strong>
                  {{ transition.left_snapshot.composition_date }}
                  <span>-></span>
                  {{ transition.right_snapshot.composition_date }}
                </strong>
                <b>{{ formatWeight(transition.gross_weight_churn) }} churn</b>
              </div>
              <div class="transition-metrics">
                <span class="status-added">{{ transition.added }} added</span>
                <span class="status-removed">{{ transition.removed }} removed</span>
                <span class="status-changed">{{ transition.changed }} reweighted</span>
              </div>
              <div class="transition-movers">
                <span v-for="row in transitionTopMovers(transition)" :key="`${transition.right_snapshot.id}:${row.key}`">
                  <b>{{ row.symbol }}</b>
                  <em :class="diffDeltaClass(row.weight_delta ?? row.weight_after ?? row.weight_before)">
                    {{ transitionMoverLabel(row) }}
                  </em>
                </span>
              </div>
            </article>
          </div>
        </section>

        <section v-if="selectedProfile && overlapCandidates.length" class="overlap-panel">
          <div class="diff-head">
            <div>
              <h3>ETF overlap</h3>
              <p>Compare shared holdings across selected ETF snapshots.</p>
            </div>
            <div class="overlap-actions">
              <button
                type="button"
                class="research-action"
                :disabled="!selectedOverlapSymbols.length || loadingOverlap"
                @click="loadOverlapSummary"
              >
                {{ loadingOverlap ? 'Comparing...' : 'Compare selected' }}
              </button>
              <button
                type="button"
                class="research-action research-action--ghost"
                :disabled="!canCompareOverlapFamily || loadingOverlap"
                @click="loadOverlapFamilyMatrix"
              >
                Compare family
              </button>
            </div>
          </div>

          <div class="overlap-family-controls" aria-label="ETF overlap family expansion">
            <label>
              <span>Issuer</span>
              <input v-model="overlapIssuer" :placeholder="selectedProfile.issuer || 'Issuer'" />
            </label>
            <label>
              <span>Family</span>
              <input v-model="overlapFundFamily" :placeholder="selectedProfile.fund_family || 'Fund family'" />
            </label>
            <label>
              <span>Search</span>
              <input v-model="overlapQuery" placeholder="Name, index, symbol" />
            </label>
            <label>
              <span>Limit</span>
              <input v-model.number="overlapFamilyLimit" min="2" max="100" type="number" />
            </label>
          </div>

          <div class="overlap-picker" aria-label="ETF overlap comparison targets">
            <button
              v-for="candidate in overlapCandidates"
              :key="candidate.symbol"
              type="button"
              class="overlap-target"
              :class="{ 'overlap-target--active': selectedOverlapSymbols.includes(candidate.symbol) }"
              @click="toggleOverlapSymbol(candidate.symbol)"
            >
              <b>{{ candidate.symbol }}</b>
              <span>{{ candidate.latest_composition_date || 'No date' }}</span>
            </button>
          </div>

          <div v-if="overlapMatrix" class="overlap-matrix">
            <div class="overlap-matrix__head">
              <strong>Overlap matrix</strong>
              <span>{{ overlapMatrix.etf_count }} ETFs · Jaccard overlap</span>
            </div>
            <div class="overlap-grid" :style="{ '--matrix-size': overlapMatrix.symbols.length }">
              <span class="overlap-grid__corner" />
              <b v-for="symbol in overlapMatrix.symbols" :key="`col:${symbol}`">{{ symbol }}</b>
              <template v-for="row in overlapMatrix.rows" :key="row.symbol">
                <b>{{ row.symbol }}</b>
                <span
                  v-for="cell in row.cells"
                  :key="`${cell.row_symbol}:${cell.column_symbol}`"
                  class="overlap-grid__cell"
                  :class="{ 'overlap-grid__cell--self': cell.row_symbol === cell.column_symbol }"
                  :style="overlapCellStyle(cell)"
                >
                  {{ formatPercentValue(cell.jaccard_overlap) }}
                </span>
              </template>
            </div>
            <div class="overlap-matrix__summary">
              <span v-for="row in overlapMatrix.rows" :key="`summary:${row.symbol}`">
                <b>{{ row.symbol }}</b>
                closest {{ row.closest_peer || '—' }} · distinct {{ row.most_distinct_peer || '—' }}
              </span>
            </div>
          </div>

          <div v-if="overlapSummary" class="overlap-results">
            <article
              v-for="pair in overlapSummary.pairs"
              :key="`${pair.left_symbol}:${pair.right_symbol}`"
              class="overlap-card"
            >
              <div class="overlap-card__head">
                <strong>{{ pair.left_symbol }} <span>vs</span> {{ pair.right_symbol }}</strong>
                <b>{{ formatPercentValue(pair.jaccard_overlap) }} overlap</b>
              </div>
              <div class="overlap-track" aria-hidden="true">
                <span :style="{ width: `${percentOffset(pair.jaccard_overlap)}%` }" />
              </div>
              <div class="overlap-card__stats">
                <span>{{ pair.shared_count }} shared</span>
                <span>{{ pair.left_unique_count }} {{ pair.left_symbol }} only</span>
                <span>{{ pair.right_unique_count }} {{ pair.right_symbol }} only</span>
                <span>{{ formatWeight(pair.overlap_weight_min) }} min weight</span>
              </div>
              <div v-if="pair.top_shared.length" class="overlap-shared">
                <span
                  v-for="row in pair.top_shared"
                  :key="`${pair.left_symbol}:${pair.right_symbol}:${row.key}`"
                >
                  <b>{{ row.symbol }}</b>
                  <em>{{ formatWeight(row.min_weight) }}</em>
                </span>
              </div>
            </article>
            <div v-if="overlapSummary.missing.length" class="notice notice--warn">
              Missing holdings data for {{ overlapSummary.missing.join(', ') }}.
            </div>
          </div>
        </section>

        <div v-if="!selectedProfile && !loadError" class="empty-state">
          Select an ETF to load or bootstrap its holdings research workspace.
        </div>
        <div v-else-if="page && !page.holdings.length" class="empty-state">
          No holdings match the current filters.
        </div>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import SearchBar from '@/components/common/SearchBar.vue'
import { api } from '@/lib/api'
import type {
  ETFHolding,
  ETFHoldingsSnapshot,
  ETFHoldingsDate,
  ETFHoldingsDiff,
  ETFHoldingsDiffRow,
  ETFHoldingsOverlapMatrix,
  ETFHoldingsOverlapMatrixCell,
  ETFHoldingsOverlapSummary,
  ETFHoldingsPage,
  ETFHoldingsTransition,
  ETFHoldingsTransitionTimeline,
  ETFHoldingsWeightEvolution,
  ETFHoldingsWeightEvolutionSeries,
  ETFHoldingsCapability,
  ETFProfile,
} from '@/types'

interface ETFSearchResult {
  symbol: string
  name: string
  exchange: string
  type: string
}

interface ETFProfileBootstrapResponse {
  profile: ETFProfile
  latest_snapshot: ETFHoldingsSnapshot | null
  probe: {
    adapter_key: string
    source_provider?: string | null
    confidence: string | number
    status: string
    reason?: string | null
    source_url?: string | null
    issuer_product_id?: string | null
    required_identifiers: string[]
  }
  refresh_attempted: boolean
  refresh_succeeded: boolean
  capability?: ETFHoldingsCapability | null
  message?: string | null
}

const router = useRouter()

const profiles = ref<ETFProfile[]>([])
const selectedProfile = ref<ETFProfile | null>(null)
const page = ref<ETFHoldingsPage | null>(null)
const diff = ref<ETFHoldingsDiff | null>(null)
const weightEvolution = ref<ETFHoldingsWeightEvolution | null>(null)
const transitionTimeline = ref<ETFHoldingsTransitionTimeline | null>(null)
const overlapSummary = ref<ETFHoldingsOverlapSummary | null>(null)
const overlapMatrix = ref<ETFHoldingsOverlapMatrix | null>(null)
const snapshotOptions = ref<ETFHoldingsDate[]>([])
const selectedHolding = ref<ETFHolding | null>(null)
const profileSearch = ref('')
const holdingsSearch = ref('')
const sortMode = ref<'position' | 'weight' | 'market_value' | 'shares' | 'symbol' | 'name' | 'resolved'>('weight')
const sortDirection = ref<'asc' | 'desc'>('desc')
const limit = ref(100)
const offset = ref(0)
const selectedSnapshotId = ref('')
const compareSnapshotId = ref('')
const selectedOverlapSymbols = ref<string[]>([])
const overlapIssuer = ref('')
const overlapFundFamily = ref('')
const overlapQuery = ref('')
const overlapFamilyLimit = ref(25)
const loadingProfiles = ref(false)
const loadingOverlap = ref(false)
const loadError = ref('')

const selectedCapability = computed(() => selectedProfile.value?.holdings_capability ?? null)

function capabilityLabel(capability: ETFHoldingsCapability | null | undefined): string {
  if (!capability) return 'Capability not checked'
  return capability.availability.replace(/_/g, ' ')
}

function capabilityClass(capability: ETFHoldingsCapability | null | undefined): string {
  return `capability--${capability?.availability || 'unknown'}`
}

function capabilityFailureLabel(failureClass: string | null | undefined): string {
  return String(failureClass || '').replace(/_/g, ' ')
}

const pageEnd = computed(() => {
  if (!page.value) return 0
  return Math.min(page.value.total, page.value.offset + page.value.holdings.length)
})

let profileLoadSeq = 0
let holdingsLoadSeq = 0
let diffLoadSeq = 0
let evolutionLoadSeq = 0
let transitionLoadSeq = 0

const compareOptions = computed(() =>
  snapshotOptions.value.filter(option => String(option.snapshot_id) !== selectedSnapshotId.value)
)

const overlapCandidates = computed(() =>
  (profiles.value ?? []).filter(profile => profile.symbol !== selectedProfile.value?.symbol)
)
const canCompareOverlapFamily = computed(() =>
  Boolean(
    overlapIssuer.value.trim()
    || overlapFundFamily.value.trim()
    || overlapQuery.value.trim()
  )
)

async function loadProfiles(search = profileSearch.value.trim(), autoSelectFirst = !selectedProfile.value) {
  const seq = ++profileLoadSeq
  loadingProfiles.value = true
  loadError.value = ''
  try {
    const loaded = await api.get<ETFProfile[]>('/etf-holdings', {
      q: search || undefined,
    })
    const normalized = Array.isArray(loaded) ? loaded : []
    if (seq !== profileLoadSeq) return
    profiles.value = normalized
    if (autoSelectFirst && !selectedProfile.value && normalized.length) {
      await selectProfile(normalized[0])
    }
    return normalized
  } catch (error) {
    if (seq !== profileLoadSeq) return
    loadError.value = error instanceof Error ? error.message : 'Could not load ETF profiles.'
    profiles.value = []
    return []
  } finally {
    if (seq === profileLoadSeq) loadingProfiles.value = false
  }
}

function resetWorkspaceSelection() {
  selectedProfile.value = null
  page.value = null
  diff.value = null
  weightEvolution.value = null
  transitionTimeline.value = null
  overlapSummary.value = null
  overlapMatrix.value = null
  snapshotOptions.value = []
  selectedHolding.value = null
  selectedSnapshotId.value = ''
  compareSnapshotId.value = ''
}

async function selectProfileFromSearch(symbol: string, result?: ETFSearchResult) {
  const normalized = symbol.trim().toUpperCase()
  if (!normalized) return
  profileSearch.value = normalized
  loadError.value = ''

  try {
    const bootstrap = await api.post<ETFProfileBootstrapResponse>(
      `/etf-holdings/${encodeURIComponent(normalized)}/bootstrap`,
      {
        name: result?.name || undefined,
      },
    )

    await loadProfiles('', false)
    const matchedProfile = profiles.value.find(
      profile => profile.id === bootstrap.profile.id || profile.symbol.toUpperCase() === normalized,
    ) ?? bootstrap.profile

    if (bootstrap.latest_snapshot || matchedProfile.latest_snapshot_id != null) {
      await selectProfile(matchedProfile)
      if (bootstrap.message && !bootstrap.refresh_succeeded) {
        loadError.value = bootstrap.message
      }
      return
    }

    resetWorkspaceSelection()
    selectedProfile.value = matchedProfile
    overlapIssuer.value = matchedProfile.issuer || ''
    overlapFundFamily.value = matchedProfile.fund_family || ''
    loadError.value = bootstrap.message
      || `No ETF holdings snapshot is stored yet for ${normalized}.`
  } catch (error) {
    resetWorkspaceSelection()
    loadError.value = error instanceof Error ? error.message : `Could not prepare ETF holdings for ${normalized}.`
  }
}

async function selectProfile(profile: ETFProfile) {
  if (profile.latest_snapshot_id == null) {
    try {
      const bootstrap = await api.post<ETFProfileBootstrapResponse>(
        `/etf-holdings/${encodeURIComponent(profile.symbol)}/bootstrap`,
        {
          name: profile.name || undefined,
        },
      )
      const bootstrappedProfile = bootstrap.profile
      const index = profiles.value.findIndex(item => item.id === bootstrappedProfile.id)
      if (index >= 0) {
        profiles.value.splice(index, 1, bootstrappedProfile)
      } else {
        profiles.value = [bootstrappedProfile, ...profiles.value]
      }
      if (bootstrap.message && !bootstrap.refresh_succeeded) {
        loadError.value = bootstrap.message
      }
      profile = bootstrappedProfile
      if (profile.latest_snapshot_id == null) {
        resetWorkspaceSelection()
        selectedProfile.value = profile
        overlapIssuer.value = profile.issuer || ''
        overlapFundFamily.value = profile.fund_family || ''
        loadError.value = bootstrap.message
          || `No ETF holdings snapshot is stored yet for ${profile.symbol}.`
        return
      }
    } catch (error) {
      loadError.value = error instanceof Error
        ? error.message
        : `Could not prepare ETF holdings for ${profile.symbol}.`
      return
    }
  }
  selectedProfile.value = profile
  holdingsSearch.value = ''
  offset.value = 0
  selectedSnapshotId.value = ''
  compareSnapshotId.value = ''
  overlapSummary.value = null
  overlapMatrix.value = null
  selectedOverlapSymbols.value = overlapCandidates.value.slice(0, 3).map(candidate => candidate.symbol)
  overlapIssuer.value = profile.issuer || ''
  overlapFundFamily.value = profile.fund_family || ''
  overlapQuery.value = ''
  await loadSnapshotOptions()
  await loadHoldings()
  await loadDiff()
  await loadWeightEvolution()
  await loadTransitionTimeline()
}

async function reloadHoldings() {
  offset.value = 0
  await loadHoldings()
}

async function reloadForSnapshotChange() {
  offset.value = 0
  await loadHoldings()
  if (!compareOptions.value.some(option => String(option.snapshot_id) === compareSnapshotId.value)) {
    compareSnapshotId.value = compareOptions.value[0] ? String(compareOptions.value[0].snapshot_id) : ''
  }
  await loadDiff()
}

async function loadSnapshotOptions() {
  const profile = selectedProfile.value
  if (!profile) return
  const loaded = await api.get<ETFHoldingsDate[]>(`/etf-holdings/${encodeURIComponent(profile.symbol)}/dates`)
  snapshotOptions.value = loaded
  if (!loaded.length) {
    selectedSnapshotId.value = ''
    compareSnapshotId.value = ''
    return
  }
  const selectedStillExists = loaded.some(option => String(option.snapshot_id) === selectedSnapshotId.value)
  if ((!selectedSnapshotId.value || !selectedStillExists) && loaded[0]) {
    selectedSnapshotId.value = String(loaded[0].snapshot_id)
  }
  const compareStillExists = loaded.some(option => String(option.snapshot_id) === compareSnapshotId.value)
  if (!compareStillExists) {
    compareSnapshotId.value = ''
  }
  if (!compareSnapshotId.value && loaded[1]) {
    compareSnapshotId.value = String(loaded[1].snapshot_id)
  }
}

async function loadHoldings() {
  const profile = selectedProfile.value
  if (!profile) return
  if (!selectedSnapshotId.value) {
    page.value = null
    selectedHolding.value = null
    return
  }
  const seq = ++holdingsLoadSeq
  loadError.value = ''
  try {
    const loaded = await api.get<ETFHoldingsPage>(`/etf-holdings/${encodeURIComponent(profile.symbol)}/holdings`, {
      q: holdingsSearch.value.trim() || undefined,
      snapshot_id: selectedSnapshotId.value || undefined,
      sort: sortMode.value,
      direction: sortDirection.value,
      limit: limit.value,
      offset: offset.value,
    })
    if (seq !== holdingsLoadSeq) return
    page.value = loaded
    selectedHolding.value = loaded.holdings[0] ?? null
  } catch (error) {
    if (seq !== holdingsLoadSeq) return
    page.value = null
    selectedHolding.value = null
    loadError.value = error instanceof Error ? error.message : 'Could not load holdings.'
  }
}

async function loadDiff() {
  const profile = selectedProfile.value
  if (!profile || !selectedSnapshotId.value || !compareSnapshotId.value) {
    diff.value = null
    return
  }
  const seq = ++diffLoadSeq
  try {
    const loaded = await api.get<ETFHoldingsDiff>(`/etf-holdings/${encodeURIComponent(profile.symbol)}/diff`, {
      left_snapshot_id: compareSnapshotId.value,
      right_snapshot_id: selectedSnapshotId.value,
    })
    if (seq !== diffLoadSeq) return
    diff.value = loaded
  } catch {
    if (seq !== diffLoadSeq) return
    diff.value = null
  }
}

async function loadWeightEvolution() {
  const profile = selectedProfile.value
  if (!profile) {
    weightEvolution.value = null
    return
  }
  const seq = ++evolutionLoadSeq
  try {
    const loaded = await api.get<ETFHoldingsWeightEvolution>(
      `/etf-holdings/${encodeURIComponent(profile.symbol)}/weight-evolution`,
      { limit: 8 },
    )
    if (seq !== evolutionLoadSeq) return
    weightEvolution.value = loaded
  } catch {
    if (seq !== evolutionLoadSeq) return
    weightEvolution.value = null
  }
}

async function loadTransitionTimeline() {
  const profile = selectedProfile.value
  if (!profile) {
    transitionTimeline.value = null
    return
  }
  const seq = ++transitionLoadSeq
  try {
    const loaded = await api.get<ETFHoldingsTransitionTimeline>(
      `/etf-holdings/${encodeURIComponent(profile.symbol)}/transitions`,
      { limit: 8 },
    )
    if (seq !== transitionLoadSeq) return
    transitionTimeline.value = loaded
  } catch {
    if (seq !== transitionLoadSeq) return
    transitionTimeline.value = null
  }
}

async function loadOverlapSummary() {
  const profile = selectedProfile.value
  if (!profile || !selectedOverlapSymbols.value.length) {
    overlapSummary.value = null
    overlapMatrix.value = null
    return
  }
  loadingOverlap.value = true
  try {
    const request = {
      etf_symbols: [profile.symbol, ...selectedOverlapSymbols.value],
      snapshot_date: page.value?.snapshot.composition_date,
      point_in_time: true,
      top_n: 5,
    }
    const [summary, matrix] = await Promise.all([
      api.post<ETFHoldingsOverlapSummary>('/etf-holdings/overlap-summary', request),
      api.post<ETFHoldingsOverlapMatrix>('/etf-holdings/overlap-matrix', {
        ...request,
        metric: 'jaccard',
      }),
    ])
    overlapSummary.value = summary
    overlapMatrix.value = matrix
  } catch {
    overlapSummary.value = null
    overlapMatrix.value = null
  } finally {
    loadingOverlap.value = false
  }
}

async function loadOverlapFamilyMatrix() {
  const profile = selectedProfile.value
  if (!profile || !canCompareOverlapFamily.value) {
    overlapMatrix.value = null
    return
  }
  loadingOverlap.value = true
  try {
    overlapSummary.value = null
    overlapMatrix.value = await api.post<ETFHoldingsOverlapMatrix>(
      '/etf-holdings/overlap-matrix',
      {
        etf_symbols: [profile.symbol],
        snapshot_date: page.value?.snapshot.composition_date,
        point_in_time: true,
        top_n: 5,
        metric: 'jaccard',
        issuer: overlapIssuer.value.trim() || undefined,
        fund_family: overlapFundFamily.value.trim() || undefined,
        q: overlapQuery.value.trim() || undefined,
        limit: overlapFamilyLimit.value,
      },
    )
  } catch {
    overlapMatrix.value = null
  } finally {
    loadingOverlap.value = false
  }
}

async function nextPage() {
  if (!page.value?.has_next) return
  offset.value += limit.value
  await loadHoldings()
}

async function previousPage() {
  offset.value = Math.max(0, offset.value - limit.value)
  await loadHoldings()
}

function numeric(value: number | string | null | undefined) {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

function formatWeight(value: number | string | null | undefined) {
  if (value == null || value === '') return '—'
  return `${(numeric(value) * 100).toFixed(2)}%`
}

function formatSignedWeight(value: number | string | null | undefined) {
  if (value == null || value === '') return '—'
  const n = numeric(value) * 100
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`
}

function formatPercentValue(value: number | string | null | undefined) {
  if (value == null || value === '') return '—'
  return `${(numeric(value) * 100).toFixed(1)}%`
}

function percentOffset(value: number | string | null | undefined) {
  return Math.max(0, Math.min(100, numeric(value) * 100))
}

function overlapCellStyle(cell: ETFHoldingsOverlapMatrixCell) {
  const alpha = 0.18 + (percentOffset(cell.jaccard_overlap) / 100) * 0.72
  return {
    background: `rgba(86, 180, 255, ${alpha})`,
  }
}

function formatQuantity(value: number | string | null | undefined) {
  if (value == null || value === '') return '—'
  return numeric(value).toLocaleString(undefined, { maximumFractionDigits: 4 })
}

function formatMoney(value: number | string | null | undefined, currency?: string | null) {
  if (value == null || value === '') return '—'
  const amount = numeric(value).toLocaleString(undefined, { maximumFractionDigits: 2 })
  return currency ? `${currency} ${amount}` : amount
}

function isSyntheticHoldingSymbol(value: string | null | undefined) {
  return String(value || '').toUpperCase().startsWith('HOLDING-')
}

function holdingSymbol(row: ETFHolding) {
  const constituent = isSyntheticHoldingSymbol(row.constituent_symbol) ? '' : row.constituent_symbol
  return constituent || row.reported_symbol || '—'
}

function holdingName(row: ETFHolding) {
  return row.constituent_name || row.reported_name || '—'
}

function isReferenceHolding(row: ETFHolding) {
  return row.row_type !== 'security' || ['cash', 'currency', 'collateral'].includes(row.holding_type)
}

function isTradableHolding(row: ETFHolding) {
  return row.is_resolved && !isReferenceHolding(row)
}

function statusLabel(row: ETFHolding) {
  if (isTradableHolding(row)) return 'ready'
  if (isReferenceHolding(row)) return 'reference'
  return 'needs match'
}

function statusClass(row: ETFHolding) {
  return {
    'status-ok': isTradableHolding(row),
    'status-warn': !isTradableHolding(row) && !isReferenceHolding(row),
    'status-muted': isReferenceHolding(row),
  }
}

function openableSymbol(row: ETFHolding) {
  if (!selectedCapability.value?.identity_verified
    || selectedCapability.value.availability !== 'current'
    || !selectedCapability.value.usable_for_current_analysis) {
    return ''
  }
  if (!isTradableHolding(row)) return ''
  const constituent = isSyntheticHoldingSymbol(row.constituent_symbol) ? '' : row.constituent_symbol
  return constituent || row.reported_symbol || ''
}

function venueLabel(row: ETFHolding) {
  return [row.exchange, row.country].filter(Boolean).join(' · ') || '—'
}

function diffStatusClass(status: string) {
  return {
    'status-added': status === 'added',
    'status-removed': status === 'removed',
    'status-changed': status === 'changed',
  }
}

function diffDeltaClass(value: number | string | null | undefined) {
  const n = numeric(value)
  return n > 0 ? 'status-ok' : n < 0 ? 'status-bad' : ''
}

function moverCountLabel(count: number) {
  return `${count} ${count === 1 ? 'mover' : 'movers'}`
}

function transitionTopMovers(transition: ETFHoldingsTransition) {
  return [
    ...transition.largest_additions,
    ...transition.largest_removals,
    ...transition.largest_reweights,
  ].slice(0, 4)
}

function transitionMoverLabel(row: ETFHoldingsDiffRow) {
  if (row.status === 'added') return `+${formatWeight(row.weight_after)}`
  if (row.status === 'removed') return `-${formatWeight(row.weight_before)}`
  return formatSignedWeight(row.weight_delta)
}

function toggleOverlapSymbol(symbol: string) {
  overlapSummary.value = null
  overlapMatrix.value = null
  if (selectedOverlapSymbols.value.includes(symbol)) {
    selectedOverlapSymbols.value = selectedOverlapSymbols.value.filter(item => item !== symbol)
    return
  }
  selectedOverlapSymbols.value = [...selectedOverlapSymbols.value, symbol]
}

function evolutionDotOffset(series: ETFHoldingsWeightEvolutionSeries, value: number | string | null | undefined) {
  const min = numeric(series.min_weight)
  const max = numeric(series.max_weight)
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return 50
  return Math.max(0, Math.min(100, ((numeric(value) - min) / (max - min)) * 100))
}

function evolutionDotClass(series: ETFHoldingsWeightEvolutionSeries, value: number | string | null | undefined) {
  const current = numeric(value)
  const first = numeric(series.first_weight)
  return {
    'evolution-dot--up': current > first,
    'evolution-dot--down': current < first,
  }
}

function openChart(row: ETFHolding) {
  const symbol = openableSymbol(row)
  if (symbol) router.push(`/chart/${encodeURIComponent(symbol)}`)
}

onMounted(loadProfiles)
</script>

<style scoped>
.holdings-view {
  height: 100%;
  display: grid;
  grid-template-columns: minmax(260px, 320px) minmax(0, 1fr);
  background: #080808;
  color: #d4d4d4;
  font-size: 12px;
}
.holdings-sidebar {
  border-right: 1px solid #171717;
  padding: 12px;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.sidebar-head h1,
.panel-title-row h2 {
  color: #f0f0f0;
  font-size: 15px;
  line-height: 1.1;
  letter-spacing: 0;
  margin: 0;
}
.sidebar-head p,
.panel-title-row p,
.profile-card span,
.profile-card em {
  color: #8d8d8d;
  font-size: 11px;
  line-height: 1.4;
}
.sidebar-head p,
.panel-title-row p {
  margin: 6px 0 0;
}
.search-field,
.toolbar label {
  display: grid;
  gap: 6px;
  color: #898989;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.search-field input,
.toolbar input,
.toolbar select {
  min-height: 34px;
  border: 1px solid #262626;
  border-radius: 6px;
  background: #101010;
  color: #d6d6d6;
  font: inherit;
  padding: 7px 10px;
}
.profile-list {
  min-height: 0;
  overflow: auto;
  display: grid;
  align-content: start;
  gap: 8px;
}
.profile-card {
  border: 1px solid #1d1d1d;
  border-radius: 8px;
  background: #101010;
  color: inherit;
  text-align: left;
  padding: 10px;
  display: grid;
  gap: 4px;
  cursor: pointer;
  font: inherit;
}
.profile-card:hover,
.profile-card--active {
  border-color: #25679f;
  background: #0d1820;
}
.profile-card__top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}
.profile-card__top b {
  color: #f2f2f2;
  font-size: 12px;
}
.profile-card small,
.profile-card em {
  font-style: normal;
  font-size: 10px;
}
.capability-pill {
  border: 1px solid #3a3a3a;
  border-radius: 999px;
  padding: 2px 6px;
  text-transform: capitalize;
}
.capability--current { color: #8fe3a1; border-color: #2b6b3a; }
.capability--degraded { color: #f0cb7a; border-color: #806326; }
.capability--stale,
.capability--unavailable { color: #ff9d9d; border-color: #693333; }
.capability--not_applicable,
.capability--unknown { color: #b5b5b5; border-color: #4a4a4a; }
.holdings-main {
  min-width: 0;
  min-height: 0;
  overflow: auto;
  padding: 16px;
}
.workspace-panel {
  min-height: 100%;
  border: 1px solid #1d1d1d;
  border-radius: 8px;
  background: #0d0d0d;
  padding: 16px;
  display: grid;
  align-content: start;
  gap: 12px;
}
.panel-title-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}
.panel-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
}
.panel-meta span {
  border: 1px solid #23384b;
  border-radius: 999px;
  color: #9ccdf7;
  background: #0e1720;
  padding: 4px 8px;
  font-size: 10px;
}
.toolbar {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) 190px 160px 190px;
  gap: 8px;
}
.holdings-browser {
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(300px, 0.38fr);
  gap: 14px;
}
.holdings-table {
  border: 1px solid #1b1b1b;
  border-radius: 8px;
  overflow: auto;
  max-height: 58vh;
}
.holding-row {
  width: 100%;
  display: grid;
  grid-template-columns: 120px minmax(220px, 1fr) 100px 130px 120px 110px;
  gap: 10px;
  align-items: center;
  border: 0;
  border-bottom: 1px solid #181818;
  background: transparent;
  color: #b7b7b7;
  font: inherit;
  text-align: left;
  padding: 8px 10px;
}
button.holding-row {
  cursor: pointer;
}
button.holding-row:hover,
.holding-row--selected {
  background: #111b22;
}
.holding-row--head {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #101010;
  color: #777;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.holding-row b {
  color: #f1f1f1;
}
.holding-row small {
  display: block;
  color: #777;
  font-size: 9px;
  text-transform: uppercase;
}
.status-ok { color: #75d894; }
.status-warn { color: #f0c66a; }
.holding-detail {
  border: 1px solid #1e2c38;
  border-radius: 8px;
  background: #0b1117;
  padding: 12px;
  align-self: start;
}
.detail-title {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  border-bottom: 1px solid #1e2c38;
  padding-bottom: 12px;
}
.detail-title small,
.holding-detail dt {
  color: #7f8996;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.detail-title h3 {
  color: #f2f2f2;
  font-size: 16px;
  margin-top: 4px;
}
.detail-title p {
  color: #9ca3af;
  font-size: 11px;
  margin-top: 2px;
}
.detail-title button,
.pager button {
  border: 1px solid #284562;
  border-radius: 6px;
  background: #102033;
  color: #9bd1ff;
  cursor: pointer;
  font: inherit;
  padding: 7px 10px;
}
.detail-title button:disabled,
.pager button:disabled {
  opacity: 0.4;
  cursor: default;
}
.holding-detail dl {
  margin: 12px 0 0;
  display: grid;
  gap: 8px;
}
.holding-detail div {
  min-width: 0;
}
.holding-detail dd {
  margin: 4px 0 0;
  color: #d8dde5;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}
.diff-panel {
  border: 1px solid #1b1b1b;
  border-radius: 8px;
  background: #0c0f14;
  padding: 12px;
  display: grid;
  gap: 10px;
}
.evolution-panel {
  border: 1px solid #1b1b1b;
  border-radius: 8px;
  background: #0c0f14;
  padding: 12px;
  display: grid;
  gap: 10px;
}
.transition-panel {
  border: 1px solid #1b1b1b;
  border-radius: 8px;
  background: #0c0f14;
  padding: 12px;
  display: grid;
  gap: 10px;
}
.overlap-panel {
  border: 1px solid #1b1b1b;
  border-radius: 8px;
  background: #0c0f14;
  padding: 12px;
  display: grid;
  gap: 10px;
}
.research-action {
  border: 1px solid #284562;
  border-radius: 6px;
  background: #102033;
  color: #9bd1ff;
  cursor: pointer;
  font: inherit;
  padding: 7px 10px;
}
.research-action:disabled {
  opacity: 0.45;
  cursor: default;
}
.research-action--ghost {
  background: #101418;
  border-color: #2a3038;
  color: #c7d0dc;
}
.overlap-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}
.overlap-family-controls {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 10px;
  align-items: end;
}
.overlap-family-controls label {
  display: grid;
  gap: 5px;
}
.overlap-family-controls span {
  color: #7e8896;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.overlap-family-controls input {
  border: 1px solid #252b33;
  border-radius: 6px;
  background: #0b0e12;
  color: #dce4ed;
  font: inherit;
  min-width: 0;
  padding: 7px 9px;
}
.overlap-picker {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.overlap-target {
  border: 1px solid #222d3a;
  border-radius: 999px;
  background: #101720;
  color: #9aa6b5;
  display: inline-flex;
  gap: 6px;
  align-items: center;
  padding: 6px 9px;
  cursor: pointer;
  font: inherit;
}
.overlap-target b {
  color: #e9eef5;
}
.overlap-target span {
  font-size: 10px;
  color: #7e8896;
}
.overlap-target--active {
  border-color: #25679f;
  background: #0f2435;
  color: #9bd1ff;
}
.overlap-matrix {
  border: 1px solid #1a2430;
  border-radius: 8px;
  background: #0e1319;
  padding: 10px;
  display: grid;
  gap: 12px;
  overflow-x: auto;
}
.overlap-matrix__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: baseline;
}
.overlap-matrix__head strong {
  color: #f0f0f0;
  font-size: 12px;
}
.overlap-matrix__head span {
  color: #7e8896;
  font-size: 10px;
}
.overlap-grid {
  --matrix-size: 1;
  display: grid;
  grid-template-columns: 54px repeat(var(--matrix-size), minmax(76px, 1fr));
  gap: 6px;
  min-width: max-content;
}
.overlap-grid b,
.overlap-grid__cell,
.overlap-grid__corner {
  min-height: 38px;
  border-radius: 8px;
}
.overlap-grid b {
  background: #101720;
  color: #a9b4c3;
  display: grid;
  place-items: center;
  font-size: 10px;
}
.overlap-grid__cell {
  color: #e9eef5;
  display: grid;
  place-items: center;
  font-size: 10px;
  border: 1px solid rgba(123, 196, 255, 0.22);
}
.overlap-grid__cell--self {
  color: #9bd1ff;
  outline: 1px solid rgba(155, 209, 255, 0.35);
}
.overlap-matrix__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}
.overlap-matrix__summary span {
  border: 1px solid #222d3a;
  border-radius: 999px;
  background: #101720;
  color: #8f9aaa;
  padding: 4px 7px;
  font-size: 10px;
}
.overlap-matrix__summary b {
  color: #e9eef5;
  margin-right: 5px;
}
.overlap-results {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 10px;
}
.overlap-card {
  border: 1px solid #1a2430;
  border-radius: 8px;
  background: #0e1319;
  padding: 10px;
  display: grid;
  gap: 10px;
}
.overlap-card__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: baseline;
}
.overlap-card__head strong {
  color: #f0f0f0;
  font-size: 12px;
}
.overlap-card__head strong span {
  color: #6f7a88;
  margin: 0 4px;
}
.overlap-card__head b {
  color: #9ccdf7;
  font-size: 11px;
  white-space: nowrap;
}
.overlap-track {
  border: 1px solid #1c2834;
  border-radius: 999px;
  background: #101720;
  height: 10px;
  overflow: hidden;
}
.overlap-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #2f82c8, #73d99a);
}
.overlap-card__stats,
.overlap-shared {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}
.overlap-card__stats span,
.overlap-shared span {
  border: 1px solid #222d3a;
  border-radius: 999px;
  background: #101720;
  padding: 4px 7px;
  color: #9aa6b5;
  font-size: 10px;
}
.overlap-shared b {
  color: #e9eef5;
  margin-right: 5px;
}
.overlap-shared em {
  color: #75d894;
  font-style: normal;
}
.diff-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}
.diff-head h3 {
  color: #f1f1f1;
  font-size: 13px;
  margin: 0;
}
.diff-head p,
.diff-picker span {
  color: #8b8b8b;
  font-size: 11px;
}
.diff-picker label {
  display: grid;
  gap: 6px;
}
.diff-picker select {
  min-height: 34px;
  border: 1px solid #262f3b;
  border-radius: 6px;
  background: #10151c;
  color: #d6d6d6;
  font: inherit;
  padding: 7px 9px;
}
.diff-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.diff-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}
.metric-card {
  border: 1px solid #1b2430;
  border-radius: 8px;
  background: #0d1218;
  padding: 10px;
  display: grid;
  gap: 6px;
}
.metric-card small,
.metric-card span {
  color: #8f98a5;
  font-size: 10px;
}
.metric-card strong {
  color: #f0f0f0;
  font-size: 14px;
}
.metric-sep {
  color: #6e7682;
}
.diff-highlights {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.highlight-card {
  border: 1px solid #1b2430;
  border-radius: 8px;
  background: #0d1218;
  padding: 10px;
  display: grid;
  align-content: start;
  gap: 8px;
}
.highlight-card header {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}
.highlight-card h4 {
  color: #f0f0f0;
  font-size: 12px;
  margin: 0;
}
.highlight-card header span {
  color: #8f98a5;
  font-size: 10px;
}
.highlight-row {
  border: 1px solid #1d2734;
  border-radius: 8px;
  background: #0f141b;
  color: inherit;
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  padding: 8px 9px;
  font: inherit;
  text-align: left;
}
.highlight-row b {
  color: #f0f0f0;
}
.highlight-row small {
  display: block;
  color: #808996;
  font-size: 10px;
}
.highlight-row strong {
  font-size: 12px;
}
.diff-chip {
  border: 1px solid #2a3340;
  border-radius: 999px;
  padding: 4px 8px;
  color: #aeb8c5;
  font-size: 10px;
}
.diff-chip--added {
  border-color: #305b40;
  color: #7fd998;
  background: #0f1b14;
}
.diff-chip--removed {
  border-color: #633739;
  color: #f1999e;
  background: #1c1012;
}
.diff-chip--changed {
  border-color: #5c4f2d;
  color: #f0ca6a;
  background: #19150a;
}
.diff-table {
  border: 1px solid #1a1f27;
  border-radius: 8px;
  overflow: auto;
  max-height: 360px;
}
.diff-row {
  display: grid;
  grid-template-columns: 95px 110px minmax(180px, 1fr) 90px 90px 90px;
  gap: 10px;
  align-items: center;
  padding: 8px 10px;
  border-bottom: 1px solid #181d24;
  color: #b7b7b7;
}
.diff-row--head {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #101010;
  color: #777;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.diff-row b {
  color: #f0f0f0;
}
.evolution-list {
  display: grid;
  gap: 8px;
}
.transition-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 10px;
}
.transition-card {
  border: 1px solid #1a2430;
  border-radius: 8px;
  background: #0e1319;
  padding: 10px;
  display: grid;
  gap: 10px;
}
.transition-card__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: baseline;
}
.transition-card__head strong {
  color: #f0f0f0;
  font-size: 12px;
}
.transition-card__head strong span {
  color: #6f7a88;
  margin: 0 4px;
}
.transition-card__head b {
  color: #9ccdf7;
  font-size: 11px;
  white-space: nowrap;
}
.transition-metrics,
.transition-movers {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}
.transition-metrics span,
.transition-movers span {
  border: 1px solid #222d3a;
  border-radius: 999px;
  background: #101720;
  padding: 4px 7px;
  font-size: 10px;
}
.transition-movers b {
  color: #e9eef5;
  margin-right: 5px;
}
.transition-movers em {
  font-style: normal;
}
.evolution-row {
  border: 1px solid #1a2430;
  border-radius: 8px;
  background: #0e1319;
  display: grid;
  grid-template-columns: minmax(160px, 0.28fr) minmax(180px, 1fr) 160px;
  gap: 12px;
  align-items: center;
  padding: 10px;
}
.evolution-row__label {
  min-width: 0;
}
.evolution-row__label strong {
  color: #f1f1f1;
  display: block;
}
.evolution-row__label span {
  color: #86909e;
  display: block;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.evolution-track {
  position: relative;
  height: 16px;
  border-radius: 999px;
  background: linear-gradient(90deg, #2b1519, #15181f 48%, #102219);
  border: 1px solid #1c2834;
}
.evolution-track::before {
  content: "";
  position: absolute;
  inset: 50% 0 auto;
  height: 1px;
  background: #2b3542;
}
.evolution-dot {
  position: absolute;
  top: 50%;
  width: 10px;
  height: 10px;
  border-radius: 999px;
  transform: translate(-50%, -50%);
  background: #9aa6b5;
  border: 1px solid #d2d8e0;
  box-shadow: 0 0 0 2px #0e1319;
}
.evolution-dot--up {
  background: #75d894;
  border-color: #b8f3c6;
}
.evolution-dot--down {
  background: #f1999e;
  border-color: #ffc7cb;
}
.evolution-row__meta {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 8px;
  align-items: center;
  color: #8f98a5;
  font-size: 11px;
  text-align: right;
}
.evolution-row__meta strong {
  color: #f0f0f0;
  font-size: 12px;
}
.status-added { color: #7fd998; }
.status-removed { color: #f1999e; }
.status-changed { color: #f0ca6a; }
.status-bad { color: #f1999e; }
.pager span,
.state-line,
.empty-state,
.notice {
  color: #888;
  font-size: 11px;
}
.notice--error {
  border: 1px solid #693333;
  border-radius: 8px;
  color: #ff9d9d;
  background: #1b0f0f;
  padding: 10px 12px;
}
.notice--capability {
  border: 1px solid #806326;
  border-radius: 8px;
  color: #ddc58d;
  background: #1b160d;
  padding: 10px 12px;
  line-height: 1.5;
}
.notice--capability strong {
  color: #f0d493;
  margin-right: 4px;
}
.notice--capability.capability--unavailable,
.notice--capability.capability--stale {
  border-color: #693333;
  color: #ffb2b2;
  background: #1b0f0f;
}
.notice--capability .capability-next-action {
  display: block;
  color: #b9c6d8;
}
.notice--capability .capability-failure-class {
  display: block;
  color: #f0c66a;
}
.empty-state {
  border: 1px dashed #292929;
  border-radius: 8px;
  padding: 14px;
}
@media (max-width: 1100px) {
  .holdings-view {
    grid-template-columns: 1fr;
  }
  .holdings-sidebar {
    max-height: 280px;
    border-right: 0;
    border-bottom: 1px solid #171717;
  }
  .toolbar,
  .holdings-browser {
    grid-template-columns: 1fr;
  }
  .diff-metrics,
  .diff-highlights {
    grid-template-columns: 1fr;
  }
  .diff-head {
    grid-template-columns: 1fr;
    display: grid;
  }
  .diff-row {
    grid-template-columns: 90px 100px minmax(120px, 1fr);
  }
  .evolution-row {
    grid-template-columns: 1fr;
  }
  .evolution-row__meta {
    text-align: left;
  }
  .diff-row span:nth-child(n + 4) {
    display: none;
  }
  .holding-row {
    grid-template-columns: 95px minmax(160px, 1fr) 90px;
  }
  .holding-row span:nth-child(n + 4) {
    display: none;
  }
}
</style>
