import os
import sys
import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"[INFO] Starting DocuChat RAG Backend on http://{host}:{port}")
    uvicorn.run("main:app", host=host, port=port, reload=True)
