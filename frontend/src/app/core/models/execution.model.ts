/** Execution quality models */

export interface ExecutionStats {
  total_orders: number;
  filled_count: number;
  avg_fill_time_ms: number;
  avg_slippage_bps: number;
  fill_rate: number;
  [key: string]: unknown;
}

export interface ExecutionReport {
  order_id: string;
  symbol: string;
  side: string;
  quantity: number;
  filled_price: number;
  expected_price: number;
  slippage_bps: number;
  fill_time_ms: number;
  timestamp: string;
  order_type: string;
  status: string;
  [key: string]: unknown;
}

export interface OrderTypeDecision {
  order_type: string;
}

export interface PriceCheckResult {
  ok: boolean;
  message: string;
}

export interface LiquidityCheckResult {
  ok: boolean;
  warnings: string[];
}
