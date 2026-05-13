import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { api } from '@/lib/api'
import type {
  StrategyDefinition,
  StrategyRun,
  StrategyVersion,
} from '@/types'

export const useStrategyLabStore = defineStore('strategy_lab', () => {
  const definitions = ref<StrategyDefinition[]>([])
  const selectedDefinitionId = ref<number | null>(null)
  const selectedRunId = ref<number | null>(null)
  const isLoading = ref(false)
  const isSaving = ref(false)
  const isRunning = ref(false)
  const error = ref<string | null>(null)

  const selectedDefinition = computed(() =>
    definitions.value.find(item => item.id === selectedDefinitionId.value) ?? null
  )
  const selectedRun = computed(() => {
    const byDefinition = selectedDefinition.value?.runs ?? []
    return byDefinition.find(run => run.id === selectedRunId.value) ?? null
  })

  async function loadAll() {
    isLoading.value = true
    error.value = null
    try {
      definitions.value = await api.get<StrategyDefinition[]>('/strategy-lab/definitions')
      if (!selectedDefinitionId.value || !definitions.value.some(item => item.id === selectedDefinitionId.value)) {
        selectedDefinitionId.value = definitions.value[0]?.id ?? null
      }
    } catch (err: any) {
      error.value = err?.message ?? 'Failed to load Strategy Lab'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function refreshDefinition(id: number) {
    const updated = await api.get<StrategyDefinition>(`/strategy-lab/definitions/${id}`)
    const index = definitions.value.findIndex(item => item.id === id)
    if (index === -1) definitions.value.unshift(updated)
    else definitions.value[index] = updated
    return updated
  }

  async function createDefinition(payload: Record<string, any>) {
    isSaving.value = true
    error.value = null
    try {
      const created = await api.post<StrategyDefinition>('/strategy-lab/definitions', payload)
      definitions.value.unshift(created)
      selectedDefinitionId.value = created.id
      return created
    } catch (err: any) {
      error.value = err?.message ?? 'Failed to create strategy definition'
      throw err
    } finally {
      isSaving.value = false
    }
  }

  async function updateDefinition(id: number, payload: Record<string, any>) {
    isSaving.value = true
    error.value = null
    try {
      const updated = await api.patch<StrategyDefinition>(`/strategy-lab/definitions/${id}`, payload)
      const index = definitions.value.findIndex(item => item.id === id)
      if (index >= 0) definitions.value[index] = updated
      return updated
    } catch (err: any) {
      error.value = err?.message ?? 'Failed to update strategy definition'
      throw err
    } finally {
      isSaving.value = false
    }
  }

  async function deleteDefinition(id: number) {
    isSaving.value = true
    error.value = null
    try {
      await api.delete(`/strategy-lab/definitions/${id}`)
      definitions.value = definitions.value.filter(item => item.id !== id)
      if (selectedDefinitionId.value === id) {
        selectedDefinitionId.value = definitions.value[0]?.id ?? null
        selectedRunId.value = null
      }
    } catch (err: any) {
      error.value = err?.message ?? 'Failed to delete strategy definition'
      throw err
    } finally {
      isSaving.value = false
    }
  }

  async function publishVersion(strategyId: number, payload: Record<string, any>) {
    isSaving.value = true
    error.value = null
    try {
      const created = await api.post<StrategyVersion>(`/strategy-lab/definitions/${strategyId}/versions`, payload)
      await refreshDefinition(strategyId)
      return created
    } catch (err: any) {
      error.value = err?.message ?? 'Failed to publish strategy version'
      throw err
    } finally {
      isSaving.value = false
    }
  }

  async function runVersion(versionId: number, payload: Record<string, any>) {
    isRunning.value = true
    error.value = null
    try {
      const submitted = await api.post<StrategyRun>(`/strategy-lab/versions/${versionId}/runs`, payload)
      await refreshDefinition(submitted.strategy_id)
      selectedDefinitionId.value = submitted.strategy_id
      selectedRunId.value = submitted.id
      return submitted
    } catch (err: any) {
      error.value = err?.message ?? 'Failed to run strategy version'
      throw err
    } finally {
      isRunning.value = false
    }
  }

  async function refreshRun(runId: number) {
    isRunning.value = true
    error.value = null
    try {
      const refreshed = await api.post<StrategyRun>(`/strategy-lab/runs/${runId}/refresh`, {})
      await refreshDefinition(refreshed.strategy_id)
      selectedDefinitionId.value = refreshed.strategy_id
      selectedRunId.value = refreshed.id
      return refreshed
    } catch (err: any) {
      error.value = err?.message ?? 'Failed to refresh strategy run'
      throw err
    } finally {
      isRunning.value = false
    }
  }

  function selectDefinition(id: number | null) {
    selectedDefinitionId.value = id
    selectedRunId.value = null
  }

  return {
    definitions,
    selectedDefinitionId,
    selectedRunId,
    selectedDefinition,
    selectedRun,
    isLoading,
    isSaving,
    isRunning,
    error,
    loadAll,
    refreshDefinition,
    createDefinition,
    updateDefinition,
    deleteDefinition,
    publishVersion,
    runVersion,
    refreshRun,
    selectDefinition,
  }
})
