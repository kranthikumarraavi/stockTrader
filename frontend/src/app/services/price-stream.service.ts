// Price stream service — uses managed WebSocket via core/services/websocket.service
import { Injectable, OnDestroy } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { PriceTick } from '../core/models';
import { WebsocketService, ManagedConnection } from '../core/services/websocket.service';

export { PriceTick };

@Injectable({ providedIn: 'root' })
export class PriceStreamService implements OnDestroy {
  private connections = new Map<string, ManagedConnection>();

  constructor(private wsService: WebsocketService) {}

  ngOnDestroy(): void {
    this.connections.forEach(c => c.disconnect());
    this.connections.clear();
  }

  connect(symbol: string): Observable<PriceTick> {
    const path = `/stream/price/${encodeURIComponent(symbol)}`;
    const sseUrl = `${environment.apiBaseUrl}/stream/price/${encodeURIComponent(symbol)}`;

    return new Observable<PriceTick>(subscriber => {
      const conn = this.wsService.connect(path, sseUrl);
      this.connections.set(symbol, conn);

      const sub = conn.messages$.subscribe(msg => {
        subscriber.next(msg as PriceTick);
      });

      return () => {
        sub.unsubscribe();
        conn.disconnect();
        this.connections.delete(symbol);
      };
    });
  }
}
