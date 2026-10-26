<template>
  <div id="app" :class="{ 'tc-legacy-app': usesSharedShell }">
    <template v-if="usesSharedShell">
      <header class="tc-app-header">
        <router-link class="tc-app-brand" to="/" aria-label="Charting Platform workstation">
          <span class="tc-app-brand-mark" aria-hidden="true">◈</span>
          <span class="tc-app-brand-name">Charting Platform</span>
        </router-link>
        <nav class="tc-app-navigation" aria-label="Main navigation">
          <router-link
            v-for="item in navigationItems"
            :key="item.path"
            :to="item.path"
            class="tc-app-nav-link"
            :aria-current="isCurrent(item) ? 'page' : undefined"
          >
            <span aria-hidden="true">{{ item.icon }}</span>
            <span>{{ item.label }}</span>
            <span v-if="item.key === 'alerts' && alertsStore.unviewedCount > 0" class="tc-app-nav-badge">
              {{ alertsStore.unviewedCount > 99 ? '99+' : alertsStore.unviewedCount }}
            </span>
          </router-link>
        </nav>
        <div class="tc-app-account">
          <span class="tc-app-account-name">{{ authStore.user?.username ?? 'Account' }}</span>
          <button
            class="tc-app-signout"
            type="button"
            :aria-label="`Sign out ${authStore.user?.username ?? ''}`.trim()"
            @click="authStore.logout()"
          >
            Sign out
          </button>
        </div>
      </header>
      <main class="tc-app-main">
        <div class="tc-app-route-frame">
          <router-view />
        </div>
        <StatusBar />
      </main>
    </template>
    <router-view v-else />
    <Notification />
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { isSharedNavigationItemActive, sharedShellNavigation, usesSharedAppShell } from '@/router'
import { useAuthStore } from '@/stores/auth'
import { useAlertsStore } from '@/stores/alerts'
import Notification from '@/components/common/Notification.vue'
import StatusBar from '@/components/common/StatusBar.vue'

const route = useRoute()
const authStore = useAuthStore()
const alertsStore = useAlertsStore()

watch(() => authStore.isAuthenticated, (authenticated) => {
  if (authenticated) alertsStore.connectWebSocket()
  else alertsStore.disconnectWebSocket()
}, { immediate: true })

const usesSharedShell = computed(() => usesSharedAppShell(route.path))
const navigationItems = sharedShellNavigation
const isCurrent = (item: typeof navigationItems[number]) => isSharedNavigationItemActive(route.path, item.match)
</script>

