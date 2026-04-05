// Simulation summary card component
import { Component, Input, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { PaperApiService, AccountMetrics } from '../services/paper-api.service';

@Component({
  selector: 'app-simulation-summary-card',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './simulation-summary-card.component.html',
  styleUrl: './simulation-summary-card.component.scss'
})
export class SimulationSummaryCardComponent implements OnInit {
  @Input() accountId!: string;
  metrics: AccountMetrics | null = null;

  constructor(private paperApi: PaperApiService) {}

  ngOnInit(): void {
    this.paperApi.getMetrics(this.accountId).subscribe({
      next: m => this.metrics = m,
      error: () => {}
    });
  }
}
