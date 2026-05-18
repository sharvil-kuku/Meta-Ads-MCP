# ruff: noqa: E402
from contextlib import asynccontextmanager
import sys
import os

from dotenv import load_dotenv

# Load environment variables from .env file (use absolute path for MCP)
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(env_path)

import structlog
from fastmcp import FastMCP

from persistence.action_log import init_db

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
)
from tools.account_tools import account_tools
from tools.adset_tools import adset_tools
from tools.campaign_tools import campaign_tools
from tools.data_tools import data_tools
from tools.optimiser_tools import optimiser_tools
from tools.write_tools import write_tools
from tools.report_tools import report_tools
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware import Middleware as ASGIMiddleware


@asynccontextmanager
async def db_lifespan(server):
    init_db()
    yield {}


mcp = FastMCP(
    name="meta-ads-mcp",
    instructions="Meta Ads operations: campaign management, adset management, insights, optimiser, apply changes",
    version="1.0.0",
    lifespan=db_lifespan,
)

# Define CORS middleware for HTTP transport
cors_middleware = [
    ASGIMiddleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
]

mcp.mount(account_tools)
mcp.mount(adset_tools)
mcp.mount(campaign_tools)
mcp.mount(data_tools)
mcp.mount(optimiser_tools)
mcp.mount(write_tools)
mcp.mount(report_tools)


if __name__ == "__main__":
    import sys

    if "--http" in sys.argv:
        mcp.run(
            transport="sse",
            host="0.0.0.0",
            port=8000,
            middleware=cors_middleware,
        )
    else:
        mcp.run()
