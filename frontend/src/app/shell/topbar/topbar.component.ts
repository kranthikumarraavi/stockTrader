import { Component, Input, Output, EventEmitter, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { Subject, takeUntil, timer, switchMap, catchError, of } from 'rxjs';
import { MarketApiService } from '../../services/market-api.service';
import { LiveStreamService } from '../../services/live-stream.service';
import { ClickOutsideDirective } from '../../shared/directives/click-outside.directive';

@Component({
  selector: 'app-topbar',
  standalone: true,
  imports: [CommonModule, ClickOutsideDirective],
  templateUrl: './topbar.component.html',
  styleUrl: './topbar.component.scss',
})
export class TopbarComponent implements OnInit, OnDestroy {
  @Input() darkMode = false;
  @Input() wsConnected = false;
  @Input() apiStatus = 'ok';
  @Input() unreadCount = 0;
  @Output() menuToggle = new EventEmitter<void>();
  @Output() quickTrade = new EventEmitter<void>();
  @Output() refresh = new EventEmitter<void>();
  @Output() toggleTheme = new EventEmitter<void>();
  @Output() commandPalette = new EventEmitter<void>();
  @Output() notificationsToggle = new EventEmitter<void>();
  @Output() symbolSearched = new EventEmitter<string>();

  searchQuery = '';
  marketPhase = 'closed';
  showSearchDropdown = false;
  activeSuggestion = -1;
  filteredSymbols: string[] = [];
  readonly popularSymbols = [
    'RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'SBIN',
    'AXISBANK', 'BAJFINANCE', 'NIFTY50', 'BANKNIFTY',
  ];
  private universeSymbols: string[] = [];
  private recentSymbols: string[] = [];

  private destroy$ = new Subject<void>();

  constructor(
    private router: Router,
    private marketApi: MarketApiService,
    private liveStream: LiveStreamService,
  ) {}

  get marketPhaseLabel(): string {
    const labels: Record<string, string> = {
      open: 'Market Open',
      pre_open: 'Pre-Open',
      post_close: 'Post-Close',
      closed: 'Closed',
      holiday: 'Holiday',
      weekend: 'Weekend',
    };
    return labels[this.marketPhase] ?? this.marketPhase;
  }

  ngOnInit(): void {
    this.recentSymbols = this.readRecentSymbols();
    this.refreshSuggestions();

    // Poll market status every 60s
    timer(0, 60_000).pipe(
      switchMap(() => this.marketApi.getMarketStatus().pipe(
        catchError(() => of(null)),
      )),
      takeUntil(this.destroy$),
    ).subscribe(status => {
      if (status) {
        this.marketPhase = status.phase;
      }
    });

    this.liveStream.getSymbols().pipe(
      catchError(() => of({ symbols: [] })),
      takeUntil(this.destroy$),
    ).subscribe(res => {
      this.universeSymbols = (res.symbols || []).map(s => s.toUpperCase());
      this.refreshSuggestions();
    });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  onSearchInput(event: Event): void {
    this.searchQuery = (event.target as HTMLInputElement).value;
    this.refreshSuggestions();
    this.showSearchDropdown = true;
    this.activeSuggestion = this.filteredSymbols.length ? 0 : -1;
  }

  onSearchFocus(): void {
    this.refreshSuggestions();
    this.showSearchDropdown = true;
  }

  onSearchKeydown(event: KeyboardEvent): void {
    if (!this.showSearchDropdown && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) {
      this.showSearchDropdown = true;
      return;
    }

    if (event.key === 'ArrowDown' && this.filteredSymbols.length > 0) {
      event.preventDefault();
      this.activeSuggestion = (this.activeSuggestion + 1) % this.filteredSymbols.length;
      return;
    }

    if (event.key === 'ArrowUp' && this.filteredSymbols.length > 0) {
      event.preventDefault();
      this.activeSuggestion = (this.activeSuggestion - 1 + this.filteredSymbols.length) % this.filteredSymbols.length;
      return;
    }

    if (event.key === 'Enter' && this.showSearchDropdown && this.activeSuggestion >= 0) {
      event.preventDefault();
      this.selectSuggestion(this.filteredSymbols[this.activeSuggestion]);
      return;
    }

    if (event.key === 'Enter') {
      event.preventDefault();
      this.onSearchSubmit();
      return;
    }

    if (event.key === 'Escape') {
      this.showSearchDropdown = false;
    }
  }

  onSearchSubmit(): void {
    const candidate = this.searchQuery.trim().toUpperCase();
    if (!candidate) return;
    this.navigateToSymbol(candidate);
  }

  selectSuggestion(symbol: string): void {
    this.navigateToSymbol(symbol);
    this.showSearchDropdown = false;
  }

  closeSearchDropdown(): void {
    this.showSearchDropdown = false;
  }

  triggerCommandPalette(): void {
    this.commandPalette.emit();
  }

  private navigateToSymbol(symbol: string): void {
    this.router.navigate(['/chart', symbol]);
    this.symbolSearched.emit(symbol);
    this.addRecentSymbol(symbol);
    this.searchQuery = '';
    this.refreshSuggestions();
  }

  private refreshSuggestions(): void {
    const query = this.searchQuery.trim().toUpperCase();
    const universe = [...this.recentSymbols, ...this.popularSymbols, ...this.universeSymbols];
    const deduped = Array.from(new Set(universe));

    const matches = query
      ? deduped.filter(s => s.includes(query))
      : deduped;

    this.filteredSymbols = matches.slice(0, 8);
    if (this.filteredSymbols.length === 0) {
      this.activeSuggestion = -1;
    } else if (this.activeSuggestion >= this.filteredSymbols.length) {
      this.activeSuggestion = 0;
    }
  }

  private addRecentSymbol(symbol: string): void {
    const next = [symbol, ...this.recentSymbols.filter(s => s !== symbol)].slice(0, 12);
    this.recentSymbols = next;
    localStorage.setItem('st_recent_symbols', JSON.stringify(next));
  }

  private readRecentSymbols(): string[] {
    try {
      const raw = localStorage.getItem('st_recent_symbols');
      if (!raw) return [];
      const parsed: unknown = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed.filter((v): v is string => typeof v === 'string').map(v => v.toUpperCase());
    } catch {
      return [];
    }
  }
}
