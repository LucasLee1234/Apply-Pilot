import logging

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

def create_app_api(
        title: str, lifespan: callable
) -> FastAPI:
    """Create a FastAPI application with common settings"""

    app = FastAPI(title=title, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "Accept",
            "Origin",
            "X-Requested-With",
        ],
    )

    @app.get("/root")
    async def root():
        """
        Root endpoint that provides a welcome message
        :return:
            dict: A dictionary containing the welcome message
        """

        return {"message": "Welcome!"}

    @app.get("/health")
    async def health_check():
        """
        Health endpoint to verify the service status
        :return:
            dict: A dictionary containing the health message
        """

        return {"status": "ok", "code": 200}
    return app