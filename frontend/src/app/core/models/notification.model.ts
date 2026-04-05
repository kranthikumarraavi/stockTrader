/** Notification / toast models */

export type ToastType = 'success' | 'error' | 'info' | 'warning';

export interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

export interface AppNotification {
  id: number;
  message: string;
  type: ToastType;
  source: string;
  createdAt: string;
  read: boolean;
}
