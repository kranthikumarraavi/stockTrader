import { Component, OnInit, OnDestroy, HostListener, Renderer2 } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router } from '@angular/router';
import { Subject, takeUntil, timer, switchMap, catchError, of } from 'rxjs';
import { SidebarComponent } from './sidebar/sidebar.component';
import { TopbarComponent } from './topbar/topbar.component';
import { FooterComponent } from './footer/footer.component';
import { MarketApiService } from '../services/market-api.service';
import { LiveStreamService } from '../services/live-stream.service';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    SidebarComponent,
    TopbarComponent,
    FooterComponent,
  ],
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.scss',
})
export class ShellComponent implements OnInit, OnDestroy {
  sidebarCollapsed = false;
  mobileMenuOpen = false;
  marketPhase = 'closed';
  wsConnected = false;
  apiStatus = 'ok';
  darkMode = false;

  private destroy$ = new Subject<void>();

  constructor(
    private router: Router,
    private marketApi: MarketApiService,
    private liveStream: LiveStreamService,
    private renderer: Renderer2,
  ) {
    // Restore persisted theme preference
    const saved = localStorage.getItem('st_theme');
    this.darkMode = saved === 'dark';
    this.applyTheme();
  }

  ngOnInit(): void {
    // Track WebSocket connection state
    this.liveStream.connected$.pipe(
      takeUntil(this.destroy$),
    ).subscribe(c => this.wsConnected = c);

    // Poll market status every 60s for footer
    timer(0, 60_000).pipe(
      switchMap(() => this.marketApi.getMarketStatus().pipe(
        catchError(() => of(null)),
      )),
      takeUntil(this.destroy$),
    ).subscribe(status => {
      if (status) {
        this.marketPhase = status.phase;
        this.apiStatus = 'ok';
      } else {
        this.apiStatus = 'error';
      }
    });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  onQuickTrade(): void {
    this.router.navigate(['/trading']);
  }

  onRefresh(): void {
    window.location.reload();
  }

  toggleDarkMode(): void {
    this.darkMode = !this.darkMode;
    localStorage.setItem('st_theme', this.darkMode ? 'dark' : 'light');
    this.applyTheme();
  }

  /** Global keyboard shortcuts */
  @HostListener('document:keydown', ['$event'])
  onKeydown(e: KeyboardEvent): void {
    // Don't trigger inside input/textarea/select
    const tag = (e.target as HTMLElement).tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

    if (e.key === 'Escape') {
      this.mobileMenuOpen = false;
    }

    // Ctrl+K or Cmd+K → focus search
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      const searchInput = document.querySelector<HTMLInputElement>('.topbar-search input');
      searchInput?.focus();
    }

    // Ctrl+Shift+O → quick order / trading page
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'O') {
      e.preventDefault();
      this.router.navigate(['/trading']);
    }

    // Ctrl+Shift+D → toggle dark mode
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'D') {
      e.preventDefault();
      this.toggleDarkMode();
    }
  }

  private applyTheme(): void {
    if (this.darkMode) {
      this.renderer.setAttribute(document.documentElement, 'data-bs-theme', 'dark');
    } else {
      this.renderer.removeAttribute(document.documentElement, 'data-bs-theme');
    }
  }
}
