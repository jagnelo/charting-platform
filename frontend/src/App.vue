<template>
  <div id="app">
    <template v-if="!isLoginPage">
      <nav class="sidebar">
        <div class="sidebar-logo" title="Charting Platform">
          <span class="logo-mark">◈</span>
        </div>
        <router-link to="/dashboard" class="nav-link" title="Dashboard">▦</router-link>
        <router-link :to="chartLink" class="nav-link" :class="{ 'router-link-active': route.path.startsWith('/chart') }" title="Chart">📈</router-link>
        <router-link to="/alerts" class="nav-link nav-link--bell" title="Alerts">
          🔔
          <span v-if="alertsStore.unviewedCount > 0" class="nav-badge">
            {{ alertsStore.unviewedCount > 99 ? '99+' : alertsStore.unviewedCount }}
          </span>
        </router-link>
        <router-link to="/radar" class="nav-link" title="Radar">◎</router-link>
        <router-link to="/watchlist" class="nav-link" title="Watchlist">★</router-link>
        <router-link to="/screener"  class="nav-link" title="Screener">🔍</router-link>
        <router-link to="/settings"  class="nav-link" title="Settings">⚙</router-link>
        <div class="sidebar-spacer" />
        <button
          class="user-avatar logout-btn"
          type="button"
          title="Sign out"
          :aria-label="`Sign out ${authStore.user?.username ?? ''}`.trim()"
          @click="authStore.logout()"
        >
          {{ userInitial }}
        </button>
      </nav>
      <main class="main-content">
        <div class="route-frame">
          <router-view />
        </div>
        <StatusBar />
      </main>
    </template>
    <template v-else>
      <router-view />
    </template>
    <Notification />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useChartStore } from '@/stores/chart'
import { useAlertsStore } from '@/stores/alerts'
import Notification from '@/components/common/Notification.vue'
import StatusBar from '@/components/common/StatusBar.vue'

const route       = useRoute()
const authStore   = useAuthStore()
const chartStore  = useChartStore()
const alertsStore = useAlertsStore()

onMounted(() => {
  alertsStore.connectWebSocket()
})

const isLoginPage  = computed(() => route.path === '/login')
const userInitial  = computed(() => (authStore.user?.username?.[0] ?? '?').toUpperCase())
const chartLink    = computed(() => chartStore.symbol ? `/chart/${chartStore.symbol}` : '/chart')
</script>

<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  width: 100%;
  height: 100%;
}
body {
  background: #080808;
  color: #ccc;
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', ui-monospace, monospace;
  overflow: hidden;
}
#app { display: flex; width: 100%; height: 100vh; overflow: hidden; }

.sidebar {
  width: 48px;
  background: #0a0a0a;
  border-right: 1px solid #161616;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px 0;
  gap: 4px;
  flex-shrink: 0;
}

.sidebar-logo { color: #64b5f6; font-size: 20px; margin-bottom: 12px; }

.nav-link {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 6px;
  text-decoration: none;
  color: #444;
  font-size: 16px;
  transition: background 0.12s, color 0.12s;
}
.nav-link:hover { background: #141414; color: #888; }
.nav-link.router-link-active { background: #0f1f2e; color: #64b5f6; }

.nav-link--bell { position: relative; }
.nav-badge {
  position: absolute;
  top: 2px;
  right: 2px;
  background: #ef5350;
  color: #fff;
  border-radius: 8px;
  font-size: 9px;
  min-width: 14px;
  height: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 3px;
  font-weight: 700;
  line-height: 1;
  pointer-events: none;
}

.sidebar-spacer { flex: 1; }

.user-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: #1a3a5c;
  color: #64b5f6;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  margin-bottom: 4px;
  border: 1px solid #2a4a6c;
  padding: 0;
}
.user-avatar:hover { background: #1e4a7a; }

.main-content {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.route-frame {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
.route-frame > * {
  height: 100%;
}
</style>
