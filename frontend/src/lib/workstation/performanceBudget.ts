/**
 * Dense workstation rendering budget.
 *
 * This is an observability contract, not a data-source or acceptance policy:
 * callers may report whether a rendered row universe fits the documented
 * stress target without truncating or substituting rows.
 */
export const WORKSTATION_ROW_BUDGET = 10_000

export type WorkstationRowBudgetState = 'within' | 'exceeded'

export function workstationRowBudgetState(rowCount: number): WorkstationRowBudgetState {
  return Number.isFinite(rowCount) && rowCount <= WORKSTATION_ROW_BUDGET ? 'within' : 'exceeded'
}
