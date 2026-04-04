// News, sentiment & anomaly detection API service
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { retry } from 'rxjs/operators';
import { environment } from '../../environments/environment';
import { SentimentResult, AnomalyAlert, NewsArticle } from '../core/models';

export { SentimentResult, AnomalyAlert, NewsArticle };

@Injectable({ providedIn: 'root' })
export class IntelligenceApiService {
  private readonly base = environment.apiBaseUrl;

  constructor(private http: HttpClient) {}

  scoreSentiment(text: string): Observable<SentimentResult> {
    return this.http.post<SentimentResult>(`${this.base}/sentiment/score`, { text });
  }

  fetchNews(symbol: string, limit = 10): Observable<NewsArticle[]> {
    return this.http.get<NewsArticle[]>(`${this.base}/news/${symbol}`, { params: { limit } }).pipe(
      retry({ count: 2, delay: 1000 }),
    );
  }

  checkAnomalies(payload: Record<string, unknown>): Observable<AnomalyAlert[]> {
    return this.http.post<AnomalyAlert[]>(`${this.base}/anomaly/check`, payload);
  }

  getRecentAlerts(limit = 20): Observable<AnomalyAlert[]> {
    return this.http.get<AnomalyAlert[]>(`${this.base}/anomaly/alerts`, { params: { limit } });
  }
}
