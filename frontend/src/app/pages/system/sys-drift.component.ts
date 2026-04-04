import {
  Component, ChangeDetectionStrategy, ChangeDetectorRef,
  OnInit, OnDestroy,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subject, takeUntil, catchError, of } from 'rxjs';

import { AdminApiService } from '../../services/admin-api.service';
import { AuthService } from '../../services/auth.service';
import { NotificationService } from '../../services/notification.service';
import { DriftResult } from '../../core/models';

import {
  StatCardComponent, StateBadgeComponent, LoadingSkeletonComponent,
  EmptyStateComponent, BadgeVariant,
} from '../../shared';

@Component({
  selector: 'app-sys-drift',
  standalone: true,
  imports: [CommonModule, StatCardComponent, StateBadgeComponent, LoadingSkeletonComponent, EmptyStateComponent],
  templateUrl: './sys-drift.component.html',
  styleUrl: './sys-drift.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SysDriftComponent implements OnInit, OnDestroy {
  drift: DriftResult | null = null;
  loading = true;
  checking = false;

  private destroy$ = new Subject<void>();

  constructor(
    private cdr: ChangeDetectorRef,
    private adminApi: AdminApiService,
    public auth: AuthService,
    private notify: NotificationService,
  ) {}

  ngOnInit(): void {
    this.load();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  get overallBadge(): BadgeVariant {
    return this.drift?.status === 'healthy' ? 'success' : 'error';
  }

  get featureBadge(): BadgeVariant {
    return this.drift?.feature_drift_detected ? 'danger' : 'success';
  }

  load(): void {
    this.loading = true;
    this.cdr.markForCheck();
    this.adminApi.checkDrift().pipe(
      catchError(() => of(null)),
      takeUntil(this.destroy$),
    ).subscribe(d => {
      this.drift = d;
      this.loading = false;
      this.cdr.markForCheck();
    });
  }

  runCheck(): void {
    this.checking = true;
    this.cdr.markForCheck();
    this.adminApi.checkDrift().pipe(
      catchError(() => { this.notify.error('Drift check failed.'); return of(null); }),
      takeUntil(this.destroy$),
    ).subscribe(d => {
      this.drift = d;
      this.checking = false;
      if (d) this.notify.success('Drift check completed.');
      this.cdr.markForCheck();
    });
  }
}
