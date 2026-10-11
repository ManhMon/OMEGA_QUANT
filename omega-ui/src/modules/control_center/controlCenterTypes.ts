import type { ActiveTask } from '../../hooks/useControlOps';
import type { OperationsCircuitBreakerResponse } from '../../api/advancedQuant';
import type { ComputeAlphasParams, IngestDataParams, OptimizePortfolioParams, RunBacktestParams } from '../../api/client';

export const CONTROL_CENTER_TABS = ['overview', 'ingest', 'alphas', 'portfolio', 'backtest', 'receipts', 'copilot', 'llm_bridge'] as const;
export type ControlCenterTab = typeof CONTROL_CENTER_TABS[number];

export type RunOperation = (name: string, operation: () => Promise<unknown>) => Promise<void>;
export interface OverviewTabProps { activeTasks: ActiveTask[]; isKillSwitchEngaged: boolean; onOpenOps(): void; onKillSwitch(): void; onBreakerObservation?(value: OperationsCircuitBreakerResponse | null): void; }
export interface IngestTabProps { activeTasks: ActiveTask[]; runOperation: RunOperation; onIngest(params: IngestDataParams): Promise<unknown>; onStopIngest(): Promise<unknown>; sources: string[]; setSources(value: string[]): void; forceRefresh: boolean; setForceRefresh(value: boolean): void; }
export interface AlphasTabProps { runOperation: RunOperation; onCompute(params: ComputeAlphasParams): Promise<unknown>; universe: string; setUniverse(value: string): void; }
export interface PortfolioTabProps { runOperation: RunOperation; onOptimize(params: OptimizePortfolioParams): Promise<unknown>; onRebalance(): Promise<unknown>; objective: string; setObjective(value: string): void; maxWeight: string; setMaxWeight(value: string): void; universe: string; setUniverse(value: string): void; }
export interface BacktestTabProps { runOperation: RunOperation; onRun(params: RunBacktestParams): Promise<unknown>; strategyId: string; setStrategyId(value: string): void; startDate: string; setStartDate(value: string): void; slippageBps: string; setSlippageBps(value: string): void; commissionBps: string; setCommissionBps(value: string): void; }
export interface ReceiptsTabProps { onOpenOps(): void; }
