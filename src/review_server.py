import os
import sys
import yaml
import signal
import argparse
import uvicorn
import asyncio
import webbrowser
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import List

import subprocess

app = FastAPI(title="Novel Review Editor")

# Global variables to store paths
NOVEL_PATH = ""
YAML_PATH = ""

class FindingItem(BaseModel):
    id: str
    location: str
    original: str
    category: str
    severity: str
    analysis: str
    suggestion: str
    accepted: str

class SaveFindingsRequest(BaseModel):
    findings: List[FindingItem]

def get_template_path():
    """Locates the templates/index.html file."""
    # Try local dev template location
    template_path = Path(__file__).parent / "templates" / "index.html"
    return template_path

@app.get("/", response_class=HTMLResponse)
async def get_index():
    template = get_template_path()
    if not template.exists():
        raise HTTPException(status_code=404, detail=f"Template not found at {template}")
    with open(template, 'r', encoding='utf-8') as f:
        return f.read()

@app.get("/api/data")
async def get_data():
    global NOVEL_PATH, YAML_PATH
    if not os.path.exists(NOVEL_PATH) or not os.path.exists(YAML_PATH):
        raise HTTPException(status_code=404, detail="Novel or YAML file not found.")

    # Read novel lines
    with open(NOVEL_PATH, 'r', encoding='utf-8') as f:
        novel_lines = [line.rstrip('\r\n') for line in f.readlines()]

    # Read findings YAML
    with open(YAML_PATH, 'r', encoding='utf-8') as f:
        try:
            data = yaml.safe_load(f) or {}
            findings = data.get('findings', [])
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse YAML: {str(e)}")

    return JSONResponse(content={
        "novel_lines": novel_lines,
        "findings": findings,
        "novel_filename": os.path.basename(NOVEL_PATH)
    })

@app.post("/api/save")
async def save_findings(payload: SaveFindingsRequest):
    global YAML_PATH
    try:
        findings_list = [item.model_dump() for item in payload.findings]
        
        # Write back to YAML
        with open(YAML_PATH, 'w', encoding='utf-8') as f:
            yaml.dump({"findings": findings_list}, f, allow_unicode=True, default_flow_style=False)
            
        return {"status": "success", "message": "Saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save YAML: {str(e)}")

def shutdown_server():
    print("[INFO] Shutting down Review Editor server...")
    os.kill(os.getpid(), signal.SIGINT)

@app.post("/api/apply")
async def apply_changes_and_shutdown(background_tasks: BackgroundTasks):
    global NOVEL_PATH, YAML_PATH
    try:
        # Apply accepted changes using the existing apply_findings.py script
        parent_dir = os.path.dirname(NOVEL_PATH)
        script_path = os.path.join(os.path.dirname(__file__), "apply_findings.py")
        cmd = ["poetry", "run", "python", script_path, "--dir", parent_dir, "--auto"]
        
        print(f"[INFO] Running apply process: {' '.join(cmd)}")
        res = subprocess.run(cmd, capture_output=True, text=True)
        
        if res.returncode != 0:
            print(f"[ERROR] apply_findings.py failed: {res.stderr}")
            raise HTTPException(status_code=500, detail=f"Failed to apply findings: {res.stderr}")
            
        print(f"[INFO] Apply output:\n{res.stdout}")
        
        # Trigger server shutdown
        background_tasks.add_task(shutdown_server)
        return {"status": "success", "message": "Applied successfully. Shutting down server..."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error applying changes: {str(e)}")

@app.post("/api/shutdown")
async def shutdown(background_tasks: BackgroundTasks):
    background_tasks.add_task(shutdown_server)
    return {"status": "success", "message": "Shutting down..."}

async def open_browser():
    await asyncio.sleep(1) # wait for server to start
    webbrowser.open("http://localhost:8000")

def main():
    parser = argparse.ArgumentParser(description="Start the Interactive Novel Review Server.")
    parser.add_argument("novel_path", help="Path to the novel txt file.")
    parser.add_argument("yaml_path", help="Path to the integrated findings YAML file.")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the server on.")
    args = parser.parse_args()

    global NOVEL_PATH, YAML_PATH
    NOVEL_PATH = os.path.abspath(args.novel_path)
    YAML_PATH = os.path.abspath(args.yaml_path)

    print(f"=== Novel Review Editor Server ===")
    print(f"Novel: {NOVEL_PATH}")
    print(f"YAML : {YAML_PATH}")
    print(f"URL  : http://localhost:{args.port}\n")

    # Start browser auto-opener
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(open_browser())

    # Start uvicorn
    # Use log_config to silence standard startup logs a bit, or keep standard logs
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")

if __name__ == '__main__':
    main()
