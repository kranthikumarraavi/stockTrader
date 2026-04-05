// Notification service
import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { AppNotification, Toast, ToastType } from '../core/models';

@Injectable({ providedIn: 'root' })
export class NotificationService {
  private counter = 0;
  private toastsSubject = new BehaviorSubject<Toast[]>([]);
  private notificationsSubject = new BehaviorSubject<AppNotification[]>([]);
  private unreadCountSubject = new BehaviorSubject<number>(0);

  private readonly maxHistory = 200;

  toasts$ = this.toastsSubject.asObservable();
  notifications$ = this.notificationsSubject.asObservable();
  unreadCount$ = this.unreadCountSubject.asObservable();

  success(message: string, source = 'System'): void { this.add(message, 'success', source); }
  error(message: string, source = 'System'): void { this.add(message, 'error', source); }
  info(message: string, source = 'System'): void { this.add(message, 'info', source); }
  warning(message: string, source = 'System'): void { this.add(message, 'warning', source); }

  private add(message: string, type: ToastType, source: string): void {
    const toast: Toast = { id: ++this.counter, message, type };
    const entry: AppNotification = {
      id: toast.id,
      message,
      type,
      source,
      createdAt: new Date().toISOString(),
      read: false,
    };

    this.toastsSubject.next([...this.toastsSubject.value, toast]);
    this.notificationsSubject.next([entry, ...this.notificationsSubject.value].slice(0, this.maxHistory));
    this.updateUnreadCount();

    setTimeout(() => this.remove(toast.id), 4000);
  }

  remove(id: number): void {
    this.toastsSubject.next(this.toastsSubject.value.filter(t => t.id !== id));
  }

  markAsRead(id: number): void {
    const updated = this.notificationsSubject.value.map(n => n.id === id ? { ...n, read: true } : n);
    this.notificationsSubject.next(updated);
    this.updateUnreadCount();
  }

  markAllRead(): void {
    this.notificationsSubject.next(this.notificationsSubject.value.map(n => ({ ...n, read: true })));
    this.updateUnreadCount();
  }

  clearHistory(): void {
    this.notificationsSubject.next([]);
    this.updateUnreadCount();
  }

  private updateUnreadCount(): void {
    const unread = this.notificationsSubject.value.reduce((acc, item) => acc + (item.read ? 0 : 1), 0);
    this.unreadCountSubject.next(unread);
  }
}
