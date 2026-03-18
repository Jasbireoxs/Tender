import streamlit as st
import PyPDF2
import json
import re
import os
import google.generativeai as genai
from pydantic import BaseModel, Field
from typing import List
import pandas as pd
from io import BytesIO
from datetime import datetime

# -------------------------------
# 1️⃣ PYDANTIC SCHEMAS
# -------------------------------
class ExtractedField(BaseModel):
    value: str = Field(description="The extracted information")
    confidence_score: int = Field(description="Confidence percentage 0-100")

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
    return genai.GenerativeModel(target)

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
        You are an AI Tender Intelligence System for Iron Throne Engineering. Extract the following from the document:
        1. Submission deadline (Format: DD MMMM YYYY)
        2. EMD amount
        3. Financial criteria
        4. Technical eligibility
        5. Scope summary
        6. Risk clauses (with risk_level and is_penalty)
        7. Unusual liabilities

        Return ONLY valid JSON:
        {{
          "submission_deadline": {{"value": "...", "confidence_score": 90}},
          "emd_amount": {{"value": "...", "confidence_score": 95}},
          "financial_criteria": {{"value": "...", "confidence_score": 85}},
          "technical_eligibility": {{"value": "...", "confidence_score": 80}},
          "scope_summary": {{"value": "...", "confidence_score": 99}},
          "risk_clauses": [{{ "description": "...", "risk_level": "High/Medium/Low", "is_penalty": true }}],
          "unusual_liabilities": ["..."]
        }}
        Text: {text}
        """
        response = model.generate_content(prompt)
        clean_json_str = clean_json_response(response.text)
        parsed_json = json.loads(clean_json_str)
        return TenderIntelligence(**parsed_json)
    except Exception as e:
        st.error(f"Analysis failed: {e}")
        return None

def generate_draft_response(tender_data):
    return f"""DRAFT SUBMISSION COVER LETTER\n\nSubject: Submission for Tender - {tender_data.scope_summary.value}\n\nDear Sir/Madam,\n\nWe, Iron Throne Engineering, confirm submission before the deadline of {tender_data.submission_deadline.value}.\nWe comply with financial criteria ({tender_data.financial_criteria.value}) and technical eligibility ({tender_data.technical_eligibility.value}).\nEMD of {tender_data.emd_amount.value} is enclosed.\n\nWe acknowledge all commercial and risk clauses and look forward to executing this project successfully.\n\nSincerely,\nIron Throne Engineering"""

def display_field(label, field):
    color = "green" if field.confidence_score > 60 else "red"
    st.markdown(f"**{label}:** {field.value} (:{color}[Confidence: {field.confidence_score}%])")

def generate_excel(result):
    df = pd.DataFrame({
        "Field": ["Deadline", "EMD", "Financial", "Technical", "Scope"],
        "Value": [result.submission_deadline.value, result.emd_amount.value, result.financial_criteria.value, result.technical_eligibility.value, result.scope_summary.value]
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
    except Exception:
        st.info(f"Could not parse deadline format: '{deadline_text}'")# -------------------------------
# 3️⃣ STREAMLIT UI SETUP
# -------------------------------
st.set_page_config(page_title="Iron Throne AI Control", layout="wide")

if "tender_result" not in st.session_state:
    st.session_state.tender_result = None

with st.sidebar:
    if os.path.exists("image_6d399e.png"):
        st.image("image_6d399e.png", use_container_width=True)
    else:
        st.header("⚙️ Iron Throne Engineering")
    st.divider()
    st.header("System Config")
    api_key_input = st.text_input("Gemini API Key", type="password")

st.title("🚀 Iron Throne AI Control Center")
st.markdown("Unified dashboard for Tender Analysis, Vendor Comparison & Operational Tracking")

tab1, tab2, tab3 = st.tabs(["📄 Tender Intelligence", "📊 Vendor Comparison", "⏰ Follow-up Tracker"])

# --- TAB 1: TENDER INTELLIGENCE ---
with tab1:
    st.header("Tender Intelligence System")
    uploaded_file = st.file_uploader("Upload Tender PDF", type="pdf")
    
    if uploaded_file and api_key_input:
        if st.button("Analyze Tender", type="primary"):
            with st.spinner("Processing Document..."):
                text = extract_and_clean_text(uploaded_file)
                st.session_state.tender_result = analyze_tender_with_gemini(text, api_key_input)
        
        if st.session_state.tender_result:
            res = st.session_state.tender_result
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("📌 Key Details")
                display_field("Deadline", res.submission_deadline)
                display_field("EMD", res.emd_amount)
            with c2:
                st.subheader("🔍 Technical Overview")
                display_field("Financial", res.financial_criteria)
                display_field("Scope", res.scope_summary)
            
            st.subheader("⏰ Deadline Reminder")
            check_deadline_reminder(res.submission_deadline.value)

            st.subheader("⚠️ Risk Intelligence")
            for r in res.risk_clauses:
                if r.risk_level == "High":
                    st.error(f"🚨 {r.risk_level} RISK: {r.description}")
                else:
                    st.warning(f"⚠️ {r.risk_level} RISK: {r.description}")
            
            st.subheader("📝 Draft Submission Letter")
            st.text_area("Generated Draft", generate_draft_response(res), height=200)
            
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                st.download_button("📥 Download JSON", data=json.dumps(res.model_dump(), indent=2), file_name="IronThrone_Tender.json")
            with col_dl2:
                st.download_button("📊 Download Excel", data=generate_excel(res), file_name="IronThrone_Tender.xlsx")

# --- TAB 2: VENDOR QUOTE COMPARISON ---
with tab2:
    st.header("AI Quotation Comparison")
    st.markdown("Upload vendor quotation images. Vision AI will extract and compare terms.")
    quote_files = st.file_uploader("Upload Quotes (Images)", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    
    if quote_files and api_key_input:
        if st.button("Extract & Compare Quotes", type="primary"):
            with st.spinner("Vision AI Analyzing Images..."):
                model = get_gemini_model(api_key_input)
                extracted_vendors = []
                
                for file in quote_files:
                    image_data = {"mime_type": file.type, "data": file.getvalue()}
                    prompt = """
                    Extract the following from this quotation image and return strictly valid JSON. Do NOT include currency symbols in numbers.
                    {
                        "Vendor": "Name of company",
                        "Price": Numeric value only,
                        "DeliveryDays": Numeric value only (estimate if necessary),
                        "CreditDays": Numeric value only
                    }
                    """
                    try:
                        response = model.generate_content([prompt, image_data])
                        clean_json_str = clean_json_response(response.text)
                        data = json.loads(clean_json_str)
                        extracted_vendors.append(data)
                    except Exception as e:
                        st.error(f"Failed to read {file.name}. Ensure the image is clear. Error: {e}")
                
                if extracted_vendors:
                    df = pd.DataFrame(extracted_vendors)
                    st.subheader("📊 Iron Throne AI Comparison Table")
                    st.dataframe(df, use_container_width=True)
                    
                    best_price = df.loc[df["Price"].idxmin()]
                    fastest = df.loc[df["DeliveryDays"].idxmin()]
                    
                    st.success(f"🏆 Lowest Price: **{best_price['Vendor']}** (₹{best_price['Price']})")
                    st.info(f"⚡ Fastest Delivery: **{fastest['Vendor']}** ({fastest['DeliveryDays']} days)")

# --- TAB 3: AGENTIC FOLLOW-UP TRACKER ---
with tab3:
    st.header("Agentic Delivery Follow-up")
    st.markdown("Tracks expected dates and auto-generates context-aware vendor follow-ups.")
    
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
