// Options strategy API service
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { OptionLeg, StrategyRecommendation } from '../core/models';
import { PayoffPoint } from '../core/models';

export { OptionLeg, StrategyRecommendation };

@Injectable({ providedIn: 'root' })
export class OptionsApiService {
  private readonly base = environment.apiBaseUrl;

  constructor(private http: HttpClient) {}

  recommendStrategy(payload: Record<string, unknown>): Observable<StrategyRecommendation> {
    return this.http.post<StrategyRecommendation>(`${this.base}/options/recommend`, payload);
  }

  buildCoveredCall(payload: Record<string, unknown>): Observable<StrategyRecommendation> {
    return this.http.post<StrategyRecommendation>(`${this.base}/options/covered-call`, payload);
  }

  buildBullCallSpread(payload: Record<string, unknown>): Observable<StrategyRecommendation> {
    return this.http.post<StrategyRecommendation>(`${this.base}/options/bull-call-spread`, payload);
  }

  buildIronCondor(payload: Record<string, unknown>): Observable<StrategyRecommendation> {
    return this.http.post<StrategyRecommendation>(`${this.base}/options/iron-condor`, payload);
  }

  buildStraddle(payload: Record<string, unknown>): Observable<StrategyRecommendation> {
    return this.http.post<StrategyRecommendation>(`${this.base}/options/straddle`, payload);
  }

  computePayoff(legs: OptionLeg[], spotRange?: [number, number], points = 100): Observable<PayoffPoint[]> {
    return this.http.post<PayoffPoint[]>(`${this.base}/options/payoff`, {
      legs,
      spot_range: spotRange,
      points,
    });
  }
}
