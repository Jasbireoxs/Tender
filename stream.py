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
    value: str = Field(description="The extracted information or 'Not specified'")
    confidence_score: int = Field(description="Confidence percentage from 0 to 100")

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
    """Safely removes markdown backticks without causing Python Syntax Errors."""
    cleaned = raw_text.strip()
    backticks = chr(96) * 3
    if cleaned.startswith(backticks):
        lines = cleaned.split('\n')
        if lines and lines[0].startswith(backticks):
            lines.pop(0)
        if lines and lines[-1].startswith(backticks):
            lines.pop(-1)
        cleaned = '\n'.join(lines).strip()
    return cleaned

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

def analyze_tender_with_gemini(text, api_key):
    try:
        model = get_gemini_model(api_key)
        
        # Brought back the more detailed, superior prompt
        prompt = f"""
You are an AI Tender Intelligence System for Iron Throne Engineering.

Extract the following from the tender document:
1. Submission deadline (MUST be formatted exactly as DD MMMM YYYY, e.g., 15 October 2026)
2. EMD amount
3. Financial criteria
4. Technical eligibility
5. Scope summary
6. Risk clauses (include risk_level and is_penalty)
7. Unusual liabilities

Return ONLY valid JSON in this format. DO NOT include markdown formatting or backticks.
{{
  "submission_deadline": {{"value": "...", "confidence_score": 90}},
  "emd_amount": {{"value": "...", "confidence_score": 95}},
  "financial_criteria": {{"value": "...", "confidence_score": 85}},
  "technical_eligibility": {{"value": "...", "confidence_score": 80}},
  "scope_summary": {{"value": "...", "confidence_score": 99}},
  "risk_clauses": [
      {{
        "description": "...",
        "risk_level": "High/Medium/Low",
        "is_penalty": true
      }}
  ],
  "unusual_liabilities": ["..."]
}}

Tender Document:
{text}
"""
        response = model.generate_content(prompt)
        parsed = json.loads(clean_json_response(response.text))
        parsed = fix_json_keys(parsed)

        required = [
            "submission_deadline", "emd_amount", "financial_criteria",
            "technical_eligibility", "scope_summary",
            "risk_clauses", "unusual_liabilities"
        ]

        for key in required:
            if key not in parsed:
                if key in ["risk_clauses", "unusual_liabilities"]:
                    parsed[key] = []
                else:
                    parsed[key] = {"value": "Not found in document", "confidence_score": 0}

        return TenderIntelligence(**parsed)

    except Exception as e:
        st.error(f"Analysis failed: {e}")
        return None

def generate_draft_response(tender_data):
    return f"""DRAFT SUBMISSION COVER LETTER

Subject: Submission for Tender - {tender_data.scope_summary.value}

Dear Sir/Madam,

We confirm submission before the deadline of {tender_data.submission_deadline.value}.
We comply with financial criteria: {tender_data.financial_criteria.value}
Technical eligibility met: {tender_data.technical_eligibility.value}
EMD enclosed: {tender_data.emd_amount.value}

We acknowledge all commercial and risk clauses.

Sincerely,
Iron Throne Engineering
"""

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
            if nums:
                avg = sum(map(int, nums)) / len(nums)
                data["DeliveryDays"] = int(avg * 7)

        return data
    except:
        return data

