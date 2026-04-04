import {
  Component, ChangeDetectionStrategy, ChangeDetectorRef,
  OnInit, OnDestroy,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, ActivatedRoute } from '@angular/router';
import { Subject, takeUntil } from 'rxjs';

import { AuthService } from '../services/auth.service';
import { NotificationService } from '../services/notification.service';

@Component({
  selector: 'app-callback',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './callback.component.html',
  styleUrl: './callback.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CallbackComponent implements OnInit, OnDestroy {
  status: 'processing' | 'success' | 'error' = 'processing';
  message = 'Processing authentication…';

  private destroy$ = new Subject<void>();

  constructor(
    private cdr: ChangeDetectorRef,
    private auth: AuthService,
    private router: Router,
    private route: ActivatedRoute,
    private notify: NotificationService,
  ) {}

  ngOnInit(): void {
    const params = this.route.snapshot.queryParamMap;
    const token = params.get('token') || params.get('access_token');
    const error = params.get('error');

    if (error) {
      this.status = 'error';
      this.message = decodeURIComponent(error);
      this.notify.error('Authentication failed.');
      this.cdr.markForCheck();
      return;
    }

    if (token) {
      // Basic sanity: reject obviously invalid tokens (must be non-empty, no spaces, reasonable length)
      if (token.length < 8 || token.length > 4096 || /\s/.test(token)) {
        this.status = 'error';
        this.message = 'Invalid token format. Please try logging in again.';
        this.notify.error('Invalid authentication token.');
        this.cdr.markForCheck();
        return;
      }

      this.auth.setToken(token);
      this.status = 'success';
      this.message = 'Authentication successful. Redirecting…';
      this.notify.success('Authenticated.');
      this.cdr.markForCheck();

      setTimeout(() => this.router.navigateByUrl('/'), 1500);
    } else {
      this.status = 'error';
      this.message = 'No token received. Please try logging in again.';
      this.cdr.markForCheck();
    }
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  goToLogin(): void {
    this.router.navigateByUrl('/auth/login');
  }
}
