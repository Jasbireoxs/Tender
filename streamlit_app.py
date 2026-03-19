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
# 1️⃣ SCHEMAS
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
# 2️⃣ CORE FUNCTIONS
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
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("\n", 1)[0]
    return cleaned.strip()


def analyze_tender_with_gemini(text, api_key):
    try:
        model = get_gemini_model(api_key)
        prompt = f"""
        Extract tender details. If not found, return "Not found in document".

        Return JSON:
        {{
          "submission_deadline": {{"value": "...", "confidence_score": 90}},
          "emd_amount": {{"value": "...", "confidence_score": 90}},
          "financial_criteria": {{"value": "...", "confidence_score": 90}},
          "technical_eligibility": {{"value": "...", "confidence_score": 90}},
          "scope_summary": {{"value": "...", "confidence_score": 90}},
          "risk_clauses": [{{"description": "...", "risk_level": "High/Medium/Low", "is_penalty": true}}],
          "unusual_liabilities": ["..."]
        }}

        Text: {text}
        """
        response = model.generate_content(prompt)
        parsed = json.loads(clean_json_response(response.text))
        return TenderIntelligence(**parsed)
    except Exception as e:
        st.error(f"Analysis failed: {e}")
        return None


# -------------------------------
# NORMALIZATION FUNCTION
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


def check_deadline_reminder(deadline_text):
    try:
        deadline_date = datetime.strptime(deadline_text, "%d %B %Y")
        days_remaining = (deadline_date - datetime.today()).days

        if days_remaining <= 2:
            st.error(f"🚨 Deadline in {days_remaining} days!")
        elif days_remaining <= 7:
            st.warning(f"⚠️ Deadline in {days_remaining} days.")
        else:
            st.info(f"🗓️ {days_remaining} days remaining.")
    except:
        st.info(f"Could not parse deadline: '{deadline_text}'")


# -------------------------------
# STREAMLIT UI
# -------------------------------
st.set_page_config(page_title="Iron Throne AI Control", layout="wide")

if "tender_result" not in st.session_state:
    st.session_state.tender_result = None

# -------------------------------
# HEADER (LOGO RESTORED)
# -------------------------------
header_col1, header_col2 = st.columns([1, 5])

with header_col1:
    if os.path.exists("image_6d399e.png"):
        st.image("image_6d399e.png", use_container_width=True)
    else:
        st.markdown("### ⚙️")

with header_col2:
    st.title("Iron Throne AI Control Center")
    st.markdown("Unified dashboard for Tender Analysis, Vendor Comparison & Operational Tracking")

st.info("⚡ Combines Document AI, Vision AI & Agentic Automation")
st.divider()

# Sidebar
with st.sidebar:
    st.header("⚙️ System Config")
    api_key_input = st.text_input("Gemini API Key", type="password")

# Tabs
tab1, tab2, tab3 = st.tabs(["📄 Tender Intelligence", "📊 Vendor Comparison", "⏰ Follow-up Tracker"])

# -------------------------------
# TAB 1: TENDER
# -------------------------------
with tab1:
    file = st.file_uploader("Upload Tender PDF", type="pdf")

    if file and api_key_input:
        if st.button("Analyze Tender"):
            text = extract_and_clean_text(file)
            res = analyze_tender_with_gemini(text, api_key_input)

            if res:
                display_field("Deadline", res.submission_deadline)

                if res.submission_deadline.value.lower() == "not found in document":
                    st.warning("⚠️ Critical Info Missing: Deadline not found.")

                check_deadline_reminder(res.submission_deadline.value)

                risk_levels = [r.risk_level for r in res.risk_clauses]

                for r in res.risk_clauses:
                    if r.risk_level == "High":
                        st.error(r.description)
                    else:
                        st.warning(r.description)

                if "High" in risk_levels:
                    st.error("🚨 Overall Risk: HIGH")
                elif "Medium" in risk_levels:
                    st.warning("⚠️ Overall Risk: MEDIUM")

# -------------------------------
# TAB 2: VENDOR
# -------------------------------
with tab2:
    files = st.file_uploader("Upload Vendor Quotes", accept_multiple_files=True)

    if files and api_key_input:
        if st.button("Analyze Quotes"):
            model = get_gemini_model(api_key_input)
            vendors = []

            for f in files:
                image_data = {"mime_type": f.type, "data": f.getvalue()}
                prompt = """
                Extract:
                {
                    "Vendor": "",
                    "Price": "",
                    "DeliveryDays": "",
                    "CreditDays": ""
                }
                """
                res = model.generate_content([prompt, image_data])
                data = json.loads(clean_json_response(res.text))
                data = normalize_values(data)
                vendors.append(data)

            df = pd.DataFrame(vendors)
            st.dataframe(df)

            best = df.loc[df["Price"].idxmin()]
            st.success(f"🏆 Recommended Vendor: {best['Vendor']}")

# -------------------------------
# TAB 3: FOLLOW-UP
# -------------------------------
with tab3:
    st.header("Delivery Monitoring")

    vendor = "L&T"
    item = "Transformer"
    date = datetime(2026, 3, 20).date()

    days = (date - datetime.today().date()).days

    if days <= 2:
        st.warning("⚠️ Follow-up required")

        if st.button("Generate AI Message"):
            model = get_gemini_model(api_key_input)
            msg = model.generate_content(
                f"Write a professional WhatsApp message to {vendor} about delay in {item}. Mention project impact."
            )
            st.text_area("Generated Message", msg.text)
