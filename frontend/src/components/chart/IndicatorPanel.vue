<template>
  <div :class="['side-panel', { 'side-panel--collapsed': !isPanelOpen }]" :style="isPanelOpen && props.panelWidth ? { width: `${props.panelWidth}px` } : undefined">
    <!-- Collapse toggle strip -->
    <button
      class="panel-toggle"
      :title="isPanelOpen ? 'Hide panel' : 'Show panel'"
      @click="isPanelOpen = !isPanelOpen"
    >{{ isPanelOpen ? '›' : '‹' }}</button>

    <div v-show="isPanelOpen" class="panel-body">

    <!-- ── Instrument info ───────────────────────────────────────────────── -->
    <InstrumentInfoPanel
      :instrument="chartStore.instrument ?? null"
      :current-price="chartStore.bars.length ? chartStore.bars[chartStore.bars.length - 1].close : null"
      :session-high="sessionRange?.high ?? null"
      :session-low="sessionRange?.low ?? null"
      :session-high-time="sessionRange?.highTime ?? null"
      :session-low-time="sessionRange?.lowTime ?? null"
      @select="symbol => emit('selectSymbol', symbol)"
    />

    <!-- ── Watchlists membership ─────────────────────────────────────────── -->
    <div v-if="membership !== null" class="section" :class="{ collapsed: !watchlistsOpen }">
      <div class="section-header" @click="watchlistsOpen = !watchlistsOpen">
        <span class="section-title">Watchlists</span>
        <span class="section-count">{{ membership!.watchlists.length }}</span>
        <span class="section-chevron">{{ watchlistsOpen ? '▾' : '▸' }}</span>
      </div>
      <Transition name="slide">
        <div class="section-content" v-if="watchlistsOpen">
          <div class="section-body">
            <div
              v-for="wl in membership!.watchlists"
              :key="wl.id"
              class="list-row membership-row"
              @click="onWatchlistClick(wl.id)"
            >
              <span class="mem-icon">☰</span>
              <span class="row-name">{{ wl.name }}</span>
              <span v-if="wl.is_managed" class="mem-badge">managed</span>
            </div>
            <div v-if="!membership!.watchlists.length" class="empty-hint">Not in any watchlist</div>
          </div>
        </div>
      </Transition>
    </div>

    <!-- ── Screeners membership ───────────────────────────────────────────── -->
    <div v-if="membership !== null" class="section" :class="{ collapsed: !screenersOpen }">
      <div class="section-header" @click="screenersOpen = !screenersOpen">
        <span class="section-title">Screeners</span>
        <span class="section-count">{{ activeScreeners.length }}</span>
        <span class="section-chevron">{{ screenersOpen ? '▾' : '▸' }}</span>
      </div>
      <Transition name="slide">
        <div class="section-content" v-if="screenersOpen">
          <div class="section-body">
            <div
              v-for="sc in activeScreeners"
              :key="sc.id"
              class="list-row membership-row"
              @click="onScreenerClick(sc.id)"
            >
              <span class="mem-icon">⊞</span>
              <span class="row-name">{{ sc.name }}</span>
            </div>
            <div v-if="!activeScreeners.length" class="empty-hint">No active screener matches</div>
          </div>
        </div>
      </Transition>
    </div>

    <!-- ── Radar detections ─────────────────────────────────────────────── -->
    <div v-if="chartStore.instrument" class="section" :class="{ collapsed: !radarsOpen }">
      <div class="section-header" @click="radarsOpen = !radarsOpen">
        <span class="section-title">Radar</span>
        <span class="section-count">{{ radarStore.chartDetections.length }}</span>
        <span class="section-chevron">{{ radarsOpen ? '▾' : '▸' }}</span>
      </div>
      <Transition name="slide">
        <div class="section-content" v-if="radarsOpen">
          <div class="section-body">
            <div
              v-for="(det, index) in radarStore.chartDetections"
              :key="det.id"
              class="list-row radar-row"
              :class="{
                'row--selected': radarStore.focusedChartDetectionId === det.id,
                'row--hidden': !radarStore.isChartDetectionActive(det.id),
              }"
              @click="radarStore.toggleChartDetection(det.id)"
            >
              <span class="radar-sequence-tag">{{ formatRadarSequenceBadge(det) }}</span>
              <span class="radar-toggle-indicator">{{ radarStore.isChartDetectionActive(det.id) ? '◉' : '○' }}</span>
              <span class="row-name radar-row-main">
                <span class="radar-row-title">{{ formatRadarSetup(det.setup_type) }}</span>
                <span class="radar-row-meta">
                  <span v-if="det.thread_event_index != null || det.thread?.detection_count" class="draw-pane-tag">
                    {{ formatRadarThreadTag(det) }}
                  </span>
                  <span :class="['draw-pane-tag', `draw-pane-tag--${det.state}`]">{{ formatRadarState(det.state) }}</span>
                  <span class="draw-pane-tag">{{ det.score.toFixed(2) }}</span>
                  <span class="draw-pane-tag draw-pane-tag--dim">{{ formatRadarSignalDate(det) }}</span>
                  <span class="draw-pane-tag draw-pane-tag--dim">Recorded {{ formatRadarRecordedDate(det.created_at) }}</span>
                </span>
              </span>
              <HoverTooltip :text="radarTooltipText(det)">
                <button
                  type="button"
                  class="radar-info-btn"
                  :aria-label="`Radar details for ${formatRadarSetup(det.setup_type)}`"
                  @click.stop
                >
                  i
                </button>
              </HoverTooltip>
            </div>
            <div v-if="focusedRadarDetection" class="radar-focus-card">
              <div class="radar-focus-head">
                <span class="radar-focus-title">{{ formatRadarSetup(focusedRadarDetection.setup_type) }}</span>
                <div class="radar-focus-head-meta">
                  <span :class="['draw-pane-tag', `draw-pane-tag--${focusedRadarDetection.state}`]">
                    {{ formatRadarState(focusedRadarDetection.state) }}
                  </span>
                  <span class="draw-pane-tag">{{ focusedRadarDetection.score.toFixed(2) }}</span>
                  <span class="draw-pane-tag draw-pane-tag--dim">{{ formatRadarSignalDate(focusedRadarDetection) }}</span>
                  <span class="draw-pane-tag draw-pane-tag--dim">Recorded {{ formatRadarRecordedDate(focusedRadarDetection.created_at) }}</span>
                </div>
              </div>
              <div class="radar-focus-copy">{{ focusedRadarDetection.summary }}</div>
              <div v-if="focusedRadarRationale.length" class="radar-focus-rationale">
                <div v-for="item in focusedRadarRationale" :key="item" class="radar-focus-rationale-item">{{ item }}</div>
              </div>
              <div class="radar-focus-grid">
                <span class="radar-focus-key">Signal</span>
                <span class="radar-focus-val">{{ formatRadarSignalDate(focusedRadarDetection) }}</span>
                <span class="radar-focus-key">Entry</span>
                <span class="radar-focus-val">{{ formatRadarPrice(focusedRadarDetection.entry_price) }}</span>
                <span class="radar-focus-key">Invalidation</span>
                <span class="radar-focus-val">{{ formatRadarPrice(focusedRadarDetection.invalidation_price) }}</span>
                <span class="radar-focus-key">Target</span>
                <span class="radar-focus-val">{{ formatRadarPrice(focusedRadarDetection.target_price) }}</span>
                <span class="radar-focus-key">Recorded</span>
                <span class="radar-focus-val">{{ formatRadarRecordedDate(focusedRadarDetection.created_at) }}</span>
              </div>
              <div v-if="focusedRadarDetection.thread_history?.length" class="radar-focus-timeline">
                <div
                  v-for="event in focusedRadarDetection.thread_history"
                  :key="event.id"
                  class="radar-focus-event"
                  :class="{ 'radar-focus-event--active': event.id === focusedRadarDetection.id }"
                >
                  <span class="radar-focus-event-seq">#{{ event.thread_event_index ?? '—' }}</span>
                  <span class="radar-focus-event-main">
                    <span class="radar-focus-event-title">{{ formatRadarSetup(event.setup_type) }}</span>
                    <span class="radar-focus-event-meta">
                      {{ formatRadarObservedDate(event.signal_at) }} · {{ formatRadarState(event.state) }}
                    </span>
                  </span>
                </div>
              </div>
            </div>
            <div v-if="!radarStore.chartDetections.length" class="empty-hint">No radar detections for this symbol</div>
          </div>
        </div>
      </Transition>
    </div>

    <!-- ── Indicators section ──────────────────────────────────────────── -->
    <div class="section" :class="{ collapsed: !indicatorsOpen }">
      <div class="section-header" @click="indicatorsOpen = !indicatorsOpen">
        <span class="section-title">Indicators</span>
        <span class="section-count">{{ chartStore.indicators.length }}</span>
        <span class="section-chevron">{{ indicatorsOpen ? '▾' : '▸' }}</span>
      </div>

      <Transition name="slide">
        <div class="section-content" v-if="indicatorsOpen">
          <div class="section-body">
            <div class="ind-list">
              <VueDraggable
                v-model="draggableIndicators"
                handle=".ind-drag-handle"
                :animation="150"
              >
                <div
                  v-for="(ind, i) in draggableIndicators"
                  :key="displayName(ind) + i"
                  class="list-row"
                  :class="{ 'row--selected': i === chartStore.selectedIndicatorIndex, 'row--tf-inactive': !isActiveOnCurrentTf(ind) }"
                  :title="isActiveOnCurrentTf(ind) ? undefined : `Locked to: ${(ind.lockedTimeframes ?? []).join(', ')}`"
                  @click.stop="chartStore.selectIndicator(i)"
                  @dblclick.stop="openIndEditor(i)"
                >
                  <span class="ind-drag-handle" title="Drag to reorder">⠿</span>
                  <span class="color-dot" :style="{ background: ind.style.color }" />
                  <span class="row-name">{{ displayName(ind) }}</span>
                  <span v-if="ind.lockedTimeframes?.length" class="tf-lock-badge" title="Timeframe locked">🔒</span>
                  <div class="row-menu-wrap">
                    <button class="row-btn row-menu-btn" @click.stop="toggleMenu(`ind-${i}`, $event)" title="More">⋯</button>
                    <Teleport to="body">
                      <div v-if="menuOpenId === `ind-${i}`" class="row-dropdown row-dropdown--fixed" :style="rowMenuStyle" @click.stop>
                        <button class="dd-item" @click.stop="openIndEditor(i); closeMenu()">⚙ Settings</button>
                        <button class="dd-item" @click.stop="alertForIndicator(i); closeMenu()">🔔 Create alert</button>
                        <button class="dd-item" @click.stop="toggleIndProjection(i); closeMenu()">
                          {{ ind.showYProjection ? '◉' : '○' }} Y projection
                        </button>
                        <div class="dd-sep" />
                        <button class="dd-item dd-item--danger" @click.stop="chartStore.removeIndicator(i); closeMenu()">✕ Remove</button>
                      </div>
                    </Teleport>
                  </div>
                </div>
              </VueDraggable>
              <div v-if="!chartStore.indicators.length" class="empty-hint">
                No indicators for this symbol
                <button v-if="presetsStore.getDefault()" class="hint-btn" @click="applyDefault">Apply default preset</button>
              </div>
            </div>
          </div>

          <!-- Footer: add button + picker + presets (outside scrollable area) -->
          <div class="add-bar">
            <button class="add-btn" @click="showPicker = !showPicker">+ Add</button>
          </div>
          <div v-if="showPicker" class="picker-dropdown">
            <button
              v-for="t in availableTypes"
              :key="t.type"
              class="picker-item"
              @click="addIndicator(t.type)"
            >{{ t.label }}</button>
          </div>
          <div class="preset-bar">
            <select v-model="selectedPresetId" class="preset-select">
              <option value="">— Preset —</option>
              <option v-for="p in presetsStore.presets" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
            <button class="preset-btn" @click="applyPreset" title="Apply preset">↓</button>
            <button class="preset-btn" @click="saveAsPreset" title="Save as preset">✎</button>
          </div>
        </div>
      </Transition>
    </div>

    <!-- ── Drawings section ────────────────────────────────────────────── -->
    <div class="section section--drawings" :class="{ collapsed: !drawingsOpen }">
      <div class="section-header" @click="drawingsOpen = !drawingsOpen">
        <span class="section-title">Drawings</span>
        <span class="section-count">{{ drawStore.drawings.length }}</span>
        <span class="section-chevron">{{ drawingsOpen ? '▾' : '▸' }}</span>
      </div>

      <Transition name="slide">
        <div class="section-content" v-if="drawingsOpen">
          <div class="section-body">
          <div class="ind-list">
            <VueDraggable
              v-model="draggableDrawings"
              handle=".draw-drag-handle"
              :animation="150"
              @end="onDrawingsReorder"
            >
              <div
                v-for="d in draggableDrawings"
                :key="d.id"
                class="list-row"
                :class="{ 'row--selected': d.id === drawStore.selectedId, 'row--hidden': !d.is_visible }"
                @click="drawStore.selectDrawing(d.id)"
                @dblclick.stop="openDrawEditor(d)"
              >
                <span class="draw-drag-handle" title="Drag to reorder">⠿</span>
                <span class="draw-icon">{{ drawingIcon(d.drawing_type) }}</span>
                <span class="row-name">
                  {{ drawingLabel(d) }}
                  <span v-if="d.indicator_key" class="draw-pane-tag">{{ d.indicator_key.toUpperCase() }}</span>
                </span>
                <div class="row-menu-wrap">
                  <button class="row-btn row-menu-btn" @click.stop="toggleMenu(`draw-${d.id}`, $event)" title="More">⋯</button>
                  <Teleport to="body">
                    <div v-if="menuOpenId === `draw-${d.id}`" class="row-dropdown row-dropdown--fixed" :style="rowMenuStyle" @click.stop>
                      <button class="dd-item" @click.stop="toggleVisible(d); closeMenu()">
                        {{ d.is_visible ? '👁 Hide' : '🚫 Show' }}
                      </button>
                      <button class="dd-item" @click.stop="toggleLock(d); closeMenu()">
                        {{ d.is_locked ? '🔓 Unlock' : '🔒 Lock' }}
                      </button>
                      <button class="dd-item" @click.stop="openDrawEditor(d); closeMenu()">⚙ Edit</button>
                      <template v-if="!['fibonacci_retracement','fibonacci_extension'].includes(d.drawing_type)">
                        <button class="dd-item" @click.stop="drawStore.toggleDrawingProjection(d.id); closeMenu()">
                          {{ drawStore.getDrawingProjection(d.id) ? '◉' : '○' }} Y projection
                        </button>
                      </template>
                      <div class="dd-sep" />
                      <button class="dd-item dd-item--danger" @click.stop="drawStore.deleteDrawing(d.id); closeMenu()">✕ Delete</button>
                    </div>
                  </Teleport>
                </div>
              </div>
            </VueDraggable>
            <div v-if="!drawStore.drawings.length" class="empty-hint">No drawings</div>
          </div>
          </div>
        </div>
      </Transition>
    </div>

    <!-- ── Alerts section ──────────────────────────────────────────── -->
    <div class="section section--alerts" :class="{ collapsed: !alertsOpen }">
      <div class="section-header" @click="alertsOpen = !alertsOpen">
        <span class="section-title">Alerts</span>
        <span class="section-count">{{ instrumentAlerts.length }}</span>
        <span class="section-chevron">{{ alertsOpen ? '▾' : '▸' }}</span>
      </div>

      <Transition name="slide">
        <div class="section-content" v-if="alertsOpen">
          <div class="section-body">
          <div class="ind-list">
            <!-- Price alerts -->
            <div
              v-for="a in instrumentPriceAlerts"
              :key="'p'+a.id"
              class="list-row alert-row"
              :class="[`alert-row--${a.status}`, { 'row--selected': a.id === alertsStore.selectedAlertId }]"
              @click.stop="alertsStore.selectAlert(a.id)"
              @dblclick.stop="openAlertEditor(a, null)"
            >
              <span class="alert-icon">¤</span>
              <span class="row-name">{{ a.condition.replace(/_/g,' ') }} {{ formatMoney(Number(a.threshold_price), a.instrument_currency) }}</span>
              <div class="row-menu-wrap">
                <button class="row-btn row-menu-btn" @click.stop="toggleMenu(`palert-${a.id}`, $event)" title="More">⋯</button>
                <Teleport to="body">
                  <div v-if="menuOpenId === `palert-${a.id}`" class="row-dropdown row-dropdown--fixed" :style="rowMenuStyle" @click.stop>
                    <button class="dd-item" @click.stop="openAlertEditor(a, null); closeMenu()">⚙ Edit</button>
                    <button class="dd-item" @click.stop="alertsStore.updateAlert(a.id, { repeat: !a.repeat }); closeMenu()">
                      {{ a.repeat ? '◉' : '○' }} Repeat
                    </button>
                    <button class="dd-item" v-if="a.status === 'active'"
                            @click.stop="alertsStore.updateAlert(a.id, { status: 'paused' }); closeMenu()">⏸ Pause</button>
                    <button class="dd-item" v-if="a.status === 'paused'"
                            @click.stop="alertsStore.updateAlert(a.id, { status: 'active' }); closeMenu()">▶ Resume</button>
                    <button class="dd-item" v-if="a.status === 'triggered'"
                            @click.stop="alertsStore.rearmAlert(a.id); closeMenu()">↺ Rearm</button>
                    <button class="dd-item" @click.stop="alertsStore.toggleAlertProjection(a.id); closeMenu()">
                      {{ alertsStore.getAlertProjection(a.id) ? '◉' : '○' }} Y projection
                    </button>
                    <div class="dd-sep" />
                    <button class="dd-item dd-item--danger" @click.stop="alertsStore.deleteAlert(a.id); closeMenu()">✕ Delete</button>
                  </div>
                </Teleport>
              </div>
            </div>
            <!-- Indicator alerts -->
            <div
              v-for="a in instrumentIndicatorAlerts"
              :key="'i'+a.id"
              class="list-row alert-row"
              :class="[`alert-row--${a.status}`, { 'row--selected': a.id === alertsStore.selectedAlertId }]"
              :title="indAlertLabel(a)"
              @click.stop="alertsStore.selectAlert(a.id)"
              @dblclick.stop="openAlertEditor(null, a)"
            >
              <span class="alert-icon">≈</span>
              <span class="row-name">{{ indAlertLabel(a) }}</span>
              <div class="row-menu-wrap">
                <button class="row-btn row-menu-btn" @click.stop="toggleMenu(`ialert-${a.id}`, $event)" title="More">⋯</button>
                <Teleport to="body">
                  <div v-if="menuOpenId === `ialert-${a.id}`" class="row-dropdown row-dropdown--fixed" :style="rowMenuStyle" @click.stop>
                    <button class="dd-item" @click.stop="openAlertEditor(null, a); closeMenu()">⚙ Edit</button>
                    <button class="dd-item" @click.stop="alertsStore.updateIndicatorAlert(a.id, { repeat: !a.repeat }); closeMenu()">
                      {{ a.repeat ? '◉' : '○' }} Repeat
                    </button>
                    <button class="dd-item" v-if="a.status === 'active'"
                            @click.stop="alertsStore.updateIndicatorAlert(a.id, { status: 'paused' }); closeMenu()">⏸ Pause</button>
                    <button class="dd-item" v-if="a.status === 'paused'"
                            @click.stop="alertsStore.updateIndicatorAlert(a.id, { status: 'active' }); closeMenu()">▶ Resume</button>
                    <button class="dd-item" v-if="a.status === 'triggered'"
                            @click.stop="alertsStore.rearmIndicatorAlert(a.id); closeMenu()">↺ Rearm</button>
                    <div class="dd-sep" />
                    <button class="dd-item dd-item--danger" @click.stop="alertsStore.deleteIndicatorAlert(a.id); closeMenu()">✕ Delete</button>
                  </div>
                </Teleport>
              </div>
            </div>
            <div v-if="!instrumentAlerts.length" class="empty-hint">No alerts for this symbol</div>
          </div>
          </div>
          <div class="add-bar">
            <button class="add-btn" @click="openAlertEditor(null, null)">+ Add Alert</button>
          </div>
        </div>
      </Transition>
    </div>

    </div><!-- /panel-body -->
  </div>

  <!-- ── Indicator editor popup ──────────────────────────────────────────── -->
  <Teleport to="body">
    <Transition name="fade">
      <div class="editor-backdrop" v-if="indEditorOpen" @click.self="closeIndEditor">
        <div class="editor-box">
          <div class="ed-header">
            <span>{{ editingInd?.type.toUpperCase() }} Settings</span>
            <button class="ed-close" @click="closeIndEditor">✕</button>
          </div>
          <div class="ed-body" v-if="editingInd">
            <div class="ed-row">
              <label>Colour</label>
              <input type="color" v-model="indFields.color" class="ed-color" />
            </div>
            <div class="ed-row">
              <label>Line width</label>
              <input type="range" min="0.5" max="4" step="0.5" v-model.number="indFields.lineWidth" class="ed-range" />
              <span class="ed-val">{{ indFields.lineWidth }}px</span>
            </div>
            <template v-for="param in editorParamDefs" :key="param.key">
              <div class="ed-row">
                <label>{{ param.label }}</label>
                <template v-if="param.input === 'datetime'">
                  <!-- Date-only input for non-intraday timeframes -->
                  <input
                    v-if="isNonIntradayTf"
                    type="date"
                    :value="tsToDateOnlyInput(indFields.params[param.key] as number)"
                    @input="e => indFields.params[param.key] = dateOnlyInputToTs((e.target as HTMLInputElement).value)"
                    class="ed-input"
                  />
                  <input
                    v-else
                    type="datetime-local"
                    :value="tsToDateInput(indFields.params[param.key] as number)"
                    @input="e => indFields.params[param.key] = dateInputToTs((e.target as HTMLInputElement).value)"
                    class="ed-input"
                  />
                </template>
                <select
                  v-else-if="param.input === 'select'"
                  v-model="indFields.params[param.key]"
                  class="ed-input"
                >
                  <option v-for="opt in param.options ?? []" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                </select>
                <template v-else>
                  <input type="number" v-model.number="indFields.params[param.key]" step="any" class="ed-input ed-num" />
                </template>
              </div>
            </template>
            <!-- AVWAP preset shortcuts -->
            <div class="ed-row" v-if="editingInd.type === 'avwap'">
              <label>Presets</label>
              <div class="avwap-presets">
                <button class="preset-chip" @click="setAvwapPreset('yesterday')" title="Start of yesterday">Yesterday</button>
                <button class="preset-chip" @click="setAvwapPreset('mtd')" title="Start of current month">MTD</button>
                <button class="preset-chip" @click="setAvwapPreset('ytd')" title="Start of current year">YTD</button>
              </div>
            </div>
            <div class="ed-sep" />
            <div class="ed-row">
              <label>Timeframes</label>
              <select v-model="indFields.tfMode" class="ed-input">
                <option value="all">All timeframes</option>
                <option value="locked">Selected only</option>
              </select>
            </div>
            <div v-if="indFields.tfMode === 'locked'" class="ed-tf-grid">
              <label
                v-for="tf in allTimeframes"
                :key="tf"
                class="ed-tf-chip"
                :class="{ 'ed-tf-chip--on': indFields.lockedTimeframes.includes(tf) }"
              >
                <input type="checkbox" :value="tf" v-model="indFields.lockedTimeframes" class="ed-tf-check" />
                {{ tf }}
              </label>
            </div>
          </div>
          <div class="ed-footer">
            <button class="ed-btn ed-apply" @click="applyIndEdit">Apply</button>
            <button class="ed-btn" @click="closeIndEditor">Cancel</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- ── Alert editor popup ────────────────────────────────────────────── -->
  <Teleport to="body">
    <Transition name="fade">
      <div class="editor-backdrop" v-if="alertEditorOpen && chartStore.instrument" @click.self="closeAlertEditor">
        <AlertForm
          :instrument-id="chartStore.instrument.id"
          :symbol="chartStore.symbol"
          :current-tf="chartStore.timeframe"
          :seed-indicator="alertSeedIndicator"
          :edit-price-alert="editingPriceAlertData"
          :edit-indicator-alert="editingIndicatorAlertData"
          @close="closeAlertEditor"
        />
      </div>
    </Transition>
  </Teleport>

  <!-- ── Drawing editor popup ────────────────────────────────────────────── -->
  <Teleport to="body">
    <Transition name="fade">
      <div class="editor-backdrop" v-if="drawEditorOpen" @click.self="closeDrawEditor">
        <div class="editor-box">
          <div class="ed-header">
            <span>{{ editingDraw ? drawingLabel(editingDraw) : '' }} Settings</span>
            <button class="ed-close" @click="closeDrawEditor">✕</button>
          </div>
          <div class="ed-body" v-if="editingDraw">
            <div class="ed-row">
              <label>Colour</label>
              <input type="color" v-model="drawFields.color" class="ed-color" />
            </div>
            <div class="ed-row">
              <label>Line width</label>
              <input type="range" min="0.5" max="4" step="0.5" v-model.number="drawFields.lineWidth" class="ed-range" />
              <span class="ed-val">{{ drawFields.lineWidth }}px</span>
            </div>
            <div class="ed-row">
              <label>Label</label>
              <input type="text" v-model="drawFields.label" placeholder="Optional label" class="ed-input" />
            </div>
            <div class="ed-row">
              <label>Notes</label>
              <input type="text" v-model="drawFields.notes" placeholder="Optional notes" class="ed-input" />
            </div>

            <!-- Coordinate editing -->
            <template v-if="drawPoints.length">
              <div class="ed-sep" />
              <template v-for="(pt, i) in drawPoints" :key="i">
                <div class="ed-point-title">{{ drawPointLabel(editingDraw.drawing_type, i, drawPoints.length) }}</div>
                <div class="ed-row" v-if="editingDraw.drawing_type !== 'horizontal_line'">
                  <label>Date / Time</label>
                  <input type="datetime-local" :value="tsToDateInput(pt.time)"
                         @change="onDrawPointTime(i, ($event.target as HTMLInputElement).value)"
                         class="ed-input" />
                </div>
                <div class="ed-row" v-if="editingDraw.drawing_type !== 'vertical_line'">
                  <label>Price</label>
                  <input type="number" step="any" :value="pt.price"
                         @change="onDrawPointPrice(i, Number(($event.target as HTMLInputElement).value))"
                         class="ed-input ed-num" />
                </div>
              </template>
            </template>
          </div>
          <div class="ed-footer">
            <button class="ed-btn ed-apply" @click="applyDrawEdit">Apply</button>
            <button class="ed-btn" @click="closeDrawEditor">Cancel</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <TextPromptModal
    v-model="showSavePresetModal"
    title="Save Indicator Preset"
    label="Preset name"
    placeholder="Preset name"
    confirm-label="Save"
    @submit="confirmSavePreset"
  />
