import {
  Component, ChangeDetectionStrategy, ChangeDetectorRef,
  OnInit, OnDestroy,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subject, takeUntil, catchError, of } from 'rxjs';

import { AdminApiService } from '../../services/admin-api.service';
import { NotificationService } from '../../services/notification.service';
import { CanaryStatus } from '../../core/models';

import {
  StatCardComponent, StateBadgeComponent, LoadingSkeletonComponent,
  EmptyStateComponent,
} from '../../shared';

@Component({
  selector: 'app-sys-canary',
  standalone: true,
  imports: [CommonModule, StatCardComponent, StateBadgeComponent, LoadingSkeletonComponent, EmptyStateComponent],
  templateUrl: './sys-canary.component.html',
  styleUrl: './sys-canary.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SysCanaryComponent implements OnInit, OnDestroy {
  canary: CanaryStatus | null = null;
  loading = true;

  private destroy$ = new Subject<void>();

  constructor(
    private cdr: ChangeDetectorRef,
    private adminApi: AdminApiService,
    private notify: NotificationService,
  ) {}

  ngOnInit(): void {
    this.load();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  load(): void {
    this.loading = true;
    this.cdr.markForCheck();
    this.adminApi.getCanaryStatus().pipe(
      catchError(() => of(null)),
      takeUntil(this.destroy$),
    ).subscribe(c => {
      this.canary = c;
      this.loading = false;
      this.cdr.markForCheck();
    });
  }
}
