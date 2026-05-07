from contextlib import asynccontextmanager

from fastmcp import FastMCP

from persistence.action_log import init_db
from tools.account_tools import account_tools
from tools.data_tools import data_tools
from tools.optimiser_tools import optimiser_tools
from tools.write_tools import write_tools
from tools.report_tools import report_tools


@asynccontextmanager
async def db_lifespan(server):
    init_db()
    yield {}


mcp = FastMCP(
    name="meta-ads-mcp",
    instructions="Meta Ads operations: insights, optimiser, apply changes",
    version="1.0.0",
    lifespan=db_lifespan,
)

mcp.mount(account_tools)
mcp.mount(data_tools)
mcp.mount(optimiser_tools)
mcp.mount(write_tools)
mcp.mount(report_tools)


if __name__ == "__main__":
    import sys
    if "--http" in sys.argv:
        mcp.run(transport="http", host="0.0.0.0", port=8000)
    else:
        mcp.run()