</template>

<script lang="ts">
// Module-level cache — survives component re-mounts (e.g. panel switches in multi-layout mode)
import type { InstrumentMembership } from '@/types'
const _membershipCache = new Map<number, InstrumentMembership>()
export {}
</script>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAlertsStore } from '@/stores/alerts'
import { useRadarStore } from '@/stores/radar'
import { useWatchlistStore } from '@/stores/watchlist'
import TextPromptModal from '@/components/common/TextPromptModal.vue'
import HoverTooltip from '@/components/common/HoverTooltip.vue'
import { formatMoney } from '@/lib/format'
import { usePanelStore }   from '@/stores/chart'
import { useDrawingsStore } from '@/stores/drawings'
import { usePresetsStore }  from '@/stores/presets'
import AlertForm from '@/components/alerts/AlertForm.vue'
import InstrumentInfoPanel from '@/components/chart/InstrumentInfoPanel.vue'
import {
  INDICATOR_CATALOG,
  INDICATOR_BY_TYPE,
  cloneDefaultIndicator,
  indicatorDisplayName,
  indicatorDefaultPane,
  normalizeIndicatorParams,
} from '@/lib/indicators/catalog'
import type { IndicatorParamDef } from '@/lib/indicators/catalog'
import type { ChartDrawing, IndicatorAlert, PriceAlert, IndicatorConfig, IndicatorType } from '@/types'
import { api } from '@/lib/api'
import { VueDraggable } from 'vue-draggable-plus'

const props = defineProps<{ panelId: string; panelWidth?: number }>()
const emit = defineEmits<{ selectSymbol: [symbol: string] }>()

const router         = useRouter()
const alertsStore    = useAlertsStore()
const radarStore     = useRadarStore()
const watchlistStore = useWatchlistStore()
const chartStore     = usePanelStore(props.panelId)
const drawStore      = useDrawingsStore()
const presetsStore   = usePresetsStore()

// ── DnD wiring ────────────────────────────────────────────────────────────────
const draggableIndicators = computed({
  get: () => chartStore.indicators,
  set: (val) => chartStore.reorderIndicators(val),
})

const draggableDrawings = computed({
  get: () => drawStore.drawings,
  set: (val) => { drawStore.drawings = val },
})

function onDrawingsReorder() {
  const ids = drawStore.drawings.map(d => d.id)
  api.post('/drawings/reorder', { ids }).catch(e => console.error('Failed to reorder drawings', e))
}

const INTRADAY_OR_DAILY: string[] = ['M1','M5','M15','M30','H1','H2','H4','H12','D1']
const sessionRange = computed(() => {
  const bars = chartStore.bars
  if (!bars.length || !INTRADAY_OR_DAILY.includes(chartStore.timeframe)) return null
  const lastDate = bars[bars.length - 1].ts.slice(0, 10)
  const dayBars  = bars.filter(b => b.ts.slice(0, 10) === lastDate)
  const highBar = dayBars.reduce((best, bar) => (best == null || bar.high > best.high ? bar : best), null as typeof dayBars[number] | null)
  const lowBar = dayBars.reduce((best, bar) => (best == null || bar.low < best.low ? bar : best), null as typeof dayBars[number] | null)
  if (!highBar || !lowBar) return null
  return {
    high: highBar.high,
    low: lowBar.low,
    highTime: highBar.ts,
    lowTime: lowBar.ts,
  }
})

