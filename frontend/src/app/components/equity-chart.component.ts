// Equity chart component
import { Component, Input, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';

interface DrawdownPoint {
  date: string;
  equity: number;
  drawdown: number;
}

@Component({
  selector: 'app-equity-chart',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './equity-chart.component.html',
  styleUrl: './equity-chart.component.scss'
})
export class EquityChartComponent implements OnChanges {
  @Input() data: { date: string; equity: number }[] = [];

  width = 800;
  eqHeight = 200;
  ddHeight = 120;
  equityPoints = '';
  drawdownPoints = '';
  minEquity = 0;
  maxEquity = 0;
  minDrawdown = 0;

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['data'] && this.data.length > 0) {
      this.buildCharts();
    }
  }

  private buildCharts(): void {
    const equities = this.data.map(d => d.equity);
    this.minEquity = Math.min(...equities);
    this.maxEquity = Math.max(...equities);
    const eqRange = this.maxEquity - this.minEquity || 1;
    const n = this.data.length;
    const xDivisor = n > 1 ? n - 1 : 1;

    this.equityPoints = this.data.map((d, i) => {
      const x = (i / xDivisor) * this.width;
      const y = this.eqHeight - ((d.equity - this.minEquity) / eqRange) * this.eqHeight;
      return `${x},${y}`;
    }).join(' ');

    // Drawdown calculation
    let peak = this.data[0].equity;
    const ddData = this.data.map(d => {
      peak = Math.max(peak, d.equity);
      return ((d.equity - peak) / peak) * 100;
    });
    this.minDrawdown = Math.min(...ddData);
    const ddRange = Math.abs(this.minDrawdown) || 1;
    const ddDivisor = ddData.length > 1 ? ddData.length - 1 : 1;

    this.drawdownPoints = ddData.map((dd, i) => {
      const x = (i / ddDivisor) * this.width;
      const y = (Math.abs(dd) / ddRange) * this.ddHeight;
      return `${x},${y}`;
    }).join(' ');
  }
}