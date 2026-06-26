import argparse
import asyncio
import os
import webbrowser

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.routes.api import router as api_router

app = FastAPI(title="Novel Studio - AI Writing & Review Portal")

# Mount static directory for CSS/JS
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")),
    name="static",
)

# Include the API routes
app.include_router(api_router)


async def open_browser(port: int):
    await asyncio.sleep(1)  # wait for server to start
    webbrowser.open(f"http://localhost:{port}")


def main():
    parser = argparse.ArgumentParser(
        description="Start the Interactive Novel Studio Server."
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

    print("=== Novel Studio Server Running ===")
    if initial_novel:
        print(f"Initial Novel: {initial_novel}")
    print(f"URL  : http://localhost:{args.port}\n")

    # Start browser auto-opener
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(open_browser(args.port))

    # Start uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
