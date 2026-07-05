import sys
from pathlib import Path

# Ensure repo root is importable
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

import os
import shutil
import tempfile
from typing import List, Dict, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Import core modules
from core.io import load_text_from_file, process_file
from core.summarize import summarize_text
from core.quiz_gen import generate_questions
from core.export_pdf import export_summary_to_pdf, export_quiz_to_pdf

try:
    from config import OUTPUT_DIR
except ImportError:
    OUTPUT_DIR = "output"

app = FastAPI(title="StudySage AI Note Assistant API", version="1.0.0")

# Enable CORS for React frontend (development & production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Output directory configuration
OUTPUT_PATH = Path(OUTPUT_DIR)
OUTPUT_PATH.mkdir(exist_ok=True)


# --- Request Models ---
class SummarizeRequest(BaseModel):
    text: str
    mode: str = "offline"
    api_key: Optional[str] = ""
    min_length: int = 30
    max_length: int = 150

class QuizRequest(BaseModel):
    text: str
    num_questions: int = 5

class ExportSummaryRequest(BaseModel):
    summary: str
    theme: str = "light"

class ExportQuizRequest(BaseModel):
    questions: List[Dict[str, object]]
    theme: str = "light"


# --- Endpoints ---

@app.get("/")
def read_root():
    return {"status": "running", "service": "StudySage API"}

@app.post("/api/ocr")
async def run_ocr(file: UploadFile = File(...), lang: str = Form("auto")):
    """Uploads an image or PDF, preprocesses it, and runs OCR to extract text."""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}:
        raise HTTPException(status_code=400, detail=f"Unsupported file format: {suffix}")

    # Save to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        try:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

    try:
        # Load and OCR the file
        extracted_text = load_text_from_file(tmp_path, lang=lang, force_ocr=False)
        return {
            "filename": file.filename,
            "char_count": len(extracted_text),
            "word_count": len(extracted_text.split()),
            "text": extracted_text
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")
    finally:
        # Cleanup
        try:
            os.unlink(tmp_path)
        except:
            pass

@app.post("/api/summarize")
def run_summarize(req: SummarizeRequest):
    """Generates a summary for a given block of text using offline or online modes."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")
    
    try:
        config = {"mode": req.mode, "api_key": req.api_key or ""}
        summary = summarize_text(
            req.text, 
            min_length=req.min_length, 
            max_length=req.max_length, 
            config=config
        )
        return {
            "summary": summary,
            "word_count": len(summary.split()),
            "char_count": len(summary)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summarization failed: {str(e)}")

@app.post("/api/quiz")
def run_quiz(req: QuizRequest):
    """Generates Multiple-Choice Questions (MCQs) from summary text using NLTK."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")
    
    try:
        questions = generate_questions(req.text, num_questions=req.num_questions)
        return {
            "question_count": len(questions),
            "questions": questions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quiz generation failed: {str(e)}")

@app.post("/api/export-summary")
def export_summary(req: ExportSummaryRequest):
    """Generates a summary PDF report and returns it as a file download stream."""
    if not req.summary.strip():
        raise HTTPException(status_code=400, detail="Summary content cannot be empty.")
    
    try:
        pdf_path = export_summary_to_pdf(req.summary, theme=req.theme)
        return FileResponse(
            pdf_path, 
            media_type="application/pdf", 
            filename="studysage_summary.pdf"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF export failed: {str(e)}")

@app.post("/api/export-quiz")
def export_quiz(req: ExportQuizRequest):
    """Generates a quiz PDF report and returns it as a file download stream."""
    if not req.questions:
        raise HTTPException(status_code=400, detail="Questions list cannot be empty.")
    
    try:
        pdf_path = export_quiz_to_pdf(req.questions, theme=req.theme)
        return FileResponse(
            pdf_path, 
            media_type="application/pdf", 
            filename="studysage_quiz.pdf"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF export failed: {str(e)}")


# Mount static files of the React build if it has been built
from fastapi.staticfiles import StaticFiles

WEB_APP_DIST = ROOT / "apps" / "web_app" / "dist"
if WEB_APP_DIST.exists():
    app.mount("/", StaticFiles(directory=str(WEB_APP_DIST), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    # Start the server on port 8000
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