// ── Panel & section collapse state ───────────────────────────────────────────
const isPanelOpen    = ref(false)   // starts hidden until an instrument is loaded
const alertsOpen     = ref(false)
const indicatorsOpen = ref(false)
const drawingsOpen   = ref(false)
const radarsOpen     = ref(false)
const watchlistsOpen = ref(false)
const screenersOpen  = ref(false)

// ── ⋯ row dropdown menu ───────────────────────────────────────────────────────
const menuOpenId = ref<string | null>(null)
const rowMenuStyle = ref<Record<string, string>>({})

function toggleMenu(key: string, event: MouseEvent) {
  if (menuOpenId.value === key) {
    closeMenu()
    return
  }

  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const menuH = estimateMenuHeight(key)
  const menuW = 158
  const gap = 6
  const below = window.innerHeight - rect.bottom
  const above = rect.top
  const openUp = below < menuH + gap && above > below
  const maxH = Math.max(96, Math.min(menuH, window.innerHeight - 16))
  const top = openUp
    ? Math.max(8, rect.top - maxH - gap)
    : Math.min(window.innerHeight - maxH - 8, rect.bottom + gap)
  const left = Math.max(8, Math.min(window.innerWidth - menuW - 8, rect.right - menuW))

  rowMenuStyle.value = {
    top: `${top}px`,
    left: `${left}px`,
    width: `${menuW}px`,
    maxHeight: `${maxH}px`,
  }
  menuOpenId.value = key
}

function closeMenu() {
  menuOpenId.value = null
}

function estimateMenuHeight(key: string): number {
  if (key.startsWith('draw-')) return 174
  if (key.startsWith('palert-')) return 198
  if (key.startsWith('ialert-')) return 164
  return 154
}

onMounted(() => document.addEventListener('click', closeMenu))
onUnmounted(() => document.removeEventListener('click', closeMenu))

const membership = ref<InstrumentMembership | null>(null)

const activeScreeners = computed(() =>
  membership.value?.screeners.filter(s => s.in_current_results) ?? []
)

watch(() => chartStore.instrument?.id, async (id) => {
  if (!id) { membership.value = null; isPanelOpen.value = false; return }
  isPanelOpen.value = true
  // Reset section states for new instrument; content-based watches will re-open them
  watchlistsOpen.value = false
  screenersOpen.value  = false
  indicatorsOpen.value = false
  drawingsOpen.value   = false
  alertsOpen.value     = false
  radarsOpen.value     = false
  if (_membershipCache.has(id)) {
    const cached = _membershipCache.get(id)!
    membership.value = cached
    watchlistsOpen.value = cached.watchlists.length > 0
    screenersOpen.value  = cached.screeners.filter(s => s.in_current_results).length > 0
    return
  }
  try {
    const data = await api.get<InstrumentMembership>(`/instruments/${id}/membership`)
    _membershipCache.set(id, data)
    membership.value = data
    watchlistsOpen.value = data.watchlists.length > 0
    screenersOpen.value  = data.screeners.filter(s => s.in_current_results).length > 0
  } catch {
    membership.value = null
  }
}, { immediate: true })

watch(
  () => radarStore.chartDetections.length,
  (count) => {
    radarsOpen.value = count > 0
  },
)

const focusedRadarDetection = computed(() => {
  const focusedId = radarStore.focusedChartDetectionId
  if (focusedId == null) return null
  return radarStore.chartDetections.find(detection => detection.id === focusedId) ?? null
})
const focusedRadarRationale = computed(() => buildRadarRationale(focusedRadarDetection.value))

function onScreenerClick(scId: number) {
  router.push(`/screener?selectedId=${scId}`)
}

function onWatchlistClick(wlId: number) {
  watchlistStore.requestFocusWatchlist(wlId)
}

function formatRadarSetup(setup: string): string {
  return humanizeRadarToken(setup)
}

function titleCaseWords(value: string): string {
  return value
    .split(' ')
    .filter(Boolean)
    .map(word => word[0].toUpperCase() + word.slice(1))
    .join(' ')
}

function formatRadarState(state: string): string {
  return titleCaseWords(state.replace(/_/g, ' '))
}

function humanizeRadarToken(value: string): string {
  const normalized = value.replace(/_/g, ' ')
  const special = normalized
    .replace(/\bweek52\b/gi, '52-week')
    .replace(/\bytd\b/gi, 'YTD')
    .replace(/\bavwap\b/gi, 'AVWAP')
    .replace(/\bema\b/gi, 'EMA')
  return titleCaseWords(special)
}

function formatRadarObservedDate(value?: string | null): string {
  if (!value) return '—'
  const match = value.match(/^\d{4}-\d{2}-\d{2}/)
  if (match) return match[0]
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '—'
  return `${parsed.getUTCFullYear()}-${String(parsed.getUTCMonth() + 1).padStart(2, '0')}-${String(parsed.getUTCDate()).padStart(2, '0')}`
}

function formatRadarRecordedDate(value?: string | null): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '—'
  return `${parsed.getUTCFullYear()}-${String(parsed.getUTCMonth() + 1).padStart(2, '0')}-${String(parsed.getUTCDate()).padStart(2, '0')} ${String(parsed.getUTCHours()).padStart(2, '0')}:${String(parsed.getUTCMinutes()).padStart(2, '0')} UTC`
}

function radarMetricNumber(
  det: { evidence?: { metrics?: Record<string, unknown> } },
  key: string,
): number | null {
  const value = det.evidence?.metrics?.[key]
  return typeof value === 'number' ? value : null
}

function formatRadarSignalDate(det: {
  observed_at: string
  signal_at?: string
  evidence?: { metrics?: Record<string, unknown> }
}) {
  if (det.signal_at) {
    return formatRadarObservedDate(det.signal_at)
  }
  const signalTime = radarMetricNumber(det, 'signal_time')
  if (signalTime != null) return formatRadarObservedDate(new Date(signalTime * 1000).toISOString())
  return formatRadarObservedDate(det.observed_at)
}

function formatRadarPrice(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toFixed(2)
}

function formatRadarThreadTag(det: {
  id?: number
  thread_event_index?: number | null
  thread?: { detection_count: number } | null
  thread_history?: Array<{ id: number }>
}) {
  const fallbackIndex = det.thread_history?.findIndex(event => event.id === det.id) ?? -1
  const eventIndex = det.thread_event_index ?? (fallbackIndex >= 0 ? fallbackIndex + 1 : null)
  const totalEvents = det.thread?.detection_count ?? det.thread_history?.length
  if (eventIndex != null && totalEvents) return `${eventIndex}/${totalEvents}`
  if (eventIndex != null) return `#${eventIndex}`
  return ''
}

function formatRadarSequenceBadge(
  det: {
    id?: number
    thread_event_index?: number | null
    thread?: { detection_count: number } | null
    thread_history?: Array<{ id: number }>
  },
) {
  return formatRadarThreadTag(det) || '•'
}

function radarTooltipText(det: {
  setup_type: string
  observed_at: string
  signal_at?: string
  context_at?: string | null
  state: string
  state_reason?: string | null
  entry_price?: number | null
  invalidation_price?: number | null
  target_price?: number | null
  summary: string
  invalidation_hint?: string | null
  score: number
  thread_event_index?: number | null
  thread?: { detection_count: number } | null
  thread_history?: Array<{
    thread_event_index?: number | null
    setup_type: string
    state: string
    signal_at: string
  }>
  evidence?: { metrics?: Record<string, unknown> }
}) {
  const signalTime = radarMetricNumber(det, 'signal_time')
  const contextTime = radarMetricNumber(det, 'context_time')
  const lines = [
    `${formatRadarSetup(det.setup_type)} · detected ${formatRadarSignalDate(det)}`,
    `State: ${formatRadarState(det.state)}`,
    det.summary,
    `Score: ${det.score.toFixed(2)}`,
  ]
  if ('created_at' in det && typeof det.created_at === 'string') lines.push(`Recorded: ${formatRadarRecordedDate(det.created_at)}`)
  if (det.state_reason) lines.push(det.state_reason)
  if (det.entry_price != null) lines.push(`Entry: ${det.entry_price.toFixed(2)}`)
  if (det.invalidation_price != null) lines.push(`Invalidation: ${det.invalidation_price.toFixed(2)}`)
  if (det.target_price != null) lines.push(`Target: ${det.target_price.toFixed(2)}`)
  if (det.thread_event_index != null && det.thread?.detection_count) {
    lines.push(`Thread event ${det.thread_event_index} of ${det.thread.detection_count}`)
  }
  if (det.thread_history?.length) {
    lines.push('Timeline:')
    for (const event of det.thread_history) {
      lines.push(
        `#${event.thread_event_index ?? '—'} ${formatRadarSetup(event.setup_type)} · ${formatRadarState(event.state)} · ${formatRadarObservedDate(event.signal_at)}`,
      )
    }
  }
  if (det.context_at && det.context_at !== det.signal_at) {
    lines.push(`Level last touched on ${formatRadarObservedDate(det.context_at)}`)
  } else if (contextTime != null && contextTime !== signalTime) {
    lines.push(`Level last touched on ${formatRadarObservedDate(new Date(contextTime * 1000).toISOString())}`)
  }
  if (det.invalidation_hint) lines.push(det.invalidation_hint)
  return lines.join('\n')
}

function buildRadarRationale(
  det: (typeof focusedRadarDetection.value) | null,
) {
  if (!det?.evidence?.metrics) return []
  const metrics = det.evidence.metrics as Record<string, unknown>
  const structures = det.evidence.structures ?? []
  const items: string[] = []
  const touchFactor = typeof det.score_factors.touch_count === 'number' ? det.score_factors.touch_count : null
  if (touchFactor != null) {
    items.push(`${Math.max(2, Math.round(touchFactor * 4))} swing touches define this level.`)
  }
  const multiTfHits = typeof metrics.multi_timeframe_hits === 'number' ? metrics.multi_timeframe_hits : 0
  if (multiTfHits > 0) {
    items.push(`${Math.round(multiTfHits)} higher-horizon levels overlap this zone.`)
  }
  if (metrics.volatility_squeeze_active) {
    items.push('Volatility is compressed, so a larger move may be brewing.')
  }
  if (typeof metrics.avwap_anchor_type === 'string') {
    items.push(`Primary AVWAP is anchored to ${humanizeRadarToken(metrics.avwap_anchor_type)}.`)
  }
  const structureTypes = new Set(structures.map(structure => String(structure.type)))
  if (structureTypes.has('channel') || structureTypes.has('wedge') || structureTypes.has('triangle')) {
    items.push('Pattern structure is reinforcing the setup context.')
  } else if (structureTypes.has('trendline')) {
    items.push('A nearby trendline is reinforcing this area.')
  }
  if ((typeof metrics.gap_count === 'number' ? metrics.gap_count : 0) > 0) {
    items.push('A nearby gap adds context to the reaction zone.')
  }
  return items.slice(0, 4)
}

// ── Indicators ─────────────────────────────────────────────────────────────────
const showPicker       = ref(false)
const selectedPresetId = ref<number | ''>('')
const showSavePresetModal = ref(false)

const availableTypes: Array<{ type: IndicatorType; label: string }> =
  INDICATOR_CATALOG.map(item => ({ type: item.type, label: item.pickerLabel }))

function isActiveOnCurrentTf(ind: IndicatorConfig): boolean {
  return !ind.lockedTimeframes?.length || ind.lockedTimeframes.includes(chartStore.timeframe)
}

function toggleIndProjection(i: number) {
  const ind = chartStore.indicators[i]
  if (!ind) return
  chartStore.updateIndicator(i, { ...ind, showYProjection: !ind.showYProjection })
}

function displayName(ind: IndicatorConfig): string {
  return indicatorDisplayName(ind)
}

function addIndicator(type: IndicatorType) {
  chartStore.addIndicator(cloneDefaultIndicator(type))
  showPicker.value = false
}

function applyPreset() {
  if (!selectedPresetId.value) return
  const preset = presetsStore.presets.find(p => p.id === selectedPresetId.value)
  if (preset) chartStore.setIndicators([...preset.indicators])
}

function applyDefault() {
  const def = presetsStore.getDefault()
  if (def) chartStore.setIndicators([...def.indicators])
}

async function saveAsPreset() {
  showSavePresetModal.value = true
}

async function confirmSavePreset(name: string) {
  await presetsStore.savePreset(name, [...chartStore.indicators])
  showSavePresetModal.value = false
}

// ── Drawings helpers ──────────────────────────────────────────────────────────
const DRAW_ICONS: Record<string, string> = {
  trendline: '╱', ray: '→', horizontal_line: '─', vertical_line: '│',
  rectangle: '▭', circle: '○', half_circle: '◒', fibonacci_retracement: 'φ',
  fibonacci_extension: 'φ+', arrow: '↗', text_box: 'T',
}

