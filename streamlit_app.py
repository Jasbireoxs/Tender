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
    target = next((m for m in models if 'flash' in m.lower() or 'pro' in m.lower()), models[0])
    return genai.GenerativeModel(model_name=target, generation_config={"temperature": 0.0})


def clean_json_response(raw_text):
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?|```$", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


# -------------------------------
# KEY FIX FUNCTION
# -------------------------------
def fix_json_keys(data):
    mapping = {
        "submission deadline": "submission_deadline",
        "emd amount": "emd_amount",
        "financial criteria": "financial_criteria",
        "technical eligibility": "technical_eligibility",
        "scope summary": "scope_summary"
    }

    fixed = {}

    for k, v in data.items():
        clean_key = re.sub(r'^\d+\.\s*', '', k.lower().strip())

        if clean_key in mapping:
            fixed[mapping[clean_key]] = v
        else:
            fixed[k] = v

    return fixed


# -------------------------------
# MAIN ANALYSIS
# -------------------------------
def analyze_tender_with_gemini(text, api_key):
    try:
        model = get_gemini_model(api_key)

        prompt = f"""
You are a strict JSON extraction engine.

RULES:
- Output ONLY JSON
- No numbering
- No explanation
- No markdown

If missing → "Not found in document"

FORMAT:
{{
  "submission_deadline": {{"value": "...", "confidence_score": 90}},
  "emd_amount": {{"value": "...", "confidence_score": 90}},
  "financial_criteria": {{"value": "...", "confidence_score": 90}},
  "technical_eligibility": {{"value": "...", "confidence_score": 90}},
  "scope_summary": {{"value": "...", "confidence_score": 90}},
  "risk_clauses": [
    {{"description": "...", "risk_level": "High/Medium/Low", "is_penalty": true}}
  ],
  "unusual_liabilities": ["..."]
}}

TEXT:
{text}
"""

        response = model.generate_content(prompt)

        parsed = json.loads(clean_json_response(response.text))
        parsed = fix_json_keys(parsed)

        # Ensure all fields exist
        required = [
            "submission_deadline", "emd_amount", "financial_criteria",
            "technical_eligibility", "scope_summary",
            "risk_clauses", "unusual_liabilities"
        ]

        for key in required:
            if key not in parsed:
                if key in ["risk_clauses"]:
                    parsed[key] = []
                elif key in ["unusual_liabilities"]:
                    parsed[key] = []
                else:
                    parsed[key] = {"value": "Not found in document", "confidence_score": 0}

        return TenderIntelligence(**parsed)

    except Exception as e:
        st.error(f"Analysis failed: {e}")
        return None


# -------------------------------
# NORMALIZATION
# -------------------------------
def normalize_values(data):
    try:
        price = str(data.get("Price", "")).lower()

        if "lakh" in price:
            num = float(re.findall(r"\d+\.?\d*", price)[0])
            data["Price"] = int(num * 100000)

        elif "₹" in price or "rs" in price:
            nums = re.findall(r"\d+", price.replace(",", ""))
            data["Price"] = int("".join(nums)) if nums else 0

        delivery = str(data.get("DeliveryDays", "")).lower()

        if "week" in delivery:
            nums = re.findall(r"\d+", delivery)
            avg = sum(map(int, nums)) / len(nums)
            data["DeliveryDays"] = int(avg * 7)

        return data
    except:
        return data


# -------------------------------
# UI HELPERS
# -------------------------------
def display_field(label, field):
    color = "green" if field.confidence_score > 60 else "red"
    st.markdown(f"**{label}:** {field.value} (:{color}[Confidence: {field.confidence_score}%])")


def generate_excel(result):
    df = pd.DataFrame({
        "Field": ["Deadline", "EMD", "Financial", "Technical", "Scope"],
        "Value": [
            result.submission_deadline.value,
            result.emd_amount.value,
            result.financial_criteria.value,
            result.technical_eligibility.value,
            result.scope_summary.value
        ]
    })
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()


def check_deadline_reminder(deadline_text):
    try:
        deadline_date = datetime.strptime(deadline_text, "%d %B %Y")
        days = (deadline_date - datetime.today()).days

        if days <= 2:
            st.error("🚨 Deadline near!")
        elif days <= 7:
            st.warning("⚠️ Deadline approaching")
        else:
            st.info(f"{days} days remaining")
    except:
        st.info("Deadline format not recognized")


# -------------------------------
# UI
# -------------------------------
st.set_page_config(page_title="Iron Throne AI", layout="wide")

# HEADER
col1, col2 = st.columns([1, 5])

with col1:
    if os.path.exists("image_6d399e.png"):
        st.image("image_6d399e.png", use_container_width=True)

with col2:
    st.title("Iron Throne AI Control Center")
    st.markdown("AI-powered Operations Dashboard")

st.divider()

# Sidebar
with st.sidebar:
    api_key_input = st.text_input("Gemini API Key", type="password")

# Tabs
tab1, tab2, tab3 = st.tabs(["Tender", "Vendor", "Follow-up"])

# -------------------------------
# TAB 1
# -------------------------------
with tab1:
    file = st.file_uploader("Upload Tender", type="pdf")

    if file and api_key_input:
        if st.button("Analyze Tender"):
            text = extract_and_clean_text(file)
            res = analyze_tender_with_gemini(text, api_key_input)

            if res:
                display_field("Deadline", res.submission_deadline)
                display_field("EMD", res.emd_amount)

                check_deadline_reminder(res.submission_deadline.value)

                st.text_area("Draft", generate_excel(res))


# -------------------------------
# TAB 2
# -------------------------------
with tab2:
    files = st.file_uploader("Upload Quotes", accept_multiple_files=True)

    if files and api_key_input:
        if st.button("Analyze Quotes"):
            model = get_gemini_model(api_key_input)
            vendors = []

            for f in files:
                image_data = {"mime_type": f.type, "data": f.getvalue()}
                res = model.generate_content(["Extract vendor data JSON", image_data])
                data = json.loads(clean_json_response(res.text))
                data = normalize_values(data)
                vendors.append(data)

            df = pd.DataFrame(vendors)
            st.dataframe(df)

# -------------------------------
# TAB 3
# -------------------------------
with tab3:
    st.write("Follow-up system active")
