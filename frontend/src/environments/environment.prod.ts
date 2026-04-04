export const environment = {
  production: true,
  apiBaseUrl: {
    prediction: 'https://stocktrader-prediction-irpt.onrender.com/api/v1',
    admin: 'https://stocktrader-admin-irpt.onrender.com/api/v1',
    trading: 'https://stocktrader-trading-irpt.onrender.com/api/v1',
    marketData: 'https://stocktrader-market-data-irpt.onrender.com/api/v1',
  },
  wsBaseUrl: 'wss://stocktrader-market-data-irpt.onrender.com/api/v1',
  enableMocks: false,
  enableDebugTools: false,
  marketTimezone: 'Asia/Kolkata',
  defaultTheme: 'light' as 'light' | 'dark',
  cacheTtlMs: 15_000,
  wsReconnectMaxMs: 60_000,
};
