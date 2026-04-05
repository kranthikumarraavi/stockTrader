// Regime & strategy intelligence page component
import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, takeUntil, timer } from 'rxjs';
import { StrategyApiService, RegimeResult } from '../services/strategy-api.service';
import { NotificationService } from '../services/notification.service';

@Component({
  selector: 'app-regime-panel',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './regime-panel.component.html',
  styleUrl: './regime-panel.component.scss',
})
export class RegimePanelComponent implements OnInit, OnDestroy {
  symbolsStr = 'RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK';
  heatmap: Record<string, any> | null = null;
  heatmapEntries: { symbol: string; regime: string; confidence: number; volatility: number }[] = [];
  heatmapLoading = false;

  detailSymbol = '';
  regimeDetail: RegimeResult | null = null;
  detailLoading = false;
  indicatorEntries: { key: string; value: number }[] = [];

  decisions: any[] | null = null;
  stats: any | null = null;
  statsEntries: { key: string; value: any }[] = [];

  private destroy$ = new Subject<void>();

  constructor(
    private strategyApi: StrategyApiService,
    private notify: NotificationService,
  ) {}

  ngOnInit(): void {
    this.loadHeatmap();
    this.loadDecisions();
    this.loadStats();
    timer(30_000, 30_000).pipe(takeUntil(this.destroy$)).subscribe(() => {
      this.loadDecisions();
      this.loadStats();
    });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  loadHeatmap(): void {
    this.heatmapLoading = true;
    const syms = this.symbolsStr.split(',').map(s => s.trim()).filter(s => s);
    this.strategyApi.regimeHeatmap(syms).pipe(takeUntil(this.destroy$)).subscribe({
      next: d => {
        this.heatmap = d;
        this.heatmapEntries = Object.entries(d)
          .map(([symbol, v]: [string, any]) => ({
            symbol,
            regime: v.regime || 'unknown',
            confidence: (v.confidence || 0) * 100,
            volatility: v.volatility || 0,
          }))
          .sort((a, b) => a.symbol.localeCompare(b.symbol));
        this.heatmapLoading = false;
      },
      error: () => {
        this.heatmapLoading = false;
        this.notify.error('Failed to load regime heatmap.');
      }
    });
  }

  detectRegime(): void {
    if (!this.detailSymbol) return;
    this.detailLoading = true;
    this.strategyApi.detectRegime(this.detailSymbol.trim()).pipe(takeUntil(this.destroy$)).subscribe({
      next: r => {
        this.regimeDetail = r;
        this.indicatorEntries = Object.entries(r.indicators || {}).map(([key, value]) => ({ key, value }));
        this.detailLoading = false;
      },
      error: () => {
        this.detailLoading = false;
        this.notify.error('Failed to detect regime.');
      }
    });
  }

  loadDecisions(): void {
    this.strategyApi.getRecentDecisions().pipe(takeUntil(this.destroy$)).subscribe({
      next: d => this.decisions = d,
      error: () => this.notify.error('Failed to load strategy decisions.')
    });
  }

  loadStats(): void {
    this.strategyApi.getStats().pipe(takeUntil(this.destroy$)).subscribe({
      next: s => {
        this.stats = s;
        this.statsEntries = Object.entries(s || {}).map(([key, value]) => ({ key, value }));
      },
      error: () => this.notify.error('Failed to load strategy stats.')
    });
  }

  trackByHeatmap(_: number, item: { symbol: string }): string {
    return item.symbol;
  }

  trackByStat(_: number, item: { key: string; value: any }): string {
    return item.key;
  }

  trackByDecision(index: number, item: any): string {
    const reason = String(item?.reason ?? index);
    return `${item?.ticker ?? 'UNKNOWN'}-${item?.strategy ?? 'strategy'}-${reason}`;
  }

  formatLabel(key: string): string {
    return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  normalizeRegime(regime: string | null | undefined): string {
    const normalized = (regime || 'unknown').toLowerCase().replace(/[^a-z0-9]+/g, '-');
    return `rp__regime--${normalized}`;
  }
}
