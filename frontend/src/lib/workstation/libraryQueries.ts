import type { QueryClient } from '@tanstack/vue-query'
import { api } from '@/lib/api'

export type CodeAssetSummary = {
  kind: string
  name: string
  versions: Array<{
    id?: number
    version_number: number
    output_contract?: string
    diagnostics?: Array<Record<string, unknown>>
  }>
}

export const CODE_ASSETS_QUERY_KEY = ['workstation', 'code-assets'] as const

export function fetchCodeAssets(queryClient: QueryClient) {
  return queryClient.fetchQuery<CodeAssetSummary[]>({
    queryKey: CODE_ASSETS_QUERY_KEY,
    queryFn: async () => (await api.get<CodeAssetSummary[]>('/code/assets')) ?? [],
    staleTime: 30_000,
  })
}

export function invalidateCodeAssets(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: CODE_ASSETS_QUERY_KEY })
}
