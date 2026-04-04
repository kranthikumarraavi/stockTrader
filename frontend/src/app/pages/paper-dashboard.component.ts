import {
  Component, ChangeDetectionStrategy, ChangeDetectorRef,
  OnInit, OnDestroy,
} from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { Subject, takeUntil, catchError, of, forkJoin } from 'rxjs';

import { PaperApiService } from '../services/paper-api.service';
import { NotificationService } from '../services/notification.service';
import { PaperAccount, EquityPoint, AccountMetrics } from '../core/models/paper.model';

import {
  StatCardComponent, StateBadgeComponent, LoadingSkeletonComponent,
  EmptyStateComponent, TradingChartComponent,
  StatCardConfig, PricePoint,
} from '../shared';

@Component({
  selector: 'app-paper-dashboard',
  standalone: true,
  imports: [
    CommonModule, FormsModule, DecimalPipe,
    StatCardComponent, StateBadgeComponent, LoadingSkeletonComponent,
    EmptyStateComponent, TradingChartComponent,
  ],
  templateUrl: './paper-dashboard.component.html',
  styleUrl: './paper-dashboard.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PaperDashboardComponent implements OnInit, OnDestroy {
  accounts: PaperAccount[] = [];
  selectedId: string | null = null;
  loading = true;
  creating = false;

  // Selected account detail
  metrics: AccountMetrics | null = null;
  equityData: EquityPoint[] = [];
  equityCurve: PricePoint[] = [];
  metricsLoading = false;

  // Paper order form
  orderTicker = '';
  orderSide: 'buy' | 'sell' = 'buy';
  orderQty = 1;
  orderType: 'market' | 'limit' = 'market';
  orderLimitPrice: number | null = null;
  submittingOrder = false;

  private destroy$ = new Subject<void>();

  constructor(
    private cdr: ChangeDetectorRef,
    private paperApi: PaperApiService,
    private notify: NotificationService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.loadAccounts();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  // ── Computed ──
  get selectedAccount(): PaperAccount | undefined {
    return this.accounts.find(a => a.account_id === this.selectedId);
  }

  get perfCards(): StatCardConfig[] {
    if (!this.metrics) return [];
    return [
      { label: 'Net P&L', value: `₹${(this.metrics.net_pnl ?? 0).toLocaleString('en-IN')}`, icon: 'graph-up-arrow', trend: (this.metrics.net_pnl ?? 0) >= 0 ? 'up' : 'down' },
      { label: 'Win Rate', value: this.metrics.win_rate != null ? `${(this.metrics.win_rate * 100).toFixed(1)}%` : 'N/A', icon: 'bullseye' },
      { label: 'Total Trades', value: this.metrics.total_trades ?? 0, icon: 'arrow-left-right' },
      { label: 'Sharpe', value: this.metrics.sharpe != null ? this.metrics.sharpe.toFixed(2) : 'N/A', icon: 'bar-chart-line' },
      { label: 'Max Drawdown', value: this.metrics.max_drawdown != null ? `${(this.metrics.max_drawdown * 100).toFixed(1)}%` : 'N/A', icon: 'graph-down-arrow', trend: 'down' },
      { label: 'Sortino', value: this.metrics.sortino != null ? this.metrics.sortino.toFixed(2) : 'N/A', icon: 'bar-chart-steps' },
    ];
  }

  // ── Actions ──
  createAccount(): void {
    this.creating = true;
    this.cdr.markForCheck();
    this.paperApi.createAccount().pipe(
      catchError(() => { this.notify.error('Failed to create account.'); return of(null); }),
      takeUntil(this.destroy$),
    ).subscribe(acc => {
      this.creating = false;
      if (acc) {
        this.accounts = [...this.accounts, acc];
        this.notify.success('Paper account created.');
        this.selectAccount(acc.account_id);
      }
      this.cdr.markForCheck();
    });
  }

  selectAccount(id: string): void {
    this.selectedId = id;
    this.metricsLoading = true;
    this.metrics = null;
    this.equityCurve = [];
    this.cdr.markForCheck();

    forkJoin({
      metrics: this.paperApi.getMetrics(id).pipe(catchError(() => of(null))),
      equity: this.paperApi.getEquity(id).pipe(catchError(() => of([]))),
    }).pipe(takeUntil(this.destroy$)).subscribe(({ metrics, equity }) => {
      this.metrics = metrics;
      this.equityData = equity;
      this.equityCurve = equity.map(e => ({ time: e.date, value: e.equity }));
      this.metricsLoading = false;
      this.cdr.markForCheck();
    });
  }

  submitOrder(): void {
    if (!this.selectedId || !this.orderTicker.trim()) return;
    this.submittingOrder = true;
    this.cdr.markForCheck();

    const intent: Record<string, unknown> = {
      ticker: this.orderTicker.trim().toUpperCase(),
      side: this.orderSide,
      quantity: this.orderQty,
      order_type: this.orderType,
    };
    if (this.orderType === 'limit' && this.orderLimitPrice) {
      intent['limit_price'] = this.orderLimitPrice;
    }

    this.paperApi.submitOrderIntent(this.selectedId, intent).pipe(
      catchError(() => { this.notify.error('Order failed.'); return of(null); }),
      takeUntil(this.destroy$),
    ).subscribe(res => {
      this.submittingOrder = false;
      if (res) this.notify.success('Paper order submitted.');
      this.cdr.markForCheck();
    });
  }

  goToDetail(id: string): void {
    this.router.navigate(['/account', id]);
  }

  // ── Private ──
  private loadAccounts(): void {
    this.paperApi.listAccounts().pipe(
      catchError(() => of([])),
      takeUntil(this.destroy$),
    ).subscribe(data => {
      this.accounts = data;
      this.loading = false;
      this.cdr.markForCheck();
    });
  }
}