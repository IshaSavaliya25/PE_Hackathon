# Frontend - Streamlit Document Q&A Chatbot

This is the Streamlit frontend for the Document Q&A Chatbot.

## Features

1. **Document Upload**:
   - Accepts `.pdf`, `.docx`, `.txt`, `.csv`, `.md`.
   - Displays file metadata (name, size, type).
   - "Process & Set Active" button sends file to backend or sets up mock simulation.
   - Detach/attach documents per session.

2. **Full Conversation & History Management**:
   - Multiple session support (Create new sessions with `➕`).
   - Switch between past conversations.
   - Clear chat button.
   - Export chat history as JSON.
   - Source citations & page references dropdown for answers.

3. **Backend Integration / Mock Toggle**:
   - Sidebar contains **"Backend Configuration"** with a **"Mock / Standalone Mode"** switch.
   - When **Mock Mode** is ON, the app simulates document-aware answers (great for testing UI right away).
   - When **Mock Mode** is OFF, it sends requests to your friend's backend at the configured base URL (default `http://localhost:8000`).

---

## Backend API Specification (For your friend)

Your friend can implement their backend (e.g., using FastAPI or Flask) with these two simple endpoints:

### 1. Document Upload
- **Method**: `POST`
- **Path**: `/api/upload`
- **Content-Type**: `multipart/form-data`
- **Form Data**:
  - `file`: The uploaded document file
- **Expected JSON Response**:
  ```json
  {
    "status": "success",
    "document_id": "doc_12345",
    "filename": "annual_report.pdf",
    "total_pages": 12
  }
  ```

### 2. Chat / Query
- **Method**: `POST`
- **Path**: `/api/chat`
- **Content-Type**: `application/json`
- **Request Body**:
  ```json
  {
    "query": "What are the main risks mentioned?",
    "document_name": "annual_report.pdf",
    "history": [
      {"role": "user", "content": "Hello"},
      {"role": "assistant", "content": "Hi! Upload a document to start."}
    ]
  }
  ```
- **Expected JSON Response**:
  ```json
  {
    "answer": "The main risks identified in the document include market volatility and supply chain disruption.",
    "sources": [
      {
        "page": 4,
        "snippet": "Section 3.2 outlines potential market volatility impacting Q3 performance."
      }
    ]
  }
  ```

---

## Running the Frontend

To start or restart the frontend:
```powershell
cd frontend
.\venv\Scripts\Activate.ps1
streamlit run app.py
```
