// Market API service
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { retry } from 'rxjs/operators';
import { environment } from '../../environments/environment';
import { MarketStatus, AccountProfile, BotStatus, BotConfig } from '../core/models';

export { MarketStatus, AccountProfile, BotStatus };

@Injectable({ providedIn: 'root' })
export class MarketApiService {
  private readonly base = environment.apiBaseUrl;

  constructor(private http: HttpClient) {}

  getMarketStatus(): Observable<MarketStatus> {
    return this.http.get<MarketStatus>(`${this.base}/market/status`).pipe(
      retry({ count: 2, delay: 1000 }),
    );
  }

  getAccountProfile(): Observable<AccountProfile> {
    return this.http.get<AccountProfile>(`${this.base}/account/profile`);
  }

  getBotStatus(): Observable<BotStatus> {
    return this.http.get<BotStatus>(`${this.base}/bot/status`);
  }

  startBot(config?: Partial<BotConfig>): Observable<Record<string, unknown>> {
    return this.http.post<Record<string, unknown>>(`${this.base}/bot/start`, config || {});
  }

  stopBot(): Observable<Record<string, unknown>> {
    return this.http.post<Record<string, unknown>>(`${this.base}/bot/stop`, {});
  }

  updateBotConfig(config: Partial<BotConfig>): Observable<Record<string, unknown>> {
    return this.http.put<Record<string, unknown>>(`${this.base}/bot/config`, config);
  }

  botConsent(resume: boolean): Observable<Record<string, unknown>> {
    return this.http.post<Record<string, unknown>>(`${this.base}/bot/consent`, { resume });
  }
}