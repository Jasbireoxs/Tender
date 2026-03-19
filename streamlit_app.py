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
    if not models:
        raise ValueError("No models found. Check API Key.")
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
You are an AI Tender Intelligence System.

Extract:
1. Submission deadline (DD MMMM YYYY)
2. EMD amount
3. Financial criteria
4. Technical eligibility
5. Scope summary
6. Risk clauses
7. Unusual liabilities

If missing, return "Not found in document".

Return valid JSON only.

Text:
{text}
"""
        response = model.generate_content(prompt)
        parsed_json = json.loads(clean_json_response(response.text))
        return TenderIntelligence(**parsed_json)
    except Exception as e:
        st.error(f"Analysis failed: {e}")
        return None


def generate_draft_response(tender_data):
    return f"""
DRAFT SUBMISSION COVER LETTER

Subject: Submission for Tender - {tender_data.scope_summary.value}

Dear Sir/Madam,

We confirm submission before {tender_data.submission_deadline.value}.
We meet financial criteria: {tender_data.financial_criteria.value}
Technical eligibility: {tender_data.technical_eligibility.value}
EMD enclosed: {tender_data.emd_amount.value}

Sincerely,
Iron Throne Engineering
"""


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
# UI
# -------------------------------
st.set_page_config(page_title="Iron Throne AI Control", layout="wide")

if "tender_result" not in st.session_state:
    st.session_state.tender_result = None

# HEADER
col1, col2 = st.columns([1, 5])

with col1:
    if os.path.exists("image_6d399e.png"):
        st.image("image_6d399e.png", use_container_width=True)

with col2:
    st.title("Iron Throne AI Control Center")
    st.markdown("Unified dashboard for Tender Analysis, Vendor Comparison & Operations")

st.info("⚡ AI-powered automation across documents, vendors, and workflows")
st.divider()

# Sidebar
with st.sidebar:
    api_key_input = st.text_input("Gemini API Key", type="password")

# Tabs
tab1, tab2, tab3 = st.tabs(["📄 Tender", "📊 Vendor", "⏰ Follow-up"])

# -------------------------------
# TAB 1: TENDER
# -------------------------------
with tab1:
    uploaded_file = st.file_uploader("Upload Tender PDF", type="pdf")

    if uploaded_file and api_key_input:
        if st.button("Analyze Tender"):
            text = extract_and_clean_text(uploaded_file)
            st.session_state.tender_result = analyze_tender_with_gemini(text, api_key_input)

        if st.session_state.tender_result:
            res = st.session_state.tender_result

            c1, c2 = st.columns(2)

            with c1:
                display_field("Deadline", res.submission_deadline)
                display_field("EMD", res.emd_amount)

            with c2:
                display_field("Financial", res.financial_criteria)
                display_field("Technical", res.technical_eligibility)

            check_deadline_reminder(res.submission_deadline.value)

            # Missing warning
            if res.submission_deadline.value.lower() == "not found in document":
                st.warning("⚠️ Deadline missing - manual review needed")

            # Risk
            st.subheader("⚠️ Risk Analysis")
            risk_levels = []

            for r in res.risk_clauses:
                risk_levels.append(r.risk_level)
                if r.risk_level == "High":
                    st.error(r.description)
                else:
                    st.warning(r.description)

            if "High" in risk_levels:
                st.error("🚨 Overall Risk: HIGH")
            elif "Medium" in risk_levels:
                st.warning("⚠️ Overall Risk: MEDIUM")
            else:
                st.success("✅ Overall Risk: LOW")

            # Draft
            st.text_area("Draft", generate_draft_response(res), height=200)

            # Downloads
            col1, col2 = st.columns(2)
            with col1:
                st.download_button("Download JSON", data=json.dumps(res.model_dump(), indent=2))
            with col2:
                st.download_button("Download Excel", data=generate_excel(res))

# -------------------------------
# TAB 2: VENDOR
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

            best = df.loc[df["Price"].idxmin()]
            st.success(f"🏆 Best Vendor: {best['Vendor']}")

# -------------------------------
# TAB 3: FOLLOW-UP
# -------------------------------
with tab3:
    st.header("Follow-up System")

    vendor = "L&T"
    item = "Transformer"
    date = datetime(2026, 3, 20).date()

    days = (date - datetime.today().date()).days

    if days <= 2:
        st.warning("Follow-up required")

        if st.button("Generate Message"):
            model = get_gemini_model(api_key_input)
            msg = model.generate_content(
                f"Write a professional WhatsApp message to {vendor} about delay in {item} impacting project timelines."
            )
            st.text_area("Message", msg.text)
