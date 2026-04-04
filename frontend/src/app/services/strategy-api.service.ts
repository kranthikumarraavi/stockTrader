// Strategy intelligence & regime detection API service
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { RegimeResult, StrategyDecision } from '../core/models';
import { StrategyStats, StrategyHistoryEntry } from '../core/models';

export { RegimeResult, StrategyDecision };

@Injectable({ providedIn: 'root' })
export class StrategyApiService {
  private readonly base = environment.apiBaseUrl;

  constructor(private http: HttpClient) {}

  detectRegime(symbol: string): Observable<RegimeResult> {
    return this.http.get<RegimeResult>(`${this.base}/regime/${symbol}`);
  }

  regimeHeatmap(symbols?: string[]): Observable<Record<string, RegimeResult>> {
    const params: Record<string, string> = {};
    if (symbols?.length) {
      params['symbols'] = symbols.join(',');
    }
    return this.http.get<Record<string, RegimeResult>>(`${this.base}/regime`, { params });
  }

  selectStrategy(payload: Record<string, unknown>): Observable<StrategyDecision> {
    return this.http.post<StrategyDecision>(`${this.base}/strategy/select`, payload);
  }

  getRecentDecisions(limit = 20): Observable<StrategyHistoryEntry[]> {
    return this.http.get<StrategyHistoryEntry[]>(`${this.base}/strategy/decisions`, { params: { limit } });
  }

  getStats(): Observable<StrategyStats> {
    return this.http.get<StrategyStats>(`${this.base}/strategy/stats`);
  }
}
