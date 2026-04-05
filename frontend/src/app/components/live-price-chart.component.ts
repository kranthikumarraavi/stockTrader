// Live price chart component
import { Component, Input, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface PriceTick {
  timestamp: string;
  price: number;
  volume: number;
}

@Component({
  selector: 'app-live-price-chart',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './live-price-chart.component.html',
  styleUrl: './live-price-chart.component.scss'
})
export class LivePriceChartComponent implements OnChanges {
  @Input() data: PriceTick[] = [];

  chartW = 800;
  chartH = 280;
  viewBox = '0 0 800 280';
  points = '';
  areaPoints = '';
  minPrice = 0;
  maxPrice = 0;
  currentPrice = 0;
  priceChange = 0;
  priceChangePct = 0;
  priceDirection = 'flat';
  lineColor = '#16a34a';
  areaFill = '#16a34a';
  currentPriceY = 0;
  lastPointX = 0;
  lastPointY = 0;
  yLabels: { value: number; pct: number; svgY: number }[] = [];
  xLabels: { text: string; pct: number }[] = [];

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['data'] && this.data.length > 0) {
      this.buildChart();
    }
  }

  private buildChart(): void {
    const prices = this.data.map(d => d.price);
    this.minPrice = Math.min(...prices);
    this.maxPrice = Math.max(...prices);

    // Add 2% padding to Y range
    const rawRange = this.maxPrice - this.minPrice || 1;
    const padding = rawRange * 0.04;
    const yMin = this.minPrice - padding;
    const yMax = this.maxPrice + padding;
    const range = yMax - yMin;

    // Current price info
    this.currentPrice = prices[prices.length - 1];
    const firstPrice = prices[0];
    this.priceChange = this.currentPrice - firstPrice;
    this.priceChangePct = firstPrice ? (this.priceChange / firstPrice) * 100 : 0;
    this.priceDirection = this.priceChange > 0.01 ? 'up' : this.priceChange < -0.01 ? 'down' : 'flat';
    this.lineColor = this.priceDirection === 'down' ? '#dc2626' : '#16a34a';
    this.areaFill = this.lineColor;

    // Build polyline points
    const pointPairs: string[] = [];
    const n = this.data.length;
    for (let i = 0; i < n; i++) {
      const x = n > 1 ? (i / (n - 1)) * this.chartW : this.chartW / 2;
      const y = this.chartH - ((prices[i] - yMin) / range) * this.chartH;
      pointPairs.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    }
    this.points = pointPairs.join(' ');

    // Area fill (polygon under the line)
    const lastX = n > 1 ? this.chartW : this.chartW / 2;
    this.areaPoints = `0,${this.chartH} ${pointPairs.join(' ')} ${lastX.toFixed(1)},${this.chartH}`;

    // Last point (for dot indicator)
    if (n > 1) {
      this.lastPointX = this.chartW;
      this.lastPointY = this.chartH - ((this.currentPrice - yMin) / range) * this.chartH;
      this.currentPriceY = this.lastPointY;
    }

    // Y-axis labels (5 labels)
    this.yLabels = [];
    const nLabels = 5;
    for (let i = 0; i <= nLabels; i++) {
      const value = this.minPrice + (rawRange * i) / nLabels;
      const pct = ((value - yMin) / range) * 100;
      const svgY = this.chartH - (pct / 100) * this.chartH;
      this.yLabels.push({ value, pct, svgY });
    }

    // X-axis labels (up to 6 time labels)
    this.xLabels = [];
    if (n > 1) {
      const nXLabels = Math.min(6, n);
      for (let i = 0; i < nXLabels; i++) {
        const idx = Math.round((i / (nXLabels - 1)) * (n - 1));
        const ts = this.data[idx].timestamp;
        const text = this.formatTime(ts);
        this.xLabels.push({ text, pct: (idx / (n - 1)) * 100 });
      }
    }
  }

  private formatTime(ts: string): string {
    try {
      const d = new Date(ts);
      const h = d.getHours();
      const m = d.getMinutes();
      if (h === 0 && m === 0) {
        // Daily data — show date
        return `${d.getDate()}/${d.getMonth() + 1}`;
      }
      return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
    } catch {
      return '';
    }
  }
}