function drawingIcon(type: string): string {
  return DRAW_ICONS[type] ?? '✎'
}

function drawingLabel(d: ChartDrawing): string {
  if (d.label) return d.label
  const name = d.drawing_type.replace(/_/g, ' ')
  // If it has points with a price, show it
  const pts = (d.data as any)?.points
  if (pts?.length) {
    const price = pts[0]?.price
    if (price != null) return `${name} @ ${Number(price).toFixed(2)}`
  }
  return name
}

async function toggleVisible(d: ChartDrawing) {
  await drawStore.updateDrawing(d.id, { is_visible: !d.is_visible })
}

async function toggleLock(d: ChartDrawing) {
  await drawStore.updateDrawing(d.id, { is_locked: !d.is_locked })
}

// ── Indicator editor ──────────────────────────────────────────────────────────
const indEditorOpen = ref(false)
let   editingIndIdx = -1
const editingInd = ref<IndicatorConfig | null>(null)
const allTimeframes = ['M1','M5','M15','M30','H1','H2','H4','H12','D1','W1','MN'] as const
const indFields  = reactive({
  color: '#fff',
  lineWidth: 1.5,
  params: {} as Record<string, unknown>,
  tfMode: 'all' as 'all'|'locked',
  lockedTimeframes: [] as string[],
})

function openIndEditor(i: number) {
  const ind = chartStore.indicators[i]
  if (!ind) return
  editingIndIdx = i
  editingInd.value = ind
  indFields.color            = ind.style.color
  indFields.lineWidth        = ind.style.lineWidth ?? 1.5
  indFields.params           = normalizeIndicatorParams(ind.type, ind.params)
  indFields.lockedTimeframes = ind.lockedTimeframes ? [...ind.lockedTimeframes] : []
  indFields.tfMode           = indFields.lockedTimeframes.length ? 'locked' : 'all'
  indEditorOpen.value = true
}

const editorParamDefs = computed<IndicatorParamDef[]>(() => {
  if (!editingInd.value) return []
  const catalog = INDICATOR_BY_TYPE[editingInd.value.type]
  if (catalog?.params.length) return catalog.params
  return Object.keys(indFields.params).map(key => ({ key, label: paramLabel(key) }))
})

function alertForIndicator(i: number) {
  openAlertEditor(null, null, chartStore.indicators[i])
}

function closeIndEditor() { indEditorOpen.value = false; editingInd.value = null; editingIndIdx = -1 }

function applyIndEdit() {
  if (editingIndIdx < 0) return
  chartStore.updateIndicator(editingIndIdx, {
    ...chartStore.indicators[editingIndIdx],
    style:            { ...chartStore.indicators[editingIndIdx].style, color: indFields.color, lineWidth: indFields.lineWidth },
    pane:             indicatorDefaultPane(chartStore.indicators[editingIndIdx].type as import('@/types').IndicatorType),
    params:           { ...indFields.params },
    lockedTimeframes: indFields.tfMode === 'locked' && indFields.lockedTimeframes.length
      ? [...indFields.lockedTimeframes] as import('@/types').Timeframe[]
      : null,
  })
  closeIndEditor()
}

const instrumentPriceAlerts = computed(() =>
  alertsStore.alerts.filter(a => a.instrument_id === chartStore.instrument?.id)
)
const instrumentIndicatorAlerts = computed(() =>
  alertsStore.indicatorAlerts.filter(a => a.instrument_id === chartStore.instrument?.id)
)
const instrumentAlerts = computed(() =>
  [...instrumentPriceAlerts.value, ...instrumentIndicatorAlerts.value]
)

// Auto-expand sections when they have content (one-way; resets happen in the instrument watch)
watch(() => chartStore.indicators.length, (n) => { if (n > 0) indicatorsOpen.value = true }, { immediate: true })
watch(() => drawStore.drawings.length,    (n) => { if (n > 0) drawingsOpen.value   = true }, { immediate: true })
watch(instrumentAlerts,               (alerts) => { if (alerts.length > 0) alertsOpen.value = true }, { immediate: true })

// ── Alert editor ──────────────────────────────────────────────────────────────
const alertEditorOpen           = ref(false)
const editingPriceAlertData     = ref<PriceAlert | null>(null)
const editingIndicatorAlertData = ref<IndicatorAlert | null>(null)
const alertSeedIndicator        = ref<IndicatorConfig | null>(null)

function openAlertEditor(price: PriceAlert | null, indicator: IndicatorAlert | null, seed: IndicatorConfig | null = null) {
  editingPriceAlertData.value     = price
  editingIndicatorAlertData.value = indicator
  alertSeedIndicator.value        = seed
  alertEditorOpen.value = true
}

function closeAlertEditor() {
  alertEditorOpen.value = false
  editingPriceAlertData.value     = null
  editingIndicatorAlertData.value = null
  alertSeedIndicator.value        = null
}

function fmtTs(ts: number): string {
  const d = new Date(ts * 1000)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}`
}

function fmtIndParams(type: string, params: Record<string, unknown>): string {
  return indicatorDisplayName({ type: type as IndicatorType, params: params ?? {} })
}

function indAlertLabel(a: IndicatorAlert): string {
  const indA = fmtIndParams(a.indicator_a_type, a.indicator_a_params ?? {})
  const cond = a.condition.replace(/_/g, ' ')
  const expr = a.indicator_b_type
    ? `${indA} ${cond} ${fmtIndParams(a.indicator_b_type, a.indicator_b_params ?? {})}`
    : `${indA} ${cond} ${a.threshold_value ?? ''}`
  return `${expr} · ${a.timeframe}`
}

// ── Drawing editor ────────────────────────────────────────────────────────────
const drawEditorOpen = ref(false)
const editingDraw    = ref<ChartDrawing | null>(null)
const drawFields     = reactive({ color: '#fff', lineWidth: 1.5, label: '', notes: '' })
const drawPoints     = ref<Array<{ time: number; price: number }>>([])
let   drawOriginalPoints: Array<{ time: number; price: number }> = []

function openDrawEditor(d: ChartDrawing) {
  editingDraw.value    = d
  drawFields.color     = d.style?.color ?? '#ffffff'
  drawFields.lineWidth = d.style?.lineWidth ?? 1.5
  drawFields.label     = d.label ?? ''
  drawFields.notes     = d.notes ?? ''
  const pts = ((d.data as any)?.points ?? []) as Array<{ time: number; price: number }>
  drawOriginalPoints   = pts.map(p => ({ ...p }))
  drawPoints.value     = pts.map(p => ({ ...p }))
  drawEditorOpen.value = true
}

function closeDrawEditor() {
  // Revert any live coordinate preview changes if user cancels
  if (editingDraw.value) {
    drawStore.localUpdateDrawing(editingDraw.value.id, {
      data: { ...(editingDraw.value.data as any), points: drawOriginalPoints },
    } as any)
  }
  drawEditorOpen.value = false
  editingDraw.value    = null
  drawPoints.value     = []
}

function onDrawPointTime(idx: number, val: string) {
  if (!editingDraw.value) return
  const ts = dateInputToTs(val)
  if (!isFinite(ts)) return
  drawPoints.value[idx] = { ...drawPoints.value[idx], time: ts }
  _livePreviewPoints()
}

function onDrawPointPrice(idx: number, price: number) {
  if (!editingDraw.value || !isFinite(price)) return
  drawPoints.value[idx] = { ...drawPoints.value[idx], price }
  _livePreviewPoints()
}

function _livePreviewPoints() {
  if (!editingDraw.value) return
  drawStore.localUpdateDrawing(editingDraw.value.id, {
    data: { ...(editingDraw.value.data as any), points: drawPoints.value.map(p => ({ ...p })) },
  } as any)
}

function drawPointLabel(type: string, idx: number, total: number): string {
  if (total === 1) return 'Point'
  const labels: Record<string, string[]> = {
    rectangle: ['Top-left', 'Bottom-right'],
    fibonacci_retracement: ['Start', 'End'],
    fibonacci_extension: ['Start', 'End'],
    circle: ['Bounds start', 'Bounds end'],
    half_circle: ['Bounds start', 'Bounds end'],
  }
  return labels[type]?.[idx] ?? `Point ${idx + 1}`
}

async function applyDrawEdit() {
  if (!editingDraw.value) return
  await drawStore.updateDrawing(editingDraw.value.id, {
    data:  { ...(editingDraw.value.data as any), points: drawPoints.value.map(p => ({ ...p })) },
    style: { ...editingDraw.value.style, color: drawFields.color, lineWidth: drawFields.lineWidth },
    label: drawFields.label || undefined,
    notes: drawFields.notes || undefined,
  } as any)
  drawEditorOpen.value = false
  editingDraw.value    = null
  drawPoints.value     = []
}

// ── Shared helpers ────────────────────────────────────────────────────────────
const NON_INTRADAY_TFS = new Set(['D1', 'W1', 'MN'])
const isNonIntradayTf = computed(() => NON_INTRADAY_TFS.has(chartStore.timeframe))

function paramLabel(key: string): string {
  const m: Record<string, string> = {
    period: 'Period', fast: 'Fast', slow: 'Slow',
    signal: 'Signal', std_dev: 'Std dev', anchor_timestamp: 'Anchor date',
    atr_period: 'ATR period', senkou_b: 'Senkou B',
    af_start: 'AF start', af_step: 'AF step', af_max: 'AF max',
    k_period: '%K period', d_period: '%D period', smooth_k: '%K smooth',
  }
  return m[key] ?? key.charAt(0).toUpperCase() + key.slice(1)
}

function tsToDateInput(ts: number | undefined): string {
  if (!ts) return ''
  const d   = new Date(ts * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function tsToDateOnlyInput(ts: number | undefined): string {
  if (!ts) return ''
  const d   = new Date(ts * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`
}

