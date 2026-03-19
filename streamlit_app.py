import streamlit as st
import PyPDF2
import json
import re
import os
import google.generativeai as genai
from pydantic import BaseModel, Field, field_validator
from typing import List
import pandas as pd
from io import BytesIO
from datetime import datetime

# -------------------------------
# SCHEMAS
# -------------------------------
class ExtractedField(BaseModel):
    value: str
    confidence_score: int

    @field_validator('value', mode='before')
    @classmethod
    def sanitize_value(cls, v):
        if v is None or str(v).strip().lower() in ["", "null"]:
            return "Not found in document"
        return str(v)

class RiskItem(BaseModel):
    description: str
    risk_level: str
    is_penalty: bool

class TenderIntelligence(BaseModel):
    submission_deadline: ExtractedField
    emd_amount: ExtractedField
    financial_criteria: ExtractedField
    technical_eligibility: ExtractedField
    scope_summary: ExtractedField
    risk_clauses: List[RiskItem]
    unusual_liabilities: List[str]

# -------------------------------
# CORE FUNCTIONS
# -------------------------------
def extract_and_clean_text(uploaded_file):
    pdf_reader = PyPDF2.PdfReader(uploaded_file)
    text = ""
    for page in pdf_reader.pages:
        raw_text = page.extract_text()
        if raw_text:
            text += re.sub(r'\s+', ' ', raw_text) + "\n"
    return text

def get_gemini_model(api_key):
    genai.configure(api_key=api_key)
    models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    if not models:
        raise ValueError("No models found. Check API Key.")
    target = next((m for m in models if 'flash' in m.lower() or 'pro' in m.lower()), models[0])
    return genai.GenerativeModel(model_name=target, generation_config={"temperature": 0.0})

def clean_json_response(raw_text):
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^
http://googleusercontent.com/immersive_entry_chip/0

Would you like me to help you build out the logic for Tab 3 next, or are you ready to test this current setup?