# -------------------------------
# UI HELPERS
# -------------------------------
def display_field(label, field):
    if field.confidence_score < 60:
        st.error(f"{label}: {field.value} (Confidence: {field.confidence_score}%)")
    else:
        st.success(f"{label}: {field.value} (Confidence: {field.confidence_score}%)")

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
        today = datetime.today()
        days_remaining = (deadline_date - today).days

        if days_remaining <= 2:
            st.error(f"🚨 Deadline in {days_remaining} days!")
        elif days_remaining <= 7:
            st.warning(f"⚠️ Deadline in {days_remaining} days.")
        else:
            st.info(f"🗓️ {days_remaining} days remaining.")
    except Exception:
        st.info(f"Could not automatically parse deadline format from: '{deadline_text}'")

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
# TAB 1: TENDER INTELLIGENCE
# -------------------------------
with tab1:
    file = st.file_uploader("Upload Tender", type="pdf")

    if file and api_key_input:
        if st.button("Analyze Tender", type="primary"):
            with st.spinner("Dynamically selecting model and analyzing document..."):
                text = extract_and_clean_text(file)
                st.session_state.tender_result = analyze_tender_with_gemini(text, api_key_input)

        if st.session_state.tender_result:
            result = st.session_state.tender_result
            st.success("Analysis Complete")

            col1, col2 = st.columns(2)

            with col1:
                st.subheader("📌 Key Details")
                display_field("Deadline", result.submission_deadline)
                display_field("EMD", result.emd_amount)
                display_field("Financial Criteria", result.financial_criteria)

            with col2:
                st.subheader("🔍 Technical Overview")
                display_field("Technical Eligibility", result.technical_eligibility)
                display_field("Scope Summary", result.scope_summary)

            st.subheader("⏰ Deadline Reminder")
            check_deadline_reminder(result.submission_deadline.value)

            st.subheader("⚠️ Risk Clauses")
            for risk in result.risk_clauses:
                st.write(f"- {risk.description} | Level: {risk.risk_level} | Penalty: {risk.is_penalty}")

            st.subheader("⚡ Unusual Liabilities")
            for item in result.unusual_liabilities:
                st.write("-", item)

            st.subheader("📝 Draft Cover Letter")
            draft = generate_draft_response(result)
            st.text_area("Generated Draft", draft, height=250)

            col_dl1, col_dl2 = st.columns(2)
            
            with col_dl1:
                result_dict = result.model_dump()
                st.download_button(
                    "📥 Download JSON Report",
                    data=json.dumps(result_dict, indent=2),
                    file_name="tender_analysis.json",
                    mime="application/json"
                )

            with col_dl2:
                excel_file = generate_excel(result)
                st.download_button(
                    "📊 Download Excel Report",
                    data=excel_file,
                    file_name="tender_analysis.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

# -------------------------------
# TAB 2: VENDOR QUOTE COMPARISON
# -------------------------------
with tab2:
    files = st.file_uploader("Upload Quotes", accept_multiple_files=True, type=["png", "jpg", "jpeg"])

    if files and api_key_input:
        if st.button("Analyze Quotes"):
            with st.spinner("Extracting Vision Data..."):
                model = get_gemini_model(api_key_input)
                vendors = []

                vision_prompt = """
                Extract vendor data from this image into strictly valid JSON.
                Use EXACTLY these keys: "Vendor", "Price", "DeliveryDays".
                Do not include markdown formatting or backticks.
                """

                for f in files:
                    image_data = {"mime_type": f.type, "data": f.getvalue()}
                    try:
                        res = model.generate_content([vision_prompt, image_data])
                        data = json.loads(clean_json_response(res.text))
                        data = normalize_values(data)
                        vendors.append(data)
                    except Exception as e:
                        st.error(f"Failed to process {f.name}: {e}")

                if vendors:
                    df = pd.DataFrame(vendors)
                    st.dataframe(df)

# -------------------------------
# TAB 3: FOLLOW UP TRACKER
# -------------------------------
with tab3:
    st.header("Agentic Delivery Follow-up")
    st.markdown("Tracks expected dates and auto-generates context-aware vendor follow-ups.")
    
    # Simulated active database
    orders = [
        {"vendor": "L&T Switchgears", "item": "33kV Transformers", "date": datetime(2026, 3, 20).date()},
        {"vendor": "Polycab Cables", "item": "Armoured Cables", "date": datetime(2026, 3, 28).date()},
        {"vendor": "Local Hardware Supply", "item": "Cement Bags", "date": datetime(2026, 3, 17).date()}
    ]
    
    for o in orders:
        with st.expander(f"{o['vendor']} - {o['item']}"):
            today = datetime.today().date()
            days_remaining = (o['date'] - today).days
            
            st.write(f"**Expected Date:** {o['date']}")
            
            needs_alert = False
            if days_remaining < 0:
                st.error(f"❌ Delayed by {abs(days_remaining)} days.")
                needs_alert = True
            elif days_remaining <= 2:
                st.warning(f"⚠️ Due in {days_remaining} days. Follow-up required.")
                needs_alert = True
            else:
                st.success(f"✅ On track. {days_remaining} days remaining.")
            
            if needs_alert:
                if st.button(f"Generate AI Alert for {o['vendor']}", key=o['vendor']):
                    if not api_key_input:
                        st.warning("Enter API Key to use the Agent.")
                    else:
                        with st.spinner("Agent drafting message..."):
                            model = get_gemini_model(api_key_input)
                            prompt = f"Draft a polite but firm WhatsApp message to {o['vendor']} regarding the delivery of {o['item']} which was expected on {o['date']}. Identify the sender as Iron Throne Engineering. Remind them that site operations depend on this."
                            response = model.generate_content(prompt)
                            st.text_area("WhatsApp Draft (Ready to Send):", response.text, height=150)
