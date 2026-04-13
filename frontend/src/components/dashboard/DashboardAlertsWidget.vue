<template>
  <div class="dash-alerts">
    <div class="alert-filter">
      <button :class="{ active: filter === 'all' }" @click="filter = 'all'">All</button>
      <button :class="{ active: filter === 'price' }" @click="filter = 'price'">Price</button>
      <button :class="{ active: filter === 'indicator' }" @click="filter = 'indicator'">Indicator</button>
      <button :class="{ active: filter === 'screener' }" @click="filter = 'screener'">Screener</button>
    </div>
    <div class="alert-list">
      <div v-for="row in rows" :key="row.key" class="alert-row">
        <span class="type" :class="row.type">{{ row.type }}</span>
        <b>{{ row.title }}</b>
        <small>{{ row.detail }}</small>
        <em :class="row.status">{{ row.status }}</em>
      </div>
      <div v-if="!rows.length" class="empty-small">No alerts.</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAlertsStore } from '@/stores/alerts'
import { useScreenerAlertsStore } from '@/stores/screener_alerts'

const alertsStore = useAlertsStore()
const screenerAlertsStore = useScreenerAlertsStore()
const filter = ref<'all' | 'price' | 'indicator' | 'screener'>('all')

const rows = computed(() => {
  const price = alertsStore.alerts.map(alert => ({
    key: `price-${alert.id}`,
    type: 'price',
    title: alert.instrument_symbol,
    detail: `${alert.condition.replace(/_/g, ' ')} ${Number(alert.threshold_price).toFixed(2)}`,
    status: alert.status,
  }))
  const indicator = alertsStore.indicatorAlerts.map(alert => ({
    key: `indicator-${alert.id}`,
    type: 'indicator',
    title: alert.instrument_symbol,
    detail: `${alert.indicator_a_type.toUpperCase()} ${alert.condition.replace(/_/g, ' ')}`,
    status: alert.status,
  }))
  const screener = screenerAlertsStore.alerts.map(alert => ({
    key: `screener-${alert.id}`,
    type: 'screener',
    title: alert.screener_name,
    detail: `${alert.trigger_type} membership`,
    status: alert.status,
  }))
  return [...price, ...indicator, ...screener]
    .filter(row => filter.value === 'all' || row.type === filter.value)
})
</script>

<style scoped>
.dash-alerts {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.alert-filter {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
  flex-shrink: 0;
}
.alert-filter button {
  background: #151515;
  color: #888;
  border: 1px solid #282828;
  border-radius: 4px;
  padding: 4px 6px;
  font-family: inherit;
  font-size: 9px;
  cursor: pointer;
}
.alert-filter button.active {
  color: #64b5f6;
  border-color: #245177;
}
.alert-list {
  min-height: 0;
  flex: 1;
  overflow: auto;
}
.alert-row {
  display: grid;
  grid-template-columns: 58px minmax(0, 82px) 1fr auto;
  gap: 7px;
  align-items: center;
  min-height: 30px;
  padding: 5px 0;
  border-bottom: 1px solid #181818;
  font-size: 10px;
}
.type {
  border-radius: 4px;
  padding: 3px 5px;
  text-transform: uppercase;
  font-size: 8px;
  text-align: center;
  border: 1px solid #2a2a2a;
  color: #888;
}
.type.price { color: #ffb74d; }
.type.indicator { color: #64b5f6; }
.type.screener { color: #81c784; }
.alert-row b {
  color: #ddd;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.alert-row small {
  color: #777;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.alert-row em {
  font-style: normal;
  color: #777;
  font-size: 9px;
}
.alert-row em.active { color: #81c784; }
.alert-row em.triggered { color: #ffb74d; }
.alert-row em.paused { color: #ffd54f; }
.empty-small {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #555;
  font-size: 12px;
  text-align: center;
}
</style>
