import {
  Component, ChangeDetectionStrategy, ChangeDetectorRef,
  OnDestroy,
} from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, takeUntil, catchError, of, timer, switchMap, EMPTY } from 'rxjs';

import { BacktestApiService } from '../services/backtest-api.service';
import { NotificationService } from '../services/notification.service';
import {
  BacktestRunRequest, BacktestResults, BacktestTrade,
} from '../core/models/backtest.model';

import {
  StatCardComponent, StateBadgeComponent, LoadingSkeletonComponent,
  EmptyStateComponent, TradingChartComponent,
  BadgeVariant, StatCardConfig, PricePoint,
} from '../shared';

@Component({
  selector: 'app-backtest',
  standalone: true,
  imports: [
    CommonModule, FormsModule, DecimalPipe,
    StatCardComponent, StateBadgeComponent, LoadingSkeletonComponent,
    EmptyStateComponent, TradingChartComponent,
  ],
  templateUrl: './backtest.component.html',
  styleUrl: './backtest.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BacktestComponent implements OnDestroy {
  // Form
  tickersInput = 'RELIANCE, TCS';
  strategy = 'momentum';
  startDate = '2025-06-01';
  endDate = '2026-03-31';
  initialCapital = 100000;

  // State
  submitting = false;
  jobId: string | null = null;
  jobStatus = 'pending';
  polling = false;
  results: BacktestResults | null = null;
  error: string | null = null;

  // Pagination
  currentPage = 0;
  readonly tradesPerPage = 20;

  // Equity curve
  equityCurve: PricePoint[] = [];

  private destroy$ = new Subject<void>();
  private pollDone$ = new Subject<void>();

  constructor(
    private cdr: ChangeDetectorRef,
    private backtestApi: BacktestApiService,
    private notify: NotificationService,
  ) {}

  ngOnDestroy(): void {
    this.pollDone$.next();
    this.pollDone$.complete();
    this.destroy$.next();
    this.destroy$.complete();
  }

  // ── Computed ──
  get tradesStart(): number { return this.currentPage * this.tradesPerPage; }
  get tradesEnd(): number {
    return Math.min(this.tradesStart + this.tradesPerPage, this.results?.trades.length ?? 0);
  }

  get displayedTrades(): BacktestTrade[] {
    return this.results?.trades.slice(this.tradesStart, this.tradesEnd) ?? [];
  }

  get totalPages(): number {
    return Math.ceil((this.results?.trades.length ?? 0) / this.tradesPerPage);
  }

  get resultCards(): StatCardConfig[] {
    if (!this.results) return [];
    const r = this.results;
    return [
      {
        label: 'Final Value',
        value: `₹${r.final_value.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`,
        icon: 'cash-stack',
      },
      {
        label: 'Total Return',
        value: `${r.total_return_pct.toFixed(2)}%`,
        icon: 'percent',
        trend: r.total_return_pct >= 0 ? 'up' : 'down',
      },
      {
        label: 'Sharpe Ratio',
        value: r.sharpe_ratio != null ? r.sharpe_ratio.toFixed(2) : 'N/A',
        icon: 'bar-chart-line',
      },
      {
        label: 'Sortino Ratio',
        value: r.sortino_ratio != null ? r.sortino_ratio.toFixed(2) : 'N/A',
        icon: 'bar-chart-line-fill',
      },
      {
        label: 'Max Drawdown',
        value: r.max_drawdown_pct != null ? `${r.max_drawdown_pct.toFixed(2)}%` : 'N/A',
        icon: 'graph-down-arrow',
        trend: 'down',
      },
      {
        label: 'Win Rate',
        value: r.win_rate != null ? `${r.win_rate.toFixed(1)}%` : 'N/A',
        icon: 'trophy',
        trend: (r.win_rate ?? 0) >= 50 ? 'up' : 'down',
      },
      {
        label: 'Expectancy',
        value: r.expectancy != null ? `₹${r.expectancy.toFixed(2)}` : 'N/A',
        icon: 'calculator',
        trend: (r.expectancy ?? 0) >= 0 ? 'up' : 'down',
      },
      {
        label: 'Total Charges',
        value: `₹${(r.total_charges ?? 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`,
        icon: 'currency-rupee',
      },
    ];
  }

  get tradeStats(): { label: string; value: string }[] {
    if (!this.results) return [];
    const r = this.results;
    const sells = r.trades.filter(t => t.side === 'sell');
    const wins = sells.filter(t => t.pnl > 0);
    const losses = sells.filter(t => t.pnl < 0);
    const totalPnl = sells.reduce((s, t) => s + t.pnl, 0);
    const avgWin = r.avg_win ?? (wins.length ? wins.reduce((s, t) => s + t.pnl, 0) / wins.length : 0);
    const avgLoss = r.avg_loss ?? (losses.length ? losses.reduce((s, t) => s + t.pnl, 0) / losses.length : 0);
    return [
      { label: 'Round-Trip Trades', value: `${r.total_trades ?? sells.length}` },
      { label: 'Winning', value: `${wins.length}` },
      { label: 'Losing', value: `${losses.length}` },
      { label: 'Win Rate', value: r.win_rate != null ? `${r.win_rate.toFixed(1)}%` : 'N/A' },
      { label: 'Total P&L', value: `₹${totalPnl.toLocaleString('en-IN', { maximumFractionDigits: 2 })}` },
      { label: 'Avg Win', value: `₹${avgWin.toFixed(2)}` },
      { label: 'Avg Loss', value: `₹${avgLoss.toFixed(2)}` },
      { label: 'Profit Factor', value: losses.length && avgLoss !== 0 ? Math.abs(avgWin / avgLoss).toFixed(2) : 'N/A' },
      { label: 'Rejections', value: `${r.rejection_count ?? 0}` },
      { label: 'No-Trade Signals', value: `${r.no_trade_count ?? 0}` },
    ];
  }

  sideBadge(side: string): BadgeVariant {
    return side === 'buy' ? 'buy' : 'sell';
  }

  statusBadge(status: string): BadgeVariant {
    switch (status) {
      case 'completed': return 'success';
      case 'failed': return 'danger';
      case 'running': return 'running';
      default: return 'pending';
    }
  }

  get isFormValid(): boolean {
    const tickers = this.tickersInput.split(',').map(t => t.trim()).filter(t => t);
    return tickers.length > 0 && !!this.startDate && !!this.endDate && this.initialCapital >= 1000;
  }

  // ── Actions ──
  submitBacktest(): void {
    const tickers = this.tickersInput.split(',').map(t => t.trim()).filter(t => t);
    if (tickers.length === 0) {
      this.notify.warning('Enter at least one ticker.');
      return;
    }

    this.submitting = true;
    this.results = null;
    this.jobId = null;
    this.error = null;
    this.equityCurve = [];
    this.cdr.markForCheck();

    const request: BacktestRunRequest = {
      tickers,
      start_date: this.startDate,
      end_date: this.endDate,
      initial_capital: this.initialCapital,
      strategy: this.strategy,
    };

    this.backtestApi.runBacktest(request).pipe(
      catchError(err => {
        this.error = err?.error?.detail || 'Failed to submit backtest.';
        this.submitting = false;
        this.cdr.markForCheck();
        return EMPTY;
      }),
      takeUntil(this.destroy$),
    ).subscribe(res => {
      this.jobId = res.job_id;
      this.jobStatus = res.status;
      this.submitting = false;
      this.notify.success('Backtest submitted.');
      this.cdr.markForCheck();
      this.startPolling();
    });
  }

  pollResults(): void {
    if (!this.jobId) return;
    this.polling = true;
    this.cdr.markForCheck();

    this.backtestApi.getResults(this.jobId).pipe(
      catchError(() => { this.polling = false; this.cdr.markForCheck(); return EMPTY; }),
      takeUntil(this.destroy$),
    ).subscribe(res => {
      this.polling = false;
      this.handleResult(res);
      this.cdr.markForCheck();
    });
  }

  prevPage(): void { if (this.currentPage > 0) this.currentPage--; }
  nextPage(): void { if (this.tradesEnd < (this.results?.trades.length ?? 0)) this.currentPage++; }

  // ── Private ──
  private startPolling(): void {
    this.pollDone$ = new Subject<void>();
    timer(2000, 3000).pipe(
      switchMap(() => {
        if (!this.jobId) return EMPTY;
        this.polling = true;
        this.cdr.markForCheck();
        return this.backtestApi.getResults(this.jobId).pipe(catchError(() => EMPTY));
      }),
      takeUntil(this.pollDone$),
      takeUntil(this.destroy$),
    ).subscribe(res => {
      this.polling = false;
      this.handleResult(res);
      this.cdr.markForCheck();
    });
  }

  private handleResult(res: BacktestResults): void {
    if (res.status === 'completed') {
      this.results = res;
      this.currentPage = 0;
      this.buildEquityCurve(res);
      this.pollDone$.next();
      this.notify.success('Backtest completed!');
    } else if (res.status === 'failed') {
      this.jobStatus = 'failed';
      this.error = res.error || 'Backtest job failed.';
      this.pollDone$.next();
      this.notify.error(this.error);
    } else {
      this.jobStatus = res.status;
    }
  }

  private buildEquityCurve(res: BacktestResults): void {
    if (!res.trades.length) return;
    let equity = res.initial_capital;
    // Use a map to keep only the last equity value per date (lightweight-charts needs strictly ascending times)
    const map = new Map<string, number>();
    map.set(res.start_date.split(' ')[0], equity);
    for (const t of res.trades) {
      equity += t.pnl;
      map.set(t.date.split(' ')[0], equity);
    }
    this.equityCurve = Array.from(map, ([time, value]) => ({ time, value } as PricePoint));
  }
}
