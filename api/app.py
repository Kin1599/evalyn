from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from api.routers import courses, assignments, submissions, reviews

def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    app = FastAPI(
        title="Evalyn API",
        description="Teacher assistant AI for code review",
        version="0.1.0",
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(courses.router, prefix="/api/courses", tags=["courses"])
    app.include_router(assignments.router, prefix="/api/assignments", tags=["assignments"])
    app.include_router(submissions.router, prefix="/api/submissions", tags=["submissions"])
    app.include_router(reviews.router, prefix="/api/reviews", tags=["reviews"])
    
    # Health check endpoint
    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "evalyn-api"}
    
    # Serve static files from frontend/public
    frontend_dir = Path(__file__).parent.parent / "frontend" / "public"
    if frontend_dir.exists():
        app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
    
    # Serve main index.html at root
    @app.get("/")
    async def root():
        index_file = Path(__file__).parent.parent / "frontend" / "public" / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "Evalyn API is running"}
    
    return app


app = create_app()
