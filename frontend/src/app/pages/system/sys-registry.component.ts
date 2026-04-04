import {
  Component, ChangeDetectionStrategy, ChangeDetectorRef,
  OnInit, OnDestroy,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subject, takeUntil, catchError, of } from 'rxjs';

import { AdminApiService } from '../../services/admin-api.service';
import { NotificationService } from '../../services/notification.service';
import { ModelVersion } from '../../core/models';

import {
  StateBadgeComponent, LoadingSkeletonComponent, EmptyStateComponent,
  BadgeVariant,
} from '../../shared';

@Component({
  selector: 'app-sys-registry',
  standalone: true,
  imports: [CommonModule, StateBadgeComponent, LoadingSkeletonComponent, EmptyStateComponent],
  templateUrl: './sys-registry.component.html',
  styleUrl: './sys-registry.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SysRegistryComponent implements OnInit, OnDestroy {
  versions: ModelVersion[] = [];
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

  statusBadge(v: ModelVersion): BadgeVariant {
    return v.status === 'active' ? 'success' : 'neutral';
  }

  load(): void {
    this.loading = true;
    this.cdr.markForCheck();
    this.adminApi.getRegistryVersions().pipe(
      catchError(() => of([])),
      takeUntil(this.destroy$),
    ).subscribe(v => {
      this.versions = Array.isArray(v) ? v : [];
      this.loading = false;
      this.cdr.markForCheck();
    });
  }
}
