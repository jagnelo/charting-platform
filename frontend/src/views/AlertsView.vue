<template>
  <div class="alerts-view">
    <h2 class="page-title">All Alerts</h2>
    <div class="filter-bar">
      <select v-model="statusFilter" class="filter-select">
        <option value="">All statuses</option>
        <option value="active">Active</option>
        <option value="triggered">Triggered</option>
        <option value="paused">Paused</option>
      </select>
    </div>
    <div class="alerts-table-wrap">
      <table class="alerts-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Condition</th>
            <th>Threshold</th>
            <th>Status</th>
            <th>Repeat</th>
            <th>Triggered</th>
            <th>Notes</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in filtered" :key="a.id" :class="`row--${a.status}`">
            <td class="td-symbol">
              <router-link :to="`/chart/${a.instrument_id}`">—</router-link>
            </td>
            <td>{{ a.condition.replace(/_/g, ' ') }}</td>
            <td class="td-mono">${{ a.threshold_price }}</td>
            <td><span :class="`status-badge status-badge--${a.status}`">{{ a.status }}</span></td>
            <td>{{ a.repeat ? '↺' : '—' }}</td>
            <td class="td-mono">{{ a.triggered_at ? new Date(a.triggered_at).toLocaleString() : '—' }}</td>
            <td class="td-notes">{{ a.notes ?? '' }}</td>
            <td class="td-actions">
              <button v-if="a.status === 'triggered'" @click="alertsStore.rearmAlert(a.id)" title="Rearm">↺</button>
              <button @click="alertsStore.deleteAlert(a.id)" title="Delete" class="btn-danger">✕</button>
            </td>
          </tr>
          <tr v-if="!filtered.length">
            <td colspan="8" class="empty-row">No alerts match the current filter</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useAlertsStore } from '@/stores/alerts'

const alertsStore = useAlertsStore()
const statusFilter = ref('')

const filtered = computed(() =>
  statusFilter.value
    ? alertsStore.alerts.filter(a => a.status === statusFilter.value)
    : alertsStore.alerts
)

onMounted(() => alertsStore.loadAlerts())
</script>

<style scoped>
.alerts-view { padding: 24px; color: #ccc; font-size: 13px; }
.page-title  { color: #fff; font-size: 20px; margin-bottom: 16px; }
.filter-bar  { margin-bottom: 12px; }
.filter-select { background: #1a1a1a; border: 1px solid #333; color: #aaa; padding: 4px 8px; border-radius: 3px; }

.alerts-table-wrap { overflow-x: auto; }
.alerts-table { width: 100%; border-collapse: collapse; font-family: monospace; font-size: 12px; }
.alerts-table th { background: #111; color: #666; text-align: left; padding: 8px 12px; border-bottom: 1px solid #222; font-weight: 600; }
.alerts-table td { padding: 7px 12px; border-bottom: 1px solid #1a1a1a; }
.alerts-table tr:hover td { background: #111; }

.row--triggered td { color: #555; }

.td-symbol a { color: #64b5f6; text-decoration: none; }
.td-mono  { font-family: monospace; }
.td-notes { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #666; }

.status-badge { padding: 2px 7px; border-radius: 10px; font-size: 10px; text-transform: uppercase; }
.status-badge--active    { background: #1a3a1a; color: #66bb6a; border: 1px solid #2e6b2e; }
.status-badge--triggered { background: #1a1a1a; color: #555;    border: 1px solid #333; }
.status-badge--paused    { background: #2a2a1a; color: #ffd54f; border: 1px solid #4a4a1a; }

.td-actions { display: flex; gap: 6px; }
.td-actions button { background: none; border: 1px solid #333; color: #777; border-radius: 3px; padding: 2px 7px; cursor: pointer; }
.td-actions button:hover { color: #aaa; }
.td-actions .btn-danger:hover { border-color: #ef5350; color: #ef5350; }

.empty-row { text-align: center; color: #444; padding: 32px; }
</style>