function dateInputToTs(val: string): number {
  return Math.floor(new Date(val).getTime() / 1000)
}

function dateOnlyInputToTs(val: string): number {
  // Interpret as midnight UTC
  return Math.floor(new Date(val + 'T00:00:00Z').getTime() / 1000)
}

function setAvwapPreset(preset: 'yesterday' | 'mtd' | 'ytd') {
  const now = new Date()
  let d: Date
  if (preset === 'yesterday') {
    d = new Date(now)
    d.setDate(d.getDate() - 1)
    d.setHours(0, 0, 0, 0)
  } else if (preset === 'mtd') {
    d = new Date(now.getFullYear(), now.getMonth(), 1, 0, 0, 0, 0)
  } else {
    d = new Date(now.getFullYear(), 0, 1, 0, 0, 0, 0)
  }
  indFields.params.anchor_timestamp = Math.floor(d.getTime() / 1000)
}

// ── Chart-item double-click → open editor ─────────────────────────────────────
watch(() => drawStore.editRequestId, (id) => {
  if (id == null) return
  const d = drawStore.drawings.find(x => x.id === id)
  if (d) openDrawEditor(d)
  drawStore.requestEditDrawing(null)
})

watch(() => alertsStore.editRequestAlertId, (id) => {
  if (id == null) return
  const pa = alertsStore.alerts.find(x => x.id === id)
  if (pa) { openAlertEditor(pa, null); alertsStore.requestEditAlert(null); return }
  const ia = alertsStore.indicatorAlerts.find(x => x.id === id)
  if (ia) { openAlertEditor(null, ia); alertsStore.requestEditAlert(null) }
})

watch(() => chartStore.editRequestIndicatorIndex, (i) => {
  if (i == null) return
  openIndEditor(i)
  chartStore.requestEditIndicator(null)
})
</script>

<style scoped>
.side-panel {
  background: #111;
  border-left: 1px solid #222;
  width: 220px;
  display: flex;
  flex-direction: row;
  font-size: 12px;
  color: #aaa;
  overflow: hidden;
  flex-shrink: 0;
  transition: width 0.2s ease;
}
.side-panel--collapsed { width: 16px; }

.panel-toggle {
  width: 16px;
  flex-shrink: 0;
  background: #0d0d0d;
  border: none;
  border-left: 1px solid #1a1a1a;
  color: #444;
  cursor: pointer;
  font-size: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  align-self: stretch;
  transition: color 0.1s, background 0.1s;
}
.panel-toggle:hover { color: #aaa; background: #111; }

.panel-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  min-width: 0;
}

/* ── Section chrome ────────────────────────────────────────────────────── */
.section {
  display: flex;
  flex-direction: column;
  flex: 0 0 auto;
  border-bottom: 1px solid #1a1a1a;
}
.section.collapsed { flex: 0 0 auto; }

