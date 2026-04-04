import {
  Component, ChangeDetectionStrategy, ChangeDetectorRef,
  OnDestroy,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { Router, ActivatedRoute } from '@angular/router';
import { Subject, takeUntil } from 'rxjs';

import { AuthService } from '../services/auth.service';
import { NotificationService } from '../services/notification.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LoginComponent implements OnDestroy {
  form: FormGroup;
  loading = false;
  error: string | null = null;
  showPassword = false;

  private returnUrl = '/';
  private destroy$ = new Subject<void>();

  constructor(
    private cdr: ChangeDetectorRef,
    private fb: FormBuilder,
    private auth: AuthService,
    private router: Router,
    private route: ActivatedRoute,
    private notify: NotificationService,
  ) {
    const raw = this.route.snapshot.queryParamMap.get('returnUrl') || '/';
    // Prevent open-redirect: only allow relative paths, no protocol schemes
    this.returnUrl = raw.startsWith('/') && !raw.startsWith('//') ? raw : '/';

    if (this.auth.isAuthenticated) {
      this.router.navigateByUrl(this.returnUrl);
    }

    this.form = this.fb.group({
      token: ['', [Validators.required, Validators.minLength(8)]],
    });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  get tokenCtrl() { return this.form.get('token')!; }

  onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.loading = true;
    this.error = null;
    this.cdr.markForCheck();

    const token = this.tokenCtrl.value.trim();

    // Direct token auth — no backend login endpoint needed
    try {
      this.auth.setToken(token);
      this.notify.success('Authenticated successfully.');
      this.router.navigateByUrl(this.returnUrl);
    } catch {
      this.error = 'Failed to save authentication token.';
      this.loading = false;
      this.cdr.markForCheck();
    }
  }
}
