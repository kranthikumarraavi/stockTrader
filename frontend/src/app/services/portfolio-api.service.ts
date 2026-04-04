// Portfolio intelligence API service
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { PortfolioMetrics } from '../core/models';

export { PortfolioMetrics };

@Injectable({ providedIn: 'root' })
export class PortfolioApiService {
  private readonly base = environment.apiBaseUrl;

  constructor(private http: HttpClient) {}

  computeMetrics(payload: Record<string, unknown>): Observable<PortfolioMetrics> {
    return this.http.post<PortfolioMetrics>(`${this.base}/portfolio/metrics`, payload);
  }

  getExposureHeatmap(positions: Record<string, unknown>): Observable<Record<string, Record<string, number>>> {
    return this.http.post<Record<string, Record<string, number>>>(`${this.base}/portfolio/exposure`, { positions });
  }

  getCapitalAllocation(payload: Record<string, unknown>): Observable<Record<string, unknown>> {
    return this.http.post<Record<string, unknown>>(`${this.base}/portfolio/allocation`, payload);
  }

  getDailySummary(payload: Record<string, unknown>): Observable<Record<string, unknown>> {
    return this.http.post<Record<string, unknown>>(`${this.base}/portfolio/daily-summary`, payload);
  }

  getSnapshot(): Observable<Record<string, unknown>> {
    return this.http.get<Record<string, unknown>>(`${this.base}/portfolio/snapshot`);
  }
}
