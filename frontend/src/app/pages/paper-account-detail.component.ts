// Paper account detail page component
import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { PaperApiService, EquityPoint } from '../services/paper-api.service';
import { NotificationService } from '../services/notification.service';
import { EquityChartComponent } from '../components/equity-chart.component';
import { SimulationSummaryCardComponent } from '../components/simulation-summary-card.component';
import { OrderIntentFormComponent, OrderIntentData } from '../components/order-intent-form.component';

@Component({
  selector: 'app-paper-account-detail',
  standalone: true,
  imports: [CommonModule, FormsModule, EquityChartComponent, SimulationSummaryCardComponent, OrderIntentFormComponent],
  templateUrl: './paper-account-detail.component.html',
  styleUrl: './paper-account-detail.component.scss',
})
export class PaperAccountDetailComponent implements OnInit {
  accountId: string | null = null;
  equity: EquityPoint[] = [];
  replayDate = '2025-01-02';
  replaySpeed = 10;
  replayResult: Record<string, unknown> | null = null;
  replaying = false;

  constructor(
    private route: ActivatedRoute,
    private paperApi: PaperApiService,
    private notify: NotificationService,
  ) {}

  ngOnInit(): void {
    this.accountId = this.route.snapshot.paramMap.get('accountId');
    if (this.accountId) {
      this.paperApi.getEquity(this.accountId).subscribe({
        next: data => this.equity = data,
        error: () => this.notify.error('Failed to load equity curve.')
      });
    }
  }

  runReplay(): void {
    if (!this.accountId) return;
    this.replaying = true;
    this.paperApi.replay(this.accountId, this.replayDate, this.replaySpeed).subscribe({
      next: result => {
        this.replayResult = result;
        this.replaying = false;
        this.notify.success('Replay complete.');
        this.paperApi.getEquity(this.accountId!).subscribe({
          next: data => this.equity = data,
          error: () => this.notify.error('Failed to refresh equity curve.')
        });
      },
      error: () => {
        this.replaying = false;
        this.notify.error('Replay failed.');
      }
    });
  }

  submitOrder(intent: OrderIntentData): void {
    if (!this.accountId) return;
    this.paperApi.submitOrderIntent(this.accountId, intent as unknown as Record<string, unknown>).subscribe({
      next: () => {
        this.notify.success('Order submitted.');
        this.paperApi.getEquity(this.accountId!).subscribe({
          next: data => this.equity = data,
          error: () => this.notify.error('Failed to refresh equity curve.')
        });
      },
      error: () => this.notify.error('Order submission failed.')
    });
  }
}
