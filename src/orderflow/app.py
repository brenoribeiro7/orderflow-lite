"""FastAPI application factory and ASGI entry point."""

from fastapi import FastAPI

from orderflow.api.error_handlers import install_error_handlers
from orderflow.api.health import router as health_router
from orderflow.api.orders import router as orders_router
from orderflow.api.products import router as products_router


def create_app() -> FastAPI:
    """Build the OrderFlow Lite HTTP application."""

    application = FastAPI(title="OrderFlow Lite", version="1.0.0")
    install_error_handlers(application)
    application.include_router(health_router)
    application.include_router(products_router)
    application.include_router(orders_router)
    return application


app = create_app()
