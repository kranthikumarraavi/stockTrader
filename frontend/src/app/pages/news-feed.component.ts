import {
  Component, ChangeDetectionStrategy, ChangeDetectorRef,
  OnInit, OnDestroy,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, takeUntil, timer, catchError, of } from 'rxjs';

import { IntelligenceApiService } from '../services/intelligence-api.service';
import { NewsArticle, SentimentResult, AnomalyAlert } from '../core/models/news.model';

import {
  StateBadgeComponent, LoadingSkeletonComponent, EmptyStateComponent,
  BadgeVariant,
} from '../shared';

@Component({
  selector: 'app-news-feed',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    StateBadgeComponent, LoadingSkeletonComponent, EmptyStateComponent,
  ],
  templateUrl: './news-feed.component.html',
  styleUrl: './news-feed.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class NewsFeedComponent implements OnInit, OnDestroy {
  // News
  newsSymbol = 'RELIANCE';
  news: NewsArticle[] = [];
  newsLoading = false;

  // Sentiment
  sentimentText = '';
  sentimentResult: SentimentResult | null = null;
  sentimentLoading = false;

  // Alerts
  alerts: AnomalyAlert[] = [];
  alertsLoading = true;

  private destroy$ = new Subject<void>();

  constructor(
    private cdr: ChangeDetectorRef,
    private intelligenceApi: IntelligenceApiService,
  ) {}

  ngOnInit(): void {
    this.loadAlerts();
    timer(30_000, 30_000).pipe(takeUntil(this.destroy$)).subscribe(() => this.loadAlerts());
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  // ── Computed ──
  sentimentBadge(label: string | undefined): BadgeVariant {
    switch (label) {
      case 'positive': return 'success';
      case 'negative': return 'danger';
      default: return 'neutral';
    }
  }

  severityBadge(severity: string): BadgeVariant {
    switch (severity) {
      case 'high': return 'danger';
      case 'medium': return 'warning';
      default: return 'info';
    }
  }

  severityBorder(severity: string): string {
    switch (severity) {
      case 'high': return 'nf__alert--high';
      case 'medium': return 'nf__alert--med';
      default: return 'nf__alert--low';
    }
  }

  // ── Actions ──
  loadNews(): void {
    if (!this.newsSymbol.trim()) return;
    this.newsLoading = true;
    this.cdr.markForCheck();

    this.intelligenceApi.fetchNews(this.newsSymbol.trim()).pipe(
      catchError(() => of([])),
      takeUntil(this.destroy$),
    ).subscribe(articles => {
      this.news = articles;
      this.newsLoading = false;
      this.cdr.markForCheck();
    });
  }

  analyzeSentiment(): void {
    if (!this.sentimentText.trim()) return;
    this.sentimentLoading = true;
    this.cdr.markForCheck();

    this.intelligenceApi.scoreSentiment(this.sentimentText).pipe(
      catchError(() => of(null)),
      takeUntil(this.destroy$),
    ).subscribe(result => {
      this.sentimentResult = result;
      this.sentimentLoading = false;
      this.cdr.markForCheck();
    });
  }

  trackByTitle(_: number, a: NewsArticle): string { return a.title; }
  trackByAlert(_: number, a: AnomalyAlert): string { return `${a.ticker}_${a.type}`; }

  private loadAlerts(): void {
    this.intelligenceApi.getRecentAlerts().pipe(
      catchError(() => of([])),
      takeUntil(this.destroy$),
    ).subscribe(alerts => {
      this.alerts = alerts;
      this.alertsLoading = false;
      this.cdr.markForCheck();
    });
  }
}
