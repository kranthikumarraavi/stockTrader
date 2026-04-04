import {
  Component, ChangeDetectionStrategy, ChangeDetectorRef,
  OnInit, OnDestroy,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, takeUntil, catchError, of } from 'rxjs';

import { OptionsApiService } from '../services/options-api.service';
import { StrategyRecommendation, OptionLeg } from '../core/models/options.model';

import {
  StatCardComponent, StateBadgeComponent, LoadingSkeletonComponent,
  EmptyStateComponent, BadgeVariant, StatCardConfig,
} from '../shared';

@Component({
  selector: 'app-options-builder',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    StatCardComponent, StateBadgeComponent, LoadingSkeletonComponent, EmptyStateComponent,
  ],
  templateUrl: './options-builder.component.html',
  styleUrl: './options-builder.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class OptionsBuilderComponent implements OnInit, OnDestroy {
  // Inputs
  underlying = 'NIFTY';
  spot = 24500;
  iv = 0.15;
  expiry = '';
  lotSize = 50;
  direction = 'bullish';
  confidence = 0.65;

  // State
  result: StrategyRecommendation | null = null;
  payoffData: { spot: number; payoff: number; pnl: number }[] = [];
  loading = false;
  maxPayoff = 1;
  labelInterval = 10;

  readonly Math = Math;

  private destroy$ = new Subject<void>();

  constructor(
    private cdr: ChangeDetectorRef,
    private optionsApi: OptionsApiService,
  ) {
    // Default expiry: next Thursday
    const now = new Date();
    const day = now.getDay();
    const daysUntilThursday = (4 - day + 7) % 7 || 7;
    const next = new Date(now);
    next.setDate(now.getDate() + daysUntilThursday);
    this.expiry = next.toISOString().split('T')[0];
  }

  ngOnInit(): void {}

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  // ── Computed ──
  get resultCards(): StatCardConfig[] {
    if (!this.result) return [];
    return [
      { label: 'Max Profit', value: `₹${this.result.max_profit.toLocaleString()}`, icon: 'arrow-up-circle', trend: 'up' },
      { label: 'Max Loss', value: `₹${this.result.max_loss.toLocaleString()}`, icon: 'arrow-down-circle', trend: 'down' },
      { label: 'Margin Req.', value: `₹${this.result.margin_required.toLocaleString()}`, icon: 'cash-stack' },
    ];
  }

  legTypeBadge(type: string): BadgeVariant {
    return type === 'CE' ? 'info' : 'warning';
  }

  legSideBadge(side: string): BadgeVariant {
    return side === 'buy' ? 'buy' : 'sell';
  }

  barHeight(payoff: number): number {
    return Math.min(70, (Math.abs(payoff) / this.maxPayoff) * 70);
  }

  barOffset(payoff: number): number {
    return payoff >= 0 ? 70 - this.barHeight(payoff) : 70;
  }

  showLabel(i: number): boolean {
    return i % this.labelInterval === 0;
  }

  // ── Actions ──
  recommend(): void {
    this.loading = true;
    this.cdr.markForCheck();

    this.optionsApi.recommendStrategy({
      ...this.payload, direction: this.direction, confidence: this.confidence,
    }).pipe(
      catchError(() => of(null)),
      takeUntil(this.destroy$),
    ).subscribe(r => {
      this.loading = false;
      if (r) this.handleResult(r);
      this.cdr.markForCheck();
    });
  }

  buildQuick(strategy: string): void {
    const map: Record<string, (p: any) => ReturnType<OptionsApiService['buildCoveredCall']>> = {
      'covered-call': p => this.optionsApi.buildCoveredCall(p),
      'bull-call-spread': p => this.optionsApi.buildBullCallSpread(p),
      'iron-condor': p => this.optionsApi.buildIronCondor(p),
      'straddle': p => this.optionsApi.buildStraddle(p),
    };
    const fn = map[strategy];
    if (!fn) return;

    this.loading = true;
    this.cdr.markForCheck();

    fn(this.payload).pipe(
      catchError(() => of(null)),
      takeUntil(this.destroy$),
    ).subscribe(r => {
      this.loading = false;
      if (r) this.handleResult(r);
      this.cdr.markForCheck();
    });
  }

  trackByLeg(_: number, leg: OptionLeg): string {
    return `${leg.instrument}_${leg.strike}_${leg.option_type}_${leg.side}`;
  }

  // ── Private ──
  private get payload() {
    return {
      underlying: this.underlying, spot: this.spot,
      expiry: this.expiry, iv: this.iv, lot_size: this.lotSize,
    };
  }

  private handleResult(r: StrategyRecommendation): void {
    this.result = r;
    this.payoffData = [];
    if (r.legs?.length) {
      this.optionsApi.computePayoff(r.legs).pipe(
        catchError(() => of([])),
        takeUntil(this.destroy$),
      ).subscribe(d => {
        this.payoffData = d;
        const vals = d.map((p: any) => Math.abs(p.payoff));
        this.maxPayoff = Math.max(...vals, 1);
        this.labelInterval = Math.max(1, Math.floor(d.length / 8));
        this.cdr.markForCheck();
      });
    }
  }
}
