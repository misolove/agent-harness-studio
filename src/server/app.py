from .main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.server.app:app", host="0.0.0.0", port=8766, reload=True)
