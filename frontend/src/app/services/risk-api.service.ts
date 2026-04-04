// Risk management API service
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { RiskStatus, RiskApproval } from '../core/models';
import { RiskSnapshot } from '../core/models';

export { RiskStatus, RiskApproval };

@Injectable({ providedIn: 'root' })
export class RiskApiService {
  private readonly base = environment.apiBaseUrl;

  constructor(private http: HttpClient) {}

  getStatus(): Observable<RiskStatus> {
    return this.http.get<RiskStatus>(`${this.base}/risk/status`);
  }

  getSectorExposure(): Observable<Record<string, number>> {
    return this.http.get<Record<string, number>>(`${this.base}/risk/exposure/sector`);
  }

  getInstrumentExposure(): Observable<Record<string, number>> {
    return this.http.get<Record<string, number>>(`${this.base}/risk/exposure/instrument`);
  }

  getStrategyExposure(): Observable<Record<string, number>> {
    return this.http.get<Record<string, number>>(`${this.base}/risk/exposure/strategy`);
  }

  getPortfolioGreeks(): Observable<Record<string, number>> {
    return this.http.get<Record<string, number>>(`${this.base}/risk/greeks`);
  }

  approveTrade(payload: Record<string, unknown>): Observable<RiskApproval> {
    return this.http.post<RiskApproval>(`${this.base}/risk/approve`, payload);
  }

  getSnapshots(limit = 20): Observable<RiskSnapshot[]> {
    return this.http.get<RiskSnapshot[]>(`${this.base}/risk/snapshot`, { params: { limit } });
  }
}
