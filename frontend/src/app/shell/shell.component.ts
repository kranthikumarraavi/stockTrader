import { Component, OnInit, OnDestroy, HostListener, Renderer2 } from '@angular/core';
import { CommonModule } from '@angular/common';
import { NavigationCancel, NavigationEnd, NavigationError, NavigationStart, Router, RouterModule } from '@angular/router';
import { Subject, takeUntil, timer, switchMap, catchError, of } from 'rxjs';
import { SidebarComponent } from './sidebar/sidebar.component';
import { TopbarComponent } from './topbar/topbar.component';
import { FooterComponent } from './footer/footer.component';
import { MarketApiService } from '../services/market-api.service';
import { LiveStreamService } from '../services/live-stream.service';
import { NotificationService } from '../services/notification.service';
import { ClickOutsideDirective } from '../shared/directives/click-outside.directive';
import { AppNotification } from '../core/models';
import { NAV_GROUPS } from './nav.config';

type CommandKind = 'route' | 'symbol' | 'theme' | 'refresh';

interface CommandOption {
  id: string;
  title: string;
  subtitle: string;
  icon: string;
  keywords: string;
  kind: CommandKind;
  route?: string;
  symbol?: string;
  hotkey?: string;
}

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    SidebarComponent,
    TopbarComponent,
    FooterComponent,
    ClickOutsideDirective,
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
  routeLoading = false;

  notificationsOpen = false;
  notifications: AppNotification[] = [];
  unreadNotifications = 0;

  commandPaletteOpen = false;
  commandQuery = '';
  commandCursor = 0;
  filteredCommands: CommandOption[] = [];
  private commandActions: CommandOption[] = [];
  private recentSymbols: string[] = [];

  private destroy$ = new Subject<void>();
  private routeLoaderTimer: ReturnType<typeof setTimeout> | null = null;
  private lastWsConnected: boolean | null = null;
  private lastMarketPhase = '';
  private lastApiStatus = 'ok';

  constructor(
    private router: Router,
    private marketApi: MarketApiService,
    private liveStream: LiveStreamService,
    private notify: NotificationService,
    private renderer: Renderer2,
  ) {
    // Restore persisted theme preference
    const saved = localStorage.getItem('st_theme');
    this.darkMode = saved === 'dark';
    this.recentSymbols = this.readRecentSymbols();
    this.initCommandActions();
    this.applyTheme();
  }

  ngOnInit(): void {
    // Track WebSocket connection state
    this.liveStream.connected$.pipe(
      takeUntil(this.destroy$),
    ).subscribe(c => {
      this.wsConnected = c;
      if (this.lastWsConnected !== null && this.lastWsConnected !== c) {
        if (c) {
          this.notify.success('Live stream connection restored', 'Connectivity');
        } else {
          this.notify.warning('Live stream disconnected. Replay/snapshot mode only.', 'Connectivity');
        }
      }
      this.lastWsConnected = c;
    });

    this.notify.notifications$.pipe(takeUntil(this.destroy$)).subscribe(items => this.notifications = items);
    this.notify.unreadCount$.pipe(takeUntil(this.destroy$)).subscribe(count => this.unreadNotifications = count);

    this.router.events.pipe(takeUntil(this.destroy$)).subscribe(event => {
      if (event instanceof NavigationStart) {
        this.routeLoading = true;
      }
      if (
        event instanceof NavigationEnd ||
        event instanceof NavigationCancel ||
        event instanceof NavigationError
      ) {
        this.mobileMenuOpen = false;
        this.notificationsOpen = false;
        if (this.routeLoaderTimer) {
          clearTimeout(this.routeLoaderTimer);
        }
        this.routeLoaderTimer = setTimeout(() => {
          this.routeLoading = false;
          this.routeLoaderTimer = null;
        }, 180);
      }
    });

    // Poll market status every 60s for footer
    timer(0, 60_000).pipe(
      switchMap(() => this.marketApi.getMarketStatus().pipe(
        catchError(() => of(null)),
      )),
      takeUntil(this.destroy$),
    ).subscribe(status => {
      if (status) {
        this.marketPhase = status.phase;
        this.setApiStatus('ok');
        if (this.lastMarketPhase && this.lastMarketPhase !== status.phase) {
          this.notify.info(`Market session changed: ${this.phaseLabel(status.phase)}`, 'Market');
        }
        this.lastMarketPhase = status.phase;
      } else {
        this.setApiStatus('error');
      }
    });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
    if (this.routeLoaderTimer) {
      clearTimeout(this.routeLoaderTimer);
      this.routeLoaderTimer = null;
    }
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
    this.notify.info(`Theme switched to ${this.darkMode ? 'dark' : 'light'} mode`, 'Preferences');
  }

  onTopbarSymbolSearched(symbol: string): void {
    this.rememberSymbol(symbol);
  }

  toggleNotificationsPanel(): void {
    this.notificationsOpen = !this.notificationsOpen;
    if (this.notificationsOpen) {
      this.notify.markAllRead();
    }
  }

  markNotificationRead(id: number): void {
    this.notify.markAsRead(id);
  }

  clearNotifications(): void {
    this.notify.clearHistory();
  }

  openCommandPalette(prefill = ''): void {
    this.recentSymbols = this.readRecentSymbols();
    this.commandQuery = prefill.toUpperCase();
    this.commandPaletteOpen = true;
    this.commandCursor = 0;
    this.notificationsOpen = false;
    this.filterCommands();
  }

  closeCommandPalette(): void {
    this.commandPaletteOpen = false;
    this.commandQuery = '';
    this.commandCursor = 0;
  }

  onCommandQueryInput(event: Event): void {
    this.commandQuery = (event.target as HTMLInputElement).value;
    this.commandCursor = 0;
    this.filterCommands();
  }

  moveCommandCursor(direction: 1 | -1): void {
    if (!this.filteredCommands.length) return;
    const next = this.commandCursor + direction;
    if (next < 0) {
      this.commandCursor = this.filteredCommands.length - 1;
      return;
    }
    this.commandCursor = next % this.filteredCommands.length;
  }

  runCommandAtCursor(): void {
    if (!this.filteredCommands.length) return;
    this.executeCommand(this.filteredCommands[this.commandCursor]);
  }

  executeCommand(command: CommandOption): void {
    switch (command.kind) {
      case 'route':
        if (command.route) {
          this.router.navigate([command.route]);
        }
        break;
      case 'symbol':
        if (command.symbol) {
          this.rememberSymbol(command.symbol);
          this.router.navigate(['/chart', command.symbol]);
        }
        break;
      case 'theme':
        this.toggleDarkMode();
        break;
      case 'refresh':
        this.onRefresh();
        break;
    }
    this.closeCommandPalette();
  }

  trackByNotification(_: number, item: AppNotification): number {
    return item.id;
  }

  trackByCommand(_: number, item: CommandOption): string {
    return item.id;
  }

  /** Global keyboard shortcuts */
  @HostListener('document:keydown', ['$event'])
  onKeydown(e: KeyboardEvent): void {
    const key = e.key.toLowerCase();
    const tag = (e.target as HTMLElement).tagName;
    const isTyping = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';

    if ((e.ctrlKey || e.metaKey) && key === 'k') {
      e.preventDefault();
      this.openCommandPalette();
      return;
    }

    if (this.commandPaletteOpen) {
      if (e.key === 'Escape') {
        e.preventDefault();
        this.closeCommandPalette();
        return;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        this.moveCommandCursor(1);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        this.moveCommandCursor(-1);
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        this.runCommandAtCursor();
        return;
      }
    }

    // Don't trigger inside input/textarea/select
    if (isTyping) return;

    if (e.key === 'Escape') {
      this.mobileMenuOpen = false;
      this.notificationsOpen = false;
    }

    // Ctrl+Shift+O → quick order / trading page
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && key === 'o') {
      e.preventDefault();
      this.router.navigate(['/trading']);
    }

    // Ctrl+Shift+D → toggle dark mode
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && key === 'd') {
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

  private phaseLabel(phase: string): string {
    switch (phase) {
      case 'open': return 'Market Open';
      case 'pre_open': return 'Pre-open';
      case 'post_close': return 'Post-close';
      case 'holiday': return 'Holiday';
      case 'weekend': return 'Weekend';
      default: return 'Closed';
    }
  }

  private setApiStatus(status: string): void {
    this.apiStatus = status;
    if (status !== this.lastApiStatus) {
      if (status === 'ok') {
        this.notify.success('API connectivity restored', 'Connectivity');
      } else {
        this.notify.error('API connectivity degraded. Some modules may fail.', 'Connectivity');
      }
      this.lastApiStatus = status;
    }
  }

  private rememberSymbol(symbol: string): void {
    const normalized = symbol.trim().toUpperCase();
    if (!normalized) return;
    const next = [normalized, ...this.recentSymbols.filter(s => s !== normalized)].slice(0, 12);
    this.recentSymbols = next;
    localStorage.setItem('st_recent_symbols', JSON.stringify(next));
  }

  private readRecentSymbols(): string[] {
    try {
      const raw = localStorage.getItem('st_recent_symbols');
      if (!raw) return [];
      const parsed: unknown = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed.filter((item): item is string => typeof item === 'string').map(item => item.toUpperCase());
    } catch {
      return [];
    }
  }

  private initCommandActions(): void {
    const navCommands: CommandOption[] = NAV_GROUPS.flatMap(group =>
      group.items.map(item => ({
        id: `route:${item.route}`,
        title: item.label,
        subtitle: `Open ${group.heading}`,
        icon: item.icon,
        keywords: `${item.label} ${group.heading} ${item.route}`.toLowerCase(),
        kind: 'route' as const,
        route: item.route,
      })),
    );

    const quickActions: CommandOption[] = [
      {
        id: 'action:trade',
        title: 'Quick Trade',
        subtitle: 'Jump to trading terminal',
        icon: 'lightning-fill',
        keywords: 'trade order quick terminal',
        kind: 'route',
        route: '/trading',
        hotkey: 'Ctrl+Shift+O',
      },
      {
        id: 'action:theme',
        title: 'Toggle Theme',
        subtitle: 'Switch dark/light mode',
        icon: 'moon-stars',
        keywords: 'theme dark light ui',
        kind: 'theme',
        hotkey: 'Ctrl+Shift+D',
      },
      {
        id: 'action:refresh',
        title: 'Hard Refresh',
        subtitle: 'Reload data and reconnect streams',
        icon: 'arrow-clockwise',
        keywords: 'refresh reload reconnect',
        kind: 'refresh',
      },
    ];

    this.commandActions = [...quickActions, ...navCommands];
    this.filterCommands();
  }

  private filterCommands(): void {
    const query = this.commandQuery.trim().toLowerCase();
    const commands: CommandOption[] = [];

    if (query) {
      const symbolCandidate = this.commandQuery.trim().toUpperCase().replace(/[^A-Z0-9_]/g, '');
      if (symbolCandidate.length >= 2) {
        commands.push({
          id: `symbol:${symbolCandidate}`,
          title: `Open chart: ${symbolCandidate}`,
          subtitle: 'Direct symbol navigation',
          icon: 'graph-up',
          keywords: `symbol chart ${symbolCandidate}`.toLowerCase(),
          kind: 'symbol',
          symbol: symbolCandidate,
        });
      }
    }

    for (const symbol of this.recentSymbols.slice(0, 8)) {
      commands.push({
        id: `recent:${symbol}`,
        title: symbol,
        subtitle: 'Recent symbol',
        icon: 'clock-history',
        keywords: `recent symbol ${symbol}`.toLowerCase(),
        kind: 'symbol',
        symbol,
      });
    }

    commands.push(...this.commandActions);
    const seen = new Set<string>();
    const deduped = commands.filter(cmd => {
      if (seen.has(cmd.id)) return false;
      seen.add(cmd.id);
      return true;
    });

    this.filteredCommands = deduped
      .filter(cmd => !query || `${cmd.title} ${cmd.subtitle} ${cmd.keywords}`.toLowerCase().includes(query))
      .slice(0, 18);

    if (!this.filteredCommands.length) {
      this.commandCursor = 0;
      return;
    }

    if (this.commandCursor >= this.filteredCommands.length) {
      this.commandCursor = this.filteredCommands.length - 1;
    }
  }
}
