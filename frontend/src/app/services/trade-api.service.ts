// Trade API service
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { TradeIntentRequest, TradeIntent, Execution } from '../core/models';

export { TradeIntentRequest, TradeIntent, Execution };

@Injectable({ providedIn: 'root' })
export class TradeApiService {
  private readonly base = environment.apiBaseUrl;

  constructor(private http: HttpClient) {}

  createIntent(request: TradeIntentRequest): Observable<TradeIntent> {
    return this.http.post<TradeIntent>(`${this.base}/trade_intent`, request);
  }

  execute(intentId: string): Observable<Execution> {
    return this.http.post<Execution>(`${this.base}/execute`, { intent_id: intentId });
  }
}

