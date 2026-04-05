// Execution quality page component
import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subject, takeUntil, timer } from 'rxjs';
import { ExecutionApiService } from '../services/execution-api.service';
import { NotificationService } from '../services/notification.service';

@Component({
  selector: 'app-execution-quality',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './execution-quality.component.html',
  styleUrl: './execution-quality.component.scss',
})
export class ExecutionQualityComponent implements OnInit, OnDestroy {
  stats: any | null = null;
  statsEntries: { key: string; value: any }[] = [];
  reports: any[] | null = null;
  loadError = false;

  private destroy$ = new Subject<void>();

  constructor(
    private execApi: ExecutionApiService,
    private notify: NotificationService,
  ) {}

  ngOnInit(): void {
    this.loadAll();
    timer(15_000, 15_000).pipe(takeUntil(this.destroy$)).subscribe(() => this.loadAll());
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  loadAll(): void {
    this.loadError = false;
    this.execApi.getStats().pipe(takeUntil(this.destroy$)).subscribe({
      next: s => {
        this.stats = s;
        this.statsEntries = Object.entries(s || {})
          .map(([key, value]) => ({ key, value }))
          .sort((a, b) => a.key.localeCompare(b.key));
      },
      error: () => {
        this.loadError = true;
        this.notify.error('Failed to load execution stats.');
      }
    });
    this.execApi.getRecentReports().pipe(takeUntil(this.destroy$)).subscribe({
      next: d => this.reports = d,
      error: () => {
        this.loadError = true;
        this.notify.error('Failed to load execution reports.');
      }
    });
  }

  trackByStat(_: number, entry: { key: string; value: any }): string {
    return entry.key;
  }

  trackByReport(index: number, report: any): string {
    const ts = String(report?.timestamp ?? report?.created_at ?? report?.updated_at ?? index);
    return `${report?.ticker ?? 'UNKNOWN'}-${ts}`;
  }

  formatLabel(key: string): string {
    return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  formatValue(val: any): string {
    if (val === null || val === undefined) return '—';
    if (typeof val === 'number') return val % 1 === 0 ? val.toString() : val.toFixed(3);
    return String(val);
  }

  sideClass(side: string | null | undefined): string {
    const normalized = (side || '').toLowerCase();
    if (normalized === 'buy') return 'eq__badge--buy';
    if (normalized === 'sell') return 'eq__badge--sell';
    return 'eq__badge--neutral';
  }

  statusClass(status: string | null | undefined): string {
    const normalized = (status || '').toLowerCase();
    if (normalized === 'filled' || normalized === 'success') return 'eq__badge--success';
    if (normalized === 'rejected' || normalized === 'failed') return 'eq__badge--danger';
    return 'eq__badge--info';
  }

  qualityClass(score: number | null | undefined): string {
    const value = Number(score ?? 0);
    if (value >= 0.8) return 'eq__badge--success';
    if (value >= 0.5) return 'eq__badge--warning';
    return 'eq__badge--danger';
  }

  slippageClass(slippage: number | null | undefined): string {
    const value = Number(slippage ?? 0);
    return value > 0.5 ? 'text-sell' : 'text-buy';
  }
}
