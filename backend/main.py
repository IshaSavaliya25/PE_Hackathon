import os
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

from rag_engine import RAGEngine

app = FastAPI(
    title="DocuChat RAG Backend",
    description="FastAPI Backend for Document Q&A with Retrieval-Augmented Generation",
    version="1.0.0"
)

# Enable CORS for Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize RAG Engine singleton
rag = RAGEngine()


# ---------------------------------------------------------
# Request/Response Schemas
# ---------------------------------------------------------
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    query: str
    document_name: Optional[str] = "Uploaded Document"
    history: Optional[List[ChatMessage]] = []

class SourceItem(BaseModel):
    page: int
    snippet: str

class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceItem]


# ---------------------------------------------------------
# Routes
# ---------------------------------------------------------
@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "DocuChat RAG Backend",
        "indexed_documents": list(rag.documents.keys()),
        "gemini_active": rag.gemini_model is not None
    }

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "total_documents_indexed": len(rag.documents),
        "documents": [
            {
                "name": name,
                "total_pages": info["total_pages"],
                "total_chunks": info["total_chunks"]
            }
            for name, info in rag.documents.items()
        ]
    }

@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Receives an uploaded document, parses text, creates chunks, and indexes vectors.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file has no filename.")

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        result = rag.index_document(file.filename, content)
        return result
    except ValueError as val_err:
        raise HTTPException(status_code=422, detail=str(val_err))
    except Exception as err:
        print(f"[API ERROR] Upload failed: {err}")
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(err)}")

@app.post("/api/chat", response_model=ChatResponse)
async def chat_with_document(request: ChatRequest):
    """
    Answers a query using RAG over the specified document.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    history_dicts = [{"role": m.role, "content": m.content} for m in (request.history or [])]
    
    try:
        response_data = rag.generate_answer(
            query=request.query,
            doc_name=request.document_name,
            history=history_dicts
        )
        return response_data
    except Exception as err:
        print(f"[API ERROR] Chat failed: {err}")
        raise HTTPException(status_code=500, detail=f"RAG query generation failed: {str(err)}")