<style>
:root {
  color-scheme: dark;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  width: 100%;
  min-width: 320px;
  height: 100%;
}
body {
  margin: 0;
  background: var(--tc-shell-bg, #0d1013);
  color: var(--tc-text, #d5dde4);
  font-family: var(--tc-font-family, "Segoe UI", Arial, sans-serif);
}
#app { width: 100%; min-height: 100vh; }
#app:not(.tc-legacy-app) { height: 100vh; overflow: hidden; }
#app.tc-legacy-app {
  height: 100vh;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  overflow: hidden;
  background: var(--tc-shell-bg);
}

.tc-app-header {
  min-height: 48px;
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 0 14px;
  border-bottom: 1px solid var(--tc-border);
  background: linear-gradient(var(--tc-header-top), var(--tc-header-bottom));
  color: var(--tc-text);
}
.tc-app-brand {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
  color: var(--tc-text);
  text-decoration: none;
  font-size: 13px;
  font-weight: 650;
}
.tc-app-brand-mark { color: var(--tc-accent); font-size: 18px; }
.tc-app-navigation {
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
  flex: 1;
  overflow-x: auto;
  scrollbar-width: thin;
}
.tc-app-nav-link {
  min-height: 30px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  position: relative;
  flex: 0 0 auto;
  padding: 0 9px;
  border: 1px solid transparent;
  color: var(--tc-text-muted);
  text-decoration: none;
  font-size: 12px;
  white-space: nowrap;
}
.tc-app-nav-link:hover,
.tc-app-nav-link:focus-visible { color: var(--tc-text); background: #ffffff0a; }
.tc-app-nav-link[aria-current="page"] {
  color: var(--tc-accent-soft);
  border-color: #68b6e933;
  background: #68b6e914;
}
.tc-app-nav-link:focus-visible,
.tc-app-signout:focus-visible,
.tc-app-brand:focus-visible { outline: 2px solid var(--tc-accent); outline-offset: 2px; }
.tc-app-nav-badge {
  min-width: 16px;
  padding: 1px 4px;
  border-radius: 8px;
  background: var(--tc-negative);
  color: #15191e;
  text-align: center;
  font-size: 10px;
  font-weight: 700;
}
.tc-app-account { display: flex; align-items: center; gap: 10px; flex: 0 0 auto; }
.tc-app-account-name { color: var(--tc-text-muted); font-size: 11px; }
.tc-app-signout {
  min-height: 28px;
  padding: 0 9px;
  border: 1px solid var(--tc-border-strong);
  background: var(--tc-control-bg);
  color: var(--tc-text);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}
.tc-app-signout:hover { border-color: var(--tc-accent); }
.tc-app-main { min-width: 0; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
.tc-app-route-frame { flex: 1; min-width: 0; min-height: 0; overflow: hidden; }
.tc-app-route-frame > * { width: 100%; height: 100%; min-width: 0; min-height: 0; }

/* Shared visual tokens for all routed legacy feature surfaces. */
#app.tc-legacy-app .dashboard-view,
#app.tc-legacy-app .chart-view,
#app.tc-legacy-app .alerts-view,
#app.tc-legacy-app .settings-view,
#app.tc-legacy-app .screener-view,
#app.tc-legacy-app .watchlist-view,
#app.tc-legacy-app .radar-view,
#app.tc-legacy-app .strategy-lab-view,
#app.tc-legacy-app .strategy-lab-v2,
#app.tc-legacy-app .basket-view,
#app.tc-legacy-app .holdings-view {
  color: var(--tc-text);
  background-color: var(--tc-window-bg);
  font-family: var(--tc-font-family);
}
#app.tc-legacy-app :is(.dashboard-view,.chart-view,.alerts-view,.settings-view,.screener-view,.watchlist-view,.radar-view,.strategy-lab-view,.strategy-lab-v2,.basket-view,.holdings-view) :is(h1,h2,h3,h4) {
  color: var(--tc-text);
  font-family: var(--tc-font-family);
}
#app.tc-legacy-app :is(.dashboard-view,.chart-view,.alerts-view,.settings-view,.screener-view,.watchlist-view,.radar-view,.strategy-lab-view,.strategy-lab-v2,.basket-view,.holdings-view) :is(p,small,label,.hint,.empty-hint,.td-dim,.history-count) {
  color: var(--tc-text-muted);
}
#app.tc-legacy-app :is(.dashboard-view,.chart-view,.alerts-view,.settings-view,.screener-view,.watchlist-view,.radar-view,.strategy-lab-view,.strategy-lab-v2,.basket-view,.holdings-view) :is(input,select,textarea) {
  border-color: var(--tc-border-strong);
  background-color: var(--tc-input-bg);
  color: var(--tc-text);
  font-family: var(--tc-font-family);
}
#app.tc-legacy-app :is(.dashboard-view,.chart-view,.alerts-view,.settings-view,.screener-view,.watchlist-view,.radar-view,.strategy-lab-view,.strategy-lab-v2,.basket-view,.holdings-view) :is(input,select,textarea):focus-visible {
  outline: 2px solid var(--tc-accent);
  outline-offset: 1px;
}
#app.tc-legacy-app :is(.dashboard-view,.chart-view,.alerts-view,.settings-view,.screener-view,.watchlist-view,.radar-view,.strategy-lab-view,.strategy-lab-v2,.basket-view,.holdings-view) :is(button,.btn,.action-button) {
  font-family: var(--tc-font-family);
}
#app.tc-legacy-app .tc-app-route-frame :is([class*="-card"],[class*="__card"],[class*="-panel"],[class*="__panel"],[class*="-section"],[class*="__section"],[class*="-sidebar"],[class*="__sidebar"],[class*="widget"]) {
  border-color: var(--tc-border);
}
#app.tc-legacy-app .tc-app-route-frame :is([class*="-card"],[class*="__card"],[class*="-panel"],[class*="__panel"],[class*="-section"],[class*="__section"],[class*="-sidebar"],[class*="__sidebar"],[class*="widget"]) {
  background-color: var(--tc-panel-bg);
}
#app.tc-legacy-app .tc-app-route-frame :is([class*="-header"],[class*="__header"],[class*="-toolbar"],[class*="__toolbar"]) {
  border-color: var(--tc-border);
  background-color: var(--tc-header-bottom);
}
#app.tc-legacy-app .tc-app-route-frame :where(:is(button,.btn,.action-button):not([class*="danger"]):not([class*="error"]):not([class*="success"]):not([class*="positive"]):not([class*="negative"]):not([class*="warning"]):not([class*="status"]):not([class*="availability"]):not([class*="capability"]):not([class*="quota"]):not(:disabled):not(:is([aria-selected="true"],[aria-pressed="true"],[class*="--active"],[class*="--selected"],[class~="active"],[class~="selected"]))) {
  border-color: var(--tc-border-strong);
  background-color: var(--tc-control-bg);
  color: var(--tc-text);
}
#app.tc-legacy-app .tc-app-route-frame :where(:is(button,.btn,.action-button):not([class*="danger"]):not([class*="error"]):not([class*="success"]):not([class*="positive"]):not([class*="negative"]):not([class*="warning"]):not([class*="status"]):not([class*="availability"]):not([class*="capability"]):not([class*="quota"]):not(:disabled):not(:is([aria-selected="true"],[aria-pressed="true"],[class*="--active"],[class*="--selected"],[class~="active"],[class~="selected"]))):hover {
  border-color: var(--tc-accent);
}
#app.tc-legacy-app .tc-app-route-frame :is(button,[role="option"],[role="tab"],[role="row"],tr,[class*="-item"],[class*="-card"],[class*="-row"],[class*="-target"]):is([aria-selected="true"],[aria-pressed="true"],[class*="--active"],[class*="--selected"],[class~="active"],[class~="selected"]) {
  border-color: var(--tc-accent);
  background-color: #68b6e91c;
}
#app.tc-legacy-app .tc-app-route-frame :is(button,[role="option"],[role="tab"]):is([aria-selected="true"],[aria-pressed="true"],[class*="--active"],[class*="--selected"],[class~="active"],[class~="selected"]) {
  color: var(--tc-accent-soft);
}
#app.tc-legacy-app .tc-app-route-frame tr:is([class*="--selected"],[class~="selected"]) > td,
#app.tc-legacy-app .tc-app-route-frame tr[aria-selected="true"] > td {
  background-color: #68b6e91c;
}
#app.tc-legacy-app .tc-app-route-frame :is(button,.btn,.action-button):focus-visible {
  outline: 2px solid var(--tc-accent);
  outline-offset: 2px;
}
#app.tc-legacy-app .tc-app-route-frame :is(button,.btn,.action-button):disabled {
  cursor: not-allowed;
  opacity: 0.58;
}
#app.tc-legacy-app .tc-app-route-frame a:not([class*="danger"]):not([class*="error"]) { color: var(--tc-accent-soft); }
#app.tc-legacy-app .tc-app-route-frame table { border-color: var(--tc-border); }
#app.tc-legacy-app .tc-app-route-frame :is(th,thead) { background-color: var(--tc-control-bg); color: var(--tc-text-muted); }
#app.tc-legacy-app .tc-app-route-frame :is(td,th) { border-color: var(--tc-border); }
#app.tc-legacy-app .tc-app-route-frame tr:hover > td { background-color: #68b6e90d; }
#app.tc-legacy-app .tc-app-route-frame tr:is([class*="--selected"],[class~="selected"]):hover > td,
#app.tc-legacy-app .tc-app-route-frame tr[aria-selected="true"]:hover > td {
  background-color: #68b6e91c;
}
#app.tc-legacy-app .tc-app-route-frame :is([role="dialog"],[role="menu"],[role="listbox"]) {
  border-color: var(--tc-border-strong);
  background-color: var(--tc-window-bg);
  color: var(--tc-text);
}
body:has(#app.tc-legacy-app) :is([role="dialog"],[role="menu"],[role="listbox"],[role="tooltip"],[class*="-modal"],[class~="modal"],[class*="-menu"],[class*="-results"],[class*="context-menu"],[class*="popover"],.editor-box,.indicator-settings-dialog,.row-dropdown,.quick-link-menu,.symbol-bars__tooltip,.r-outcome-map__tooltip,.notification) {
  border-color: var(--tc-border-strong);
  background-color: var(--tc-window-bg);
  color: var(--tc-text);
  font-family: var(--tc-font-family);
}
body:has(#app.tc-legacy-app) :is([role="dialog"],[class*="-menu"],[class*="-results"],[class*="-modal"],[class~="modal"],.editor-box,.indicator-settings-dialog,.row-dropdown,.quick-link-menu) :is(button,input,select,textarea) {
  border-color: var(--tc-border-strong);
  background-color: var(--tc-control-bg);
  color: var(--tc-text);
  font-family: var(--tc-font-family);
}
body:has(#app.tc-legacy-app) :is([class*="-menu"],[class*="-results"],.row-dropdown,.quick-link-menu) :is(button,[role="option"]):is([aria-selected="true"],[aria-pressed="true"],[class~="active"],[class~="highlighted"]) {
  border-color: var(--tc-accent);
  background-color: #68b6e91c;
  color: var(--tc-accent-soft);
}
#app.tc-legacy-app .tc-app-route-frame :is(.error,.err,[role="alert"]) { color: var(--tc-negative); }
#app.tc-legacy-app .tc-app-route-frame :is(.success,.ok,.positive) { color: var(--tc-positive); }
#app.tc-legacy-app .tc-app-route-frame :is(.warning,.warn) { color: var(--tc-warning); }
#app.tc-legacy-app .tc-app-route-frame ::selection { background: #68b6e955; color: #f4f8fb; }
#app.tc-legacy-app .tc-app-route-frame * { scrollbar-color: var(--tc-border-strong) var(--tc-window-bg); }

@media (max-width: 900px) {
  .tc-app-header { flex-wrap: wrap; gap: 6px 12px; padding: 8px 10px 0; }
  .tc-app-navigation { order: 3; flex-basis: 100%; }
  .tc-app-account { margin-left: auto; }
  .tc-app-nav-link { min-height: 32px; padding: 0 8px; }
}
@media (max-width: 520px) {
  .tc-app-brand-name { font-size: 12px; }
  .tc-app-account-name { display: none; }
  .tc-app-header { gap: 4px 8px; }
  #app.tc-legacy-app .tc-app-route-frame :is(.settings-view,.alerts-view,.radar-view,.strategy-lab-v2,.holdings-view) { padding-left: 12px; padding-right: 12px; }
}
</style>
