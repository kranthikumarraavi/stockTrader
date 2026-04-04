// Execution quality API service
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { retry } from 'rxjs/operators';
import { environment } from '../../environments/environment';
import {
  ExecutionStats, ExecutionReport, OrderTypeDecision,
  PriceCheckResult, LiquidityCheckResult,
} from '../core/models';

@Injectable({ providedIn: 'root' })
export class ExecutionApiService {
  private readonly base = environment.apiBaseUrl;

  constructor(private http: HttpClient) {}

  getStats(): Observable<ExecutionStats> {
    return this.http.get<ExecutionStats>(`${this.base}/execution/stats`).pipe(retry({ count: 2, delay: 1000 }));
  }

  getRecentReports(limit = 20): Observable<ExecutionReport[]> {
    return this.http.get<ExecutionReport[]>(`${this.base}/execution/reports`, { params: { limit } });
  }

  decideOrderType(payload: Record<string, unknown>): Observable<OrderTypeDecision> {
    return this.http.post<OrderTypeDecision>(`${this.base}/execution/decide-order-type`, payload);
  }

  priceCheck(payload: Record<string, unknown>): Observable<PriceCheckResult> {
    return this.http.post<PriceCheckResult>(`${this.base}/execution/price-check`, payload);
  }

  liquidityCheck(payload: Record<string, unknown>): Observable<LiquidityCheckResult> {
    return this.http.post<LiquidityCheckResult>(`${this.base}/execution/liquidity-check`, payload);
  }
}
