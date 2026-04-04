import {
  Component, ChangeDetectionStrategy, ChangeDetectorRef,
  OnInit, OnDestroy,
} from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, takeUntil, timer, catchError, of } from 'rxjs';

import { MarketApiService } from '../services/market-api.service';
import { NotificationService } from '../services/notification.service';
import { MarketStatus, AccountProfile } from '../core/models/market.model';
import { BotStatus, BotConfig } from '../core/models/bot.model';

import {
  StatCardComponent, StateBadgeComponent, LoadingSkeletonComponent,
  EmptyStateComponent, ConfirmDialogComponent,
  StatCardConfig, BadgeVariant, ConfirmDialogConfig,
} from '../shared';

@Component({
  selector: 'app-bot-panel',
  standalone: true,
  imports: [
    CommonModule, FormsModule, DatePipe,
    StatCardComponent, StateBadgeComponent, LoadingSkeletonComponent,
    EmptyStateComponent, ConfirmDialogComponent,
  ],
  templateUrl: './bot-panel.component.html',
  styleUrl: './bot-panel.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BotPanelComponent implements OnInit, OnDestroy {
  // Market
  market: MarketStatus | null = null;
  account: AccountProfile | null = null;
  accountLoading = false;

  // Bot
  botStatus: BotStatus | null = null;
  botRunning = false;
  starting = false;
  stopping = false;

  // Config
  watchlistStr = 'RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK';
  botConfig: BotConfig = {
    min_confidence: 0.7,
    max_positions: 5,
    position_size: 10000,
    stop_loss_pct: 0.02,
    take_profit_pct: 0.05,
    cycle_interval: 60,
  };

  // Confirm
  showConfirm = false;
  confirmConfig: ConfirmDialogConfig = { title: '', message: '' };
  pendingAction: 'start' | 'stop' | null = null;

  // Computed from bot
  positionEntries: { key: string; value: any }[] = [];
  credentialsList: { key: string; set: boolean }[] = [];
  countdownStr = '';
  private secondsLeft = 0;

  loading = true;

  private destroy$ = new Subject<void>();

  constructor(
    private cdr: ChangeDetectorRef,
    private marketApi: MarketApiService,
    private notify: NotificationService,
  ) {}

  ngOnInit(): void {
    this.loadMarket();
    this.loadBotStatus();
    timer(30_000, 30_000).pipe(takeUntil(this.destroy$)).subscribe(() => this.loadMarket());
    timer(5_000, 5_000).pipe(takeUntil(this.destroy$)).subscribe(() => this.loadBotStatus());
    timer(1_000, 1_000).pipe(takeUntil(this.destroy$)).subscribe(() => this.tickCountdown());
  }

  ngOnDestroy(): void {
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

  get botStateBadge(): BadgeVariant {
    if (this.botRunning && !this.botStatus?.paused) return 'running';
    if (this.botStatus?.paused) return 'warning';
    return 'stopped';
  }

  get botStateLabel(): string {
    if (this.botRunning && !this.botStatus?.paused) return 'RUNNING';
    if (this.botStatus?.paused) return 'PAUSED';
    return 'STOPPED';
  }

  get pnlCards(): StatCardConfig[] {
    if (!this.botStatus) return [];
    return [
      {
        label: 'Total P&L', value: `₹${(this.botStatus.total_pnl ?? 0).toLocaleString()}`,
        icon: 'graph-up-arrow', trend: (this.botStatus.total_pnl ?? 0) >= 0 ? 'up' : 'down',
      },
      { label: 'Trades Today', value: this.botStatus.trades_today?.length ?? 0, icon: 'arrow-left-right' },
      { label: 'Cycles Run', value: this.botStatus.cycle_count ?? 0, icon: 'arrow-repeat' },
      { label: 'Active Positions', value: this.botStatus.active_positions ?? 0, icon: 'stack' },
    ];
  }

  // ── Actions ──
  loadAccount(): void {
    this.accountLoading = true;
    this.cdr.markForCheck();
    this.marketApi.getAccountProfile().pipe(
      catchError(() => { this.notify.error('Failed to verify account'); return of(null); }),
      takeUntil(this.destroy$),
    ).subscribe(a => {
      this.accountLoading = false;
      if (a) {
        this.account = a;
        this.credentialsList = a.credentials_set
          ? Object.entries(a.credentials_set).map(([key, set]) => ({ key, set }))
          : [];
      }
      this.cdr.markForCheck();
    });
  }

  confirmStart(): void {
    this.pendingAction = 'start';
    this.confirmConfig = {
      title: 'Start Bot',
      message: `Start auto-trading with ${this.watchlistStr.split(',').length} symbols, ₹${this.botConfig.position_size} position size?`,
      severity: 'warning',
      confirmLabel: 'Start Bot',
    };
    this.showConfirm = true;
    this.cdr.markForCheck();
  }

  confirmStop(): void {
    this.pendingAction = 'stop';
    this.confirmConfig = {
      title: 'Stop Bot',
      message: 'Stop the auto-trading bot? All pending cycles will be cancelled.',
      severity: 'danger',
      confirmLabel: 'Stop Bot',
    };
    this.showConfirm = true;
    this.cdr.markForCheck();
  }

  onConfirm(): void {
    this.showConfirm = false;
    if (this.pendingAction === 'start') this.startBot();
    else if (this.pendingAction === 'stop') this.stopBot();
    this.pendingAction = null;
  }

  onCancelConfirm(): void {
    this.showConfirm = false;
    this.pendingAction = null;
    this.cdr.markForCheck();
  }

  grantConsent(): void {
    this.marketApi.botConsent(true).pipe(
      catchError(() => { this.notify.error('Failed to grant consent'); return of(null); }),
      takeUntil(this.destroy$),
    ).subscribe(res => {
      if (res) this.notify.success((res as Record<string, string>)['message'] || 'Trading resumed');
      this.loadBotStatus();
    });
  }

  declineConsent(): void {
    this.marketApi.botConsent(false).pipe(
      catchError(() => { this.notify.error('Failed to decline'); return of(null); }),
      takeUntil(this.destroy$),
    ).subscribe(res => {
      if (res) {
        this.botRunning = false;
        this.notify.success((res as Record<string, string>)['message'] || 'Bot stopped');
      }
      this.loadBotStatus();
    });
  }

  // ── Private ──
  private startBot(): void {
    this.starting = true;
    this.cdr.markForCheck();
    const config = {
      ...this.botConfig,
      watchlist: this.watchlistStr.split(',').map(t => t.trim()).filter(t => t),
    };
    this.marketApi.startBot(config).pipe(
      catchError(() => { this.notify.error('Failed to start bot'); return of(null); }),
      takeUntil(this.destroy$),
    ).subscribe(res => {
      this.starting = false;
      if (res) {
        this.botRunning = true;
        this.notify.success((res as Record<string, string>)['message'] || 'Bot started');
      }
      this.loadBotStatus();
      this.cdr.markForCheck();
    });
  }

  private stopBot(): void {
    this.stopping = true;
    this.cdr.markForCheck();
    this.marketApi.stopBot().pipe(
      catchError(() => { this.notify.error('Failed to stop bot'); return of(null); }),
      takeUntil(this.destroy$),
    ).subscribe(res => {
      this.stopping = false;
      if (res) {
        this.botRunning = false;
        this.notify.success((res as Record<string, string>)['message'] || 'Bot stopped');
      }
      this.loadBotStatus();
      this.cdr.markForCheck();
    });
  }

  private loadMarket(): void {
    this.marketApi.getMarketStatus().pipe(
      catchError(() => of(null)),
      takeUntil(this.destroy$),
    ).subscribe(m => {
      if (m) {
        this.market = m;
        this.secondsLeft = m.seconds_to_next;
      }
      this.loading = false;
      this.cdr.markForCheck();
    });
  }

  private loadBotStatus(): void {
    this.marketApi.getBotStatus().pipe(
      catchError(() => of(null)),
      takeUntil(this.destroy$),
    ).subscribe(s => {
      if (s) {
        this.botStatus = s;
        this.botRunning = s.running;
        this.positionEntries = Object.entries(s.positions || {}).map(([key, value]) => ({ key, value }));
      }
      this.cdr.markForCheck();
    });
  }

  private tickCountdown(): void {
    if (this.secondsLeft > 0) {
      this.secondsLeft--;
      const h = Math.floor(this.secondsLeft / 3600);
      const m = Math.floor((this.secondsLeft % 3600) / 60);
      const s = this.secondsLeft % 60;
      this.countdownStr = h > 0
        ? `${h}h ${m}m ${s}s`
        : m > 0 ? `${m}m ${s}s` : `${s}s`;
      this.cdr.markForCheck();
    }
  }
}

