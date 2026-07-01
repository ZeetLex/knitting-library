"""AI service facade assembled from prompts, OCR, and job modules."""
from app.ai.prompts import *
from app.ai.ocr import *
from app.ai.jobs import *

__all__ = [name for name in globals() if not name.startswith("__")]
