from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import sys
import os

# Add the root project directory to the path so we can import compiler modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compiler import compile_html, resolve_relative_urls, process_json_assets

app = FastAPI(title="Elementor Conversion Engine API")

# Configure CORS for local development & Vercel domains
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "service": "elementor-conversion-engine"}

from fastapi.staticfiles import StaticFiles

@app.post("/api/compile")
async def compile_endpoint(
    html_file: UploadFile = File(None),
    html_text: str = Form(None),
    base_asset_url: str = Form(None),
    wp_url: str = Form(None),
    wp_user: str = Form(None),
    wp_pass: str = Form(None)
):
    content = ""
    if html_file:
        content_bytes = await html_file.read()
        content = content_bytes.decode("utf-8", errors="ignore")
    elif html_text:
        content = html_text
    else:
        raise HTTPException(status_code=400, detail="Please provide either an uploaded HTML file or raw HTML text.")

    try:
        # Perform compilation
        template = compile_html(content)

        # Upload assets if WP credentials are provided
        if wp_url and wp_user and wp_pass:
            process_json_assets(template, wp_url, wp_user, wp_pass, base_dir="")

        # Prepend base asset URL if provided
        if base_asset_url:
            resolve_relative_urls(template, base_asset_url)

        return template
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Compilation error: {str(e)}")

# Mount static files to serve the frontend UI
app.mount("/", StaticFiles(directory="public", html=True), name="static")
