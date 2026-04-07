"""Trading Microservice – Port 8003.

Trade intents, execution, paper trading, bot, options, orchestrator.
"""

from dotenv import load_dotenv
load_dotenv()

from common_logging import setup_logging
from app.config import SERVICE_NAME

setup_logging(SERVICE_NAME)

from backend.api.services.base import create_service_app
from backend.api.routers import trade, paper, bot, options, execution, orchestrator
from common_utils.health import add_health_endpoints

app = create_service_app(title="StockTrader – Trading Service")

app.include_router(trade.router, prefix="/api/v1")
app.include_router(paper.router, prefix="/api/v1")
app.include_router(bot.router, prefix="/api/v1")
app.include_router(options.router, prefix="/api/v1")
app.include_router(execution.router, prefix="/api/v1")
app.include_router(orchestrator.router, prefix="/api/v1")

add_health_endpoints(app, SERVICE_NAME)
