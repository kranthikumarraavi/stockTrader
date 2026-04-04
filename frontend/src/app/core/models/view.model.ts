/** View-model types used by page components for display-only concerns */

// ── Market Overview page ──

export interface IndexCard {
  symbol: string;
  displayName: string;
  price: number;
  change: number;
  changePct: number;
  sparkline: number[];
}

export interface MoverRow {
  symbol: string;
  price: number;
  change: number;
  changePct: number;
  volume: number;
}

export interface SectorPerf {
  sector: string;
  changePct: number;
  symbolCount: number;
}

export interface RegimeCard {
  symbol: string;
  regime: string;
  confidence: number;
  volatility: number;
}

export interface MarketBreadth {
  advances: number;
  declines: number;
  unchanged: number;
  total: number;
  advanceRatio: number;
}

// ── Live Chart page ──

export type Timeframe = '1m' | '5m' | '15m' | '1h' | '1D';

export interface OhlcSummary {
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  prevClose: number;
}

export interface WatchlistEntry {
  symbol: string;
  price: number;
  change: number;
  changePct: number;
}

// ── Portfolio page ──

export interface KvEntry {
  key: string;
  value: number;
}

export interface ExposureCategory {
  key: string;
  entries: KvEntry[];
}

// ── Risk page ──

export interface RiskSnapshot {
  timestamp: string;
  capital: number;
  used_capital: number;
  daily_pnl: number;
  open_positions: number;
  [key: string]: unknown;
}

// ── Strategy page ──

export interface StrategyStats {
  total_decisions: number;
  accuracy: number;
  avg_confidence: number;
  [key: string]: unknown;
}

export interface StrategyHistoryEntry {
  ticker: string;
  strategy: string;
  reason: string;
  confidence: number;
  timestamp: string;
  [key: string]: unknown;
}

// ── Options page ──

export interface PayoffPoint {
  spot: number;
  pnl: number;
  payoff: number;
}

// ── Portfolio allocation ──

export interface CapitalAllocation {
  strategy: string;
  allocation_pct: number;
  current_value: number;
  [key: string]: unknown;
}

export interface DailySummary {
  date: string;
  pnl: number;
  trades: number;
  win_rate: number;
  [key: string]: unknown;
}
