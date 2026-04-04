/** Backtest models */

export interface BacktestRunRequest {
  tickers: string[];
  start_date: string;
  end_date: string;
  initial_capital: number;
  strategy: string;
}

export interface BacktestRunResponse {
  job_id: string;
  status: string;
  submitted_at: string;
}

export interface BacktestTrade {
  date: string;
  ticker: string;
  side: 'buy' | 'sell';
  quantity: number;
  price: number;
  pnl: number;
  charges?: number;
  exit_reason?: string;
}

export interface BacktestResults {
  job_id: string;
  status: string;
  tickers: string[];
  start_date: string;
  end_date: string;
  initial_capital: number;
  final_value: number;
  total_return_pct: number;
  sharpe_ratio: number | null;
  sortino_ratio: number | null;
  max_drawdown_pct: number | null;
  cagr_pct: number | null;
  total_charges: number;
  win_rate: number | null;
  avg_win: number | null;
  avg_loss: number | null;
  expectancy: number | null;
  total_trades: number;
  no_trade_count: number;
  rejection_count: number;
  trades: BacktestTrade[];
  completed_at: string | null;
  error?: string | null;
}
