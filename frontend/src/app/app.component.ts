// Root Angular component — minimal shell; layout lives in ShellComponent

import { Component, DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { NotificationService } from './services/notification.service';
import { Toast } from './core/models';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent {
  toasts: Toast[] = [];
  private destroyRef = inject(DestroyRef);

  constructor(public notify: NotificationService) {
    this.notify.toasts$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(t => this.toasts = t);
  }
}