.section-header {
  display: flex;
  align-items: center;
  padding: 7px 10px;
  background: #141414;
  cursor: pointer;
  gap: 6px;
  flex-shrink: 0;
  user-select: none;
}
.section-header:hover { background: #1a1a1a; }

.section-title { flex: 1; font-weight: 600; color: #ccc; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }
.section-count { background: #2a2a2a; color: #666; border-radius: 8px; padding: 0 5px; font-size: 10px; }
.section-chevron { color: #444; font-size: 9px; }

.section-content {
  display: flex;
  flex-direction: column;
}

.section-body {
  overflow-y: auto;
  max-height: 200px;
  min-height: 32px;
}

.alert-row { cursor: default; }
.alert-icon { width: 14px; text-align: center; font-size: 10px; color: #f59e0b; flex-shrink: 0; }
.alert-row--active .alert-icon { color: #f59e0b; }
.alert-row--triggered .alert-icon { color: #555; }
.alert-row--paused .alert-icon { color: #ffd54f; opacity: 0.5; }

/* ── List ──────────────────────────────────────────────────────────────── */
.ind-list {
  flex: 1;
  overflow-y: auto;
  padding: 2px 0;
}

.list-row {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  cursor: pointer;
  transition: background 0.1s;
}
.list-row:hover { background: #1a1a1a; }
.list-row.row--selected { background: #1a2a3a; }
.list-row.row--hidden { opacity: 0.45; }
.list-row.row--tf-inactive { opacity: 0.35; }
.list-row.row--tf-inactive .color-dot { filter: grayscale(1); }

.radar-row {
  align-items: flex-start;
}

.tf-lock-badge { font-size: 9px; opacity: 0.6; flex-shrink: 0; }

.ind-drag-handle,
.draw-drag-handle {
  color: #2a2a2a;
  cursor: grab;
  font-size: 13px;
  line-height: 1;
  flex-shrink: 0;
  user-select: none;
  padding: 0 1px;
}
.ind-drag-handle:hover,
.draw-drag-handle:hover { color: #555; }

.color-dot {
  width: 8px; height: 8px;
  border-radius: 50%; flex-shrink: 0;
}

.draw-icon {
  width: 14px; text-align: center;
  font-size: 11px; color: #555; flex-shrink: 0;
}

.radar-toggle-indicator {
  width: 14px;
  text-align: center;
  font-size: 10px;
  color: #2ec4b6;
  flex-shrink: 0;
}

.radar-sequence-tag {
  width: 14px;
  text-align: center;
  font-size: 9px;
  color: #4c6b89;
  flex-shrink: 0;
}

.radar-info-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 9px;
  height: 9px;
  margin-left: 2px;
  border: 1px solid #2c2c2c;
  border-radius: 50%;
  color: #666;
  background: #141414;
  font-family: ui-sans-serif, system-ui, sans-serif;
  font-size: 7px;
  font-weight: 700;
  line-height: 1;
  cursor: help;
  flex-shrink: 0;
  vertical-align: super;
  transform: translateY(-0.2em);
}

.radar-info-btn:hover,
.radar-info-btn:focus-visible {
  color: #8ab4f8;
  border-color: #35527a;
  outline: none;
}

.radar-focus-card {
  margin-top: 8px;
  border: 1px solid #232323;
  border-radius: 6px;
  background: #121212;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.radar-focus-head {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.radar-focus-title {
  color: #ddd;
  font-size: 11px;
  text-transform: capitalize;
}

.radar-focus-head-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.radar-focus-copy {
  color: #8c8c8c;
  font-size: 10px;
  line-height: 1.5;
}

.radar-focus-rationale {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.radar-focus-rationale-item {
  border: 1px solid #1d2833;
  border-radius: 6px;
  background: #101820;
  color: #8fb7d8;
  font-size: 10px;
  line-height: 1.45;
  padding: 6px 8px;
}

.radar-focus-grid {
  display: grid;
  grid-template-columns: minmax(0, auto) minmax(0, 1fr);
  gap: 4px 8px;
  font-size: 10px;
}

.radar-focus-key {
  color: #626262;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.radar-focus-val {
  color: #bdbdbd;
}

.radar-focus-timeline {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.radar-focus-event {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  width: 100%;
  border: 1px solid #252525;
  background: #0f0f0f;
  color: #a8a8a8;
  border-radius: 4px;
  padding: 5px 6px;
}

.radar-focus-event--active {
  border-color: #24415d;
  background: #132131;
  color: #d7e8fa;
}

.radar-focus-event-seq {
  color: #5f7ea0;
  font-size: 9px;
  min-width: 22px;
}

.radar-focus-event-main {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.radar-focus-event-title {
  font-size: 10px;
  text-transform: capitalize;
}

.radar-focus-event-meta {
  color: #6f6f6f;
  font-size: 9px;
}

.row-name {
  flex: 1;
  font-family: monospace;
  font-size: 11px;
  min-width: 0;
}

.radar-row-main {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.radar-row-title {
  color: #d6d6d6;
  line-height: 1.3;
}

.radar-row-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.draw-pane-tag {
  font-size: 9px;
  font-family: monospace;
  color: #555;
  background: #1e1e1e;
  border: 1px solid #2a2a2a;
  border-radius: 2px;
  padding: 0 3px;
  letter-spacing: 0.03em;
}

.draw-pane-tag--developing {
  color: #d6bf6c;
  border-color: #4f4a1b;
  background: #26210d;
}

.draw-pane-tag--confirmed {
  color: #73d8b2;
  border-color: #194331;
  background: #0f231b;
}

.draw-pane-tag--resolved {
  color: #7fe0b8;
  border-color: #27513b;
  background: #13271d;
}

.draw-pane-tag--stale {
  color: #8b8b8b;
  border-color: #313131;
  background: #171717;
}

.draw-pane-tag--invalidated {
  color: #ef8a85;
  border-color: #5f231f;
  background: #2a1210;
}

.draw-pane-tag--dim {
  color: #4e4e4e;
}

.row-btn {
  background: none; border: none;
  color: #444; cursor: pointer;
  padding: 1px 3px; font-size: 11px; border-radius: 2px;
  flex-shrink: 0;
}
.row-btn:hover { color: #aaa; background: #222; }
.row-btn.danger:hover { color: #ef5350; }
.row-btn.btn--dim  { opacity: 0.35; }
.row-btn.btn--active { color: #64b5f6; }

/* ── Row ⋯ dropdown ────────────────────────────────────────────────────── */
.row-menu-wrap {
  position: relative;
  flex-shrink: 0;
}

.row-menu-btn {
  font-size: 13px;
  letter-spacing: 0.5px;
  padding: 0 3px;
  line-height: 1;
}

.row-dropdown {
  position: absolute;
  right: 0;
  top: 100%;
  z-index: 200;
  background: #1a1a1a;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  min-width: 140px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.6);
  padding: 3px 0;
}

.row-dropdown--fixed {
  position: fixed;
  right: auto;
  top: auto;
  overflow-y: auto;
}

.dd-item {
  display: block;
  width: 100%;
  background: none;
  border: none;
  color: #aaa;
  text-align: left;
  padding: 5px 10px;
  cursor: pointer;
  font-size: 11px;
  white-space: nowrap;
}
.dd-item:hover { background: #242424; color: #fff; }
.dd-item--danger { color: #777; }
.dd-item--danger:hover { background: #2a1515; color: #ef5350; }

.dd-sep {
  height: 1px;
  background: #2a2a2a;
  margin: 3px 0;
}

.empty-hint { padding: 8px 10px; color: #333; font-style: italic; font-size: 11px; }

.hint-btn {
  display: block;
  margin-top: 6px;
  background: #1a3a5c;
  border: none;
  color: #64b5f6;
  border-radius: 3px;
  padding: 3px 8px;
  cursor: pointer;
  font-size: 11px;
  font-style: normal;
}
.hint-btn:hover { background: #1f4a7a; }

/* ── Add / preset bars ─────────────────────────────────────────────────── */
.add-bar {
  padding: 4px 8px;
  border-top: 1px solid #1a1a1a;
  flex-shrink: 0;
}
.add-btn {
  background: #1a3a5c; border: none;
  color: #64b5f6; border-radius: 3px;
  padding: 3px 10px; cursor: pointer; font-size: 11px; width: 100%;
}
.add-btn:hover { background: #1f4a7a; }

.picker-dropdown {
  border-top: 1px solid #222;
  background: #0d0d0d;
  max-height: 180px;
  overflow-y: auto;
  flex-shrink: 0;
}
.picker-item {
  display: block; width: 100%;
  background: none; border: none;
  color: #aaa; text-align: left;
  padding: 5px 10px; cursor: pointer; font-size: 11px;
}
.picker-item:hover { background: #1a1a1a; color: #fff; }

.preset-bar {
  display: flex; align-items: center; gap: 4px;
  padding: 4px 8px;
  border-top: 1px solid #1a1a1a;
  flex-shrink: 0;
}
.preset-select {
  flex: 1;
  background: #1a1a1a; border: 1px solid #2a2a2a;
  color: #888; border-radius: 3px;
  padding: 2px 4px; font-size: 10px;
}
.preset-btn {
  background: #1a1a1a; border: 1px solid #2a2a2a;
  color: #666; border-radius: 3px;
  padding: 2px 6px; cursor: pointer; font-size: 11px;
}
.preset-btn:hover { color: #ccc; border-color: #444; }

/* ── Shared editor styles ─────────────────────────────────────────────── */
.editor-backdrop {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.55);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.editor-box {
  background: #141414; border: 1px solid #2a2a2a; border-radius: 6px;
  min-width: 300px; max-width: 360px; width: 100%;
  max-height: calc(100vh - 80px);
  display: flex; flex-direction: column;
  font-family: 'JetBrains Mono', monospace; font-size: 12px;
  box-shadow: 0 8px 40px rgba(0,0,0,0.6);
}
.ed-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 11px 14px; border-bottom: 1px solid #1f1f1f;
  color: #ccc; font-weight: 600; font-size: 12px;
}
.ed-close { background: none; border: none; color: #555; cursor: pointer; font-size: 14px; }
.ed-close:hover { color: #aaa; }
.ed-body { padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; flex: 1; min-height: 0; }
.ed-row { display: flex; align-items: center; gap: 10px; }
.ed-row label { color: #666; min-width: 90px; font-size: 11px; }
.ed-color { width: 30px; height: 22px; border: 1px solid #333; border-radius: 3px; background: none; cursor: pointer; padding: 0; }
.ed-range { flex: 1; accent-color: #64b5f6; }
.ed-val   { color: #888; font-size: 11px; min-width: 28px; text-align: right; }
.ed-input {
  flex: 1; background: #1a1a1a; border: 1px solid #333; border-radius: 3px;
  color: #ccc; padding: 3px 7px; font-size: 11px; font-family: monospace;
}
.ed-input:focus { outline: none; border-color: #64b5f6; }
.ed-num { max-width: 120px; }
.ed-sep { height: 1px; background: #1a1a1a; margin: 6px 0; }
.ed-tf-grid {
  display: flex; flex-wrap: wrap; gap: 4px; padding: 4px 0 6px;
}
.ed-tf-chip {
  display: flex; align-items: center; gap: 3px;
  padding: 2px 7px; border-radius: 10px; font-size: 10px;
  border: 1px solid #2a2a2a; background: #1a1a1a; color: #555;
  cursor: pointer; user-select: none; transition: background 0.1s, color 0.1s;
}
.ed-tf-chip--on { background: #1a3a5c; color: #64b5f6; border-color: #1a4a7c; }
.ed-tf-check { display: none; }
.ed-point-title { font-size: 10px; color: #666; text-transform: uppercase; letter-spacing: 0.05em; padding: 4px 0 2px; }
.ed-footer { display: flex; gap: 8px; padding: 9px 14px; border-top: 1px solid #1a1a1a; }
.ed-btn {
  flex: 1; padding: 5px; border-radius: 4px; border: 1px solid #2a2a2a;
  font-family: monospace; font-size: 11px; cursor: pointer;
  background: #1a1a1a; color: #777;
}
.ed-btn:hover { color: #aaa; }
.ed-apply { background: #1a3a5c; color: #64b5f6; border-color: #1a3a5c; }
.ed-apply:hover { background: #1f4a7a; }

/* ── AVWAP presets ────────────────────────────────────────────────────── */
.avwap-presets {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.preset-chip {
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid #2a4a6a;
  background: #0d1f2d;
  color: #64b5f6;
  font-size: 10px;
  cursor: pointer;
  font-family: monospace;
  transition: background 0.1s;
}
.preset-chip:hover { background: #1a3a5c; }

/* ── Membership badges ───────────────────────────────────────────────── */
.membership-row { cursor: pointer; }

.mem-icon { color: #444; font-size: 10px; flex-shrink: 0; }

.mem-badge {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 8px;
  flex-shrink: 0;
  background: #1a1a1a;
  color: #555;
}

/* ── Transitions ──────────────────────────────────────────────────────── */
.slide-enter-active, .slide-leave-active { transition: all 0.18s ease; overflow: hidden; }
.slide-enter-from, .slide-leave-to { opacity: 0; max-height: 0; }
.slide-enter-to, .slide-leave-from { opacity: 1; max-height: 800px; }

.fade-enter-active, .fade-leave-active { transition: opacity 0.15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
