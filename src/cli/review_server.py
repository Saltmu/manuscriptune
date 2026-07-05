import argparse
import asyncio
import os
import webbrowser
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from src.routes.api import router as api_router
from src.routes.deps import verify_local_origin
from src.utils import project_paths
from src.utils.logger import get_logger

logger = get_logger("review_server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Manuscriptune Server is starting up.")
    yield
    logger.info("Manuscriptune Server is shutting down.")


app = FastAPI(title="Manuscriptune - AI Writing & Review Portal", lifespan=lifespan)


# Middleware to disable caching for static files to prevent stale browser cache
@app.middleware("http")
async def disable_static_cache(request: Request, call_next):
    response: Response = await call_next(request)
    if request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = (
            "no-store, no-cache, must-revalidate, max-age=0"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# Mount Vite assets directory if it exists
assets_dir = os.path.join(project_paths.PROJECT_ROOT, "frontend/dist/assets")
os.makedirs(assets_dir, exist_ok=True)
app.mount(
    "/assets",
    StaticFiles(directory=assets_dir),
    name="assets",
)

# Include the API routes
app.include_router(api_router, dependencies=[Depends(verify_local_origin)])


async def open_browser(port: int) -> None:
    await asyncio.sleep(1)  # wait for server to start
    webbrowser.open(f"http://localhost:{port}")


def main():
    parser = argparse.ArgumentParser(
        description="Start the Interactive Manuscriptune Server."
    )
    parser.add_argument(
        "--novel", default=None, help="Initial path to the novel txt file."
    )
    parser.add_argument(
        "--yaml",
        default=None,
        help="Initial path to the integrated findings YAML file.",
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port to run the server on."
    )
    args = parser.parse_args()

    # Store initial novel name in app state for access in routes
    initial_novel = ""
    if args.novel:
        initial_novel = os.path.basename(args.novel)
    app.state.initial_novel = initial_novel

    logger.info("=== Manuscriptune Server Running ===")
    if initial_novel:
        logger.info(f"Initial Novel: {initial_novel}")
    logger.info(f"URL  : http://localhost:{args.port}")

    # Start browser auto-opener
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(open_browser(args.port))

    # Start uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
