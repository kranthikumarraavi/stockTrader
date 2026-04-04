export const environment = {
  production: true,
  apiBaseUrl: 'https://stocktrader-gateway-irpt.onrender.com/api/v1',
  wsBaseUrl: 'wss://stocktrader-market-data-irpt.onrender.com/api/v1',
  enableMocks: false,
  enableDebugTools: false,
  marketTimezone: 'Asia/Kolkata',
  defaultTheme: 'light' as 'light' | 'dark',
  cacheTtlMs: 15_000,
  wsReconnectMaxMs: 60_000,
};
