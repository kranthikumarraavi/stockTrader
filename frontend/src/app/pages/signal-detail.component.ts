// Signal detail page component
import { Component, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { PredictionApiService, OptionSignal } from '../services/prediction-api.service';
import { LivePriceChartComponent, PriceTick } from '../components/live-price-chart.component';
import { PriceStreamService } from '../services/price-stream.service';
import { Subscription } from 'rxjs';
import { NotificationService } from '../services/notification.service';

@Component({
  selector: 'app-signal-detail',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, LivePriceChartComponent],
  templateUrl: './signal-detail.component.html',
  styleUrl: './signal-detail.component.scss',
})
export class SignalDetailComponent implements OnDestroy {
  underlying = 'NIFTY';
  strike = 22000;
  expiry = '';
  optionType: 'CE' | 'PE' = 'CE';
  signal: OptionSignal | null = null;
  error: string | null = null;
  loading = false;
  ticks: PriceTick[] = [];
  streamSub: Subscription | null = null;
  private routeSub: Subscription | null = null;

  constructor(
    private route: ActivatedRoute,
    private predictionApi: PredictionApiService,
    private priceStream: PriceStreamService,
    private notify: NotificationService,
  ) {
    this.expiry = this.nextThursdayIso();

    this.routeSub = this.route.paramMap.subscribe(params => {
      const symbol = params.get('symbol')?.trim().toUpperCase();
      if (!symbol) return;

      this.underlying = symbol;
      this.signal = null;
      this.error = null;
      this.fetchSignal();
      this.startStream();
    });
  }

  fetchSignal(): void {
    this.error = null;
    this.loading = true;
    this.predictionApi.predictOptions(this.underlying, this.strike, this.expiry, this.optionType).subscribe({
      next: res => { this.signal = res.signal ?? (res as any); this.loading = false; },
      error: () => {
        this.error = 'Failed to fetch signal';
        this.loading = false;
        this.notify.error('Failed to fetch options signal.');
      }
    });
  }

  startStream(): void {
    this.stopStream();
    this.ticks = [];
    this.streamSub = this.priceStream.connect(this.underlying).subscribe(tick => {
      this.ticks = [...this.ticks.slice(-200), tick];
    });
  }

  stopStream(): void {
    this.streamSub?.unsubscribe();
    this.streamSub = null;
  }

  ngOnDestroy(): void {
    this.routeSub?.unsubscribe();
    this.routeSub = null;
    this.stopStream();
  }

  private nextThursdayIso(): string {
    const d = new Date();
    d.setDate(d.getDate() + ((4 - d.getDay() + 7) % 7 || 7));
    return d.toISOString().slice(0, 10);
  }

  actionClass(action: string | null | undefined): string {
    const normalized = (action || '').toLowerCase();
    if (normalized === 'buy') return 'sd__badge--buy';
    if (normalized === 'sell') return 'sd__badge--sell';
    return 'sd__badge--hold';
  }
}
