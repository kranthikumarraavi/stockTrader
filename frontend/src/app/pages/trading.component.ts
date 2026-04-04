import {
  Component, ChangeDetectionStrategy, ChangeDetectorRef,
  OnInit, OnDestroy, ViewChild,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { Subject, Subscription, takeUntil, timer, catchError, of } from 'rxjs';

import { TradeApiService } from '../services/trade-api.service';
import { MarketApiService } from '../services/market-api.service';
import { PriceStreamService } from '../services/price-stream.service';
import { NotificationService } from '../services/notification.service';
import { MarketStatus, PriceTick } from '../core/models/market.model';
import { TradeIntent, Execution } from '../core/models/order.model';
import { Position } from '../core/models/position.model';

import {
  TradingChartComponent, PriceDisplayComponent, StateBadgeComponent,
  LoadingSkeletonComponent, EmptyStateComponent, OrderFormComponent,
  SymbolSearchComponent, ConfirmDialogComponent,
  ChartMode, PricePoint, VolumeBar, BadgeVariant,
  OrderFormPayload, OrderFormConfig, SymbolResult, ConfirmDialogConfig,
} from '../shared';

@Component({
  selector: 'app-trading',
  standalone: true,
  imports: [
    CommonModule, RouterModule,
    TradingChartComponent, PriceDisplayComponent, StateBadgeComponent,
    LoadingSkeletonComponent, EmptyStateComponent, OrderFormComponent,
    SymbolSearchComponent, ConfirmDialogComponent,
  ],
  templateUrl: './trading.component.html',
  styleUrl: './trading.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TradingComponent implements OnInit, OnDestroy {
  @ViewChild('tradingChart') tradingChartRef!: TradingChartComponent;

  // Instrument
  symbol = 'RELIANCE';
  lastPrice = 0;
  priceChange = 0;
  priceChangePct = 0;
  prevClose = 0;

  // Chart
  chartMode: ChartMode = 'line';
  lineData: PricePoint[] = [];
  volumeData: VolumeBar[] = [];
  streaming = false;
  tickCount = 0;

  // Market
  market: MarketStatus | null = null;
  loading = true;
  loadError = false;

  // Order
  orderConfig: OrderFormConfig = {};
  orderSubmitting = false;

  // Confirm dialog
  showConfirm = false;
  confirmConfig: ConfirmDialogConfig = { title: '', message: '' };
  pendingPayload: OrderFormPayload | null = null;

  // Positions & Trades
  positions: Position[] = [];
  intents: TradeIntent[] = [];
  executions: Execution[] = [];

  private destroy$ = new Subject<void>();
  private streamSub: Subscription | null = null;

  constructor(
    private cdr: ChangeDetectorRef,
    private tradeApi: TradeApiService,
    private marketApi: MarketApiService,
    private priceStream: PriceStreamService,
    private notify: NotificationService,
  ) {}

  ngOnInit(): void {
    this.loadMarket();
    timer(30_000, 30_000).pipe(takeUntil(this.destroy$)).subscribe(() => this.loadMarket());
    this.loadSymbol(this.symbol);
  }

  ngOnDestroy(): void {
    this.stopStream();
    this.destroy$.next();
    this.destroy$.complete();
  }

  // ── Computed ──
  get isMarketOpen(): boolean {
    return this.market?.phase === 'open' || this.market?.phase === 'pre_open';
  }

  get sessionBadge(): BadgeVariant {
    if (!this.market) return 'neutral';
    switch (this.market.phase) {
      case 'open': return 'success';
      case 'pre_open': return 'warning';
      default: return 'danger';
    }
  }

  get sessionLabel(): string {
    if (!this.market) return 'Loading…';
    switch (this.market.phase) {
      case 'open': return 'OPEN';
      case 'pre_open': return 'PRE-OPEN';
      default: return 'CLOSED';
    }
  }

  // ── Actions ──
  onSymbolSelect(result: SymbolResult): void {
    this.loadSymbol(result.symbol);
  }

  loadSymbol(sym: string): void {
    this.symbol = sym.toUpperCase().trim();
    if (!this.symbol) return;
    this.stopStream();
    this.lineData = [];
    this.volumeData = [];
    this.tickCount = 0;
    this.loading = true;
    this.orderConfig = { symbol: this.symbol };
    this.cdr.markForCheck();
    this.startStream();
  }

  startStream(): void {
    this.stopStream();
    this.streaming = true;
    this.loading = false;
    this.cdr.markForCheck();

    this.streamSub = this.priceStream.connect(this.symbol).subscribe({
      next: tick => {
        this.tickCount++;
        this.processTick(tick);
        this.cdr.markForCheck();
      },
      error: () => {
        this.streaming = false;
        this.cdr.markForCheck();
      },
    });
  }

  stopStream(): void {
    this.streamSub?.unsubscribe();
    this.streamSub = null;
    this.streaming = false;
  }

  onOrderSubmit(payload: OrderFormPayload): void {
    this.pendingPayload = payload;
    this.confirmConfig = {
      title: 'Confirm Order',
      message: `${payload.side.toUpperCase()} ${payload.quantity} × ${payload.symbol} (${payload.orderType})`,
      severity: payload.side === 'sell' ? 'danger' : 'info',
      confirmLabel: payload.side === 'buy' ? 'Place Buy' : 'Place Sell',
    };
    this.showConfirm = true;
    this.cdr.markForCheck();
  }

  onConfirmOrder(): void {
    this.showConfirm = false;
    if (!this.pendingPayload) return;
    const p = this.pendingPayload;
    this.orderSubmitting = true;
    this.cdr.markForCheck();

    this.tradeApi.createIntent({
      ticker: p.symbol,
      side: p.side,
      quantity: p.quantity,
      order_type: p.orderType === 'market' ? 'market' : 'limit',
      limit_price: p.price ?? undefined,
    }).pipe(
      catchError(() => { this.notify.error('Order failed'); return of(null); }),
      takeUntil(this.destroy$),
    ).subscribe(intent => {
      this.orderSubmitting = false;
      if (intent) {
        this.intents = [intent, ...this.intents];
        this.notify.success(`Intent created: ${intent.ticker}`);
      }
      this.pendingPayload = null;
      this.cdr.markForCheck();
    });
  }

  onCancelConfirm(): void {
    this.showConfirm = false;
    this.pendingPayload = null;
    this.cdr.markForCheck();
  }

  executeIntent(intent: TradeIntent): void {
    this.tradeApi.execute(intent.intent_id).pipe(
      catchError(() => { this.notify.error('Execution failed'); return of(null); }),
      takeUntil(this.destroy$),
    ).subscribe(exec => {
      if (exec) {
        this.executions = [exec, ...this.executions];
        this.intents = this.intents.filter(i => i.intent_id !== intent.intent_id);
        this.notify.success(`Executed: ${exec.ticker} @ ₹${exec.filled_price.toFixed(2)}`);
      }
      this.cdr.markForCheck();
    });
  }

  setChartMode(mode: ChartMode): void {
    this.chartMode = mode;
    this.cdr.markForCheck();
  }

  trackByIntentId(_: number, item: TradeIntent): string { return item.intent_id; }
  trackByExecId(_: number, item: Execution): string { return item.execution_id; }

  // ── Private ──
  private processTick(tick: PriceTick): void {
    this.lastPrice = tick.price;
    this.priceChange = this.prevClose ? tick.price - this.prevClose : 0;
    this.priceChangePct = this.prevClose ? (this.priceChange / this.prevClose) * 100 : 0;

    this.lineData = [...this.lineData, { time: tick.timestamp, value: tick.price }];
    this.volumeData = [...this.volumeData, {
      time: tick.timestamp, value: tick.volume,
      color: tick.price >= (this.lineData.length > 1 ? this.lineData[this.lineData.length - 2].value : tick.price)
        ? '#2e7d3233' : '#d32f2f33',
    }];
    if (this.lineData.length > 500) {
      this.lineData = this.lineData.slice(-500);
      this.volumeData = this.volumeData.slice(-500);
    }
    this.orderConfig = { ...this.orderConfig, lastPrice: tick.price };
  }

  loadMarket(): void {
    this.loadError = false;
    this.marketApi.getMarketStatus().pipe(
      catchError(() => of(null)), takeUntil(this.destroy$),
    ).subscribe(m => {
      if (m) {
        this.market = m;
      } else {
        this.loadError = true;
      }
      this.loading = false;
      this.cdr.markForCheck();
    });
  }
}

