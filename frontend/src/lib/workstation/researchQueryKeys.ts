/** Shared cache identities for persisted Research runs and their result list. */
export const researchRunsQueryKey = ['workstation', 'research-runs'] as const
export const researchRunQueryKey = (runId: number) => ['workstation', 'research-run', runId] as const
