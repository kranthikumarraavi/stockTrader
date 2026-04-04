// Paper API service
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../environments/environment';
import { PaperAccount, EquityPoint, AccountMetrics } from '../core/models';

export { PaperAccount, EquityPoint, AccountMetrics };

@Injectable({ providedIn: 'root' })
export class PaperApiService {
  private readonly base = environment.apiBaseUrl;

  constructor(private http: HttpClient) {}

  createAccount(): Observable<PaperAccount> {
    return this.http.post<PaperAccount>(`${this.base}/paper/accounts`, { initial_cash: 100000 });
  }

  listAccounts(): Observable<PaperAccount[]> {
    return this.http.get<PaperAccount[]>(`${this.base}/paper/accounts`);
  }

  getEquity(accountId: string): Observable<EquityPoint[]> {
    return this.http.get<EquityPoint[]>(`${this.base}/paper/${accountId}/equity`);
  }

  getMetrics(accountId: string): Observable<AccountMetrics> {
    return this.http.get<AccountMetrics>(`${this.base}/paper/${accountId}/metrics`);
  }

  replay(accountId: string, date: string, speed: number = 1): Observable<Record<string, unknown>> {
    return this.http.post<Record<string, unknown>>(`${this.base}/paper/${accountId}/replay`, { date, speed });
  }

  submitOrderIntent(accountId: string, intent: Record<string, unknown>): Observable<unknown> {
    return this.http.post(`${this.base}/paper/${accountId}/order_intent`, intent);
  }
}
