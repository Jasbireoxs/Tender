import streamlit as st
import PyPDF2
import json
import re
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
    value: str = Field(description="The extracted information or 'Not specified'")
    confidence_score: int = Field(description="Confidence percentage from 0 to 100")

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
            cleaned_text = re.sub(r'\s+', ' ', raw_text)
            text += cleaned_text + "\n"
    return text

def analyze_tender_with_gemini(text, api_key):
    genai.configure(api_key=api_key)
    
    # --- DYNAMIC MODEL SELECTOR ---
    # This searches your specific API key for authorized text models
    available_models = [
        m.name for m in genai.list_models() 
        if 'generateContent' in m.supported_generation_methods
    ]
    
    if not available_models:
        raise ValueError("Your API key does not have access to any text models. Please check Google AI Studio.")

    # Try to find a fast 'flash' or 'pro' model, otherwise default to the first available
    target_model_name = available_models[0]
    for m in available_models:
        if 'flash' in m.lower() or 'pro' in m.lower():
            target_model_name = m
            break
            
    # Initialize the dynamically found model
    model = genai.GenerativeModel(target_model_name)

    prompt = f"""
You are an AI Tender Intelligence System.

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
    
    try:
        # Regex cleaner: Strips markdown codeblocks if the AI hallucinates them
        raw_response = response.text.strip()
        if raw_response.startswith("```"):
            raw_response = re.sub(r"^```(?:json)?|```$", "", raw_response, flags=re.IGNORECASE | re.MULTILINE).strip()

        parsed_json = json.loads(raw_response)
        validated = TenderIntelligence(**parsed_json)
        return validated
    except Exception as e:
        st.error(f"❌ Error parsing Gemini response using model {target_model_name}: {e}")
        with st.expander("View Raw AI Output for Debugging"):
            st.write(response.text)
        return None

def generate_draft_response(tender_data: TenderIntelligence):
    return f"""DRAFT SUBMISSION COVER LETTER

Subject: Submission for Tender - {tender_data.scope_summary.value}

Dear Sir/Madam,

We confirm submission before the deadline of {tender_data.submission_deadline.value}.
We comply with financial criteria: {tender_data.financial_criteria.value}
Technical eligibility met: {tender_data.technical_eligibility.value}
EMD enclosed: {tender_data.emd_amount.value}

We acknowledge all commercial and risk clauses.

Sincerely,
[Your Company Name]
"""

def display_field(label, field):
    if field.confidence_score < 60:
        st.error(f"{label}: {field.value} (Confidence: {field.confidence_score}%)")
    else:
        st.success(f"{label}: {field.value} (Confidence: {field.confidence_score}%)")

def generate_excel(result):
    data = {
        "Field": ["Submission Deadline", "EMD Amount", "Financial Criteria", "Technical Eligibility", "Scope Summary"],
        "Value": [
            result.submission_deadline.value, result.emd_amount.value,
            result.financial_criteria.value, result.technical_eligibility.value,
            result.scope_summary.value
        ],
        "Confidence Score": [
            result.submission_deadline.confidence_score, result.emd_amount.confidence_score,
            result.financial_criteria.confidence_score, result.technical_eligibility.confidence_score,
            result.scope_summary.confidence_score
        ]
    }
    df = pd.DataFrame(data)
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
# 3️⃣ STREAMLIT UI
# -------------------------------
st.set_page_config(page_title="AI Tender Intelligence System", layout="wide")

if "tender_result" not in st.session_state:
    st.session_state.tender_result = None

with st.sidebar:
    st.header("⚙️ Configuration")
    api_key_input = st.text_input("Enter Google Gemini API Key", type="password")
    st.markdown("Get API key from Google AI Studio")

st.title("📄 AI Tender Intelligence System")
st.markdown("Automated clause extraction, risk intelligence & operational alerts")

uploaded_file = st.file_uploader("Upload Tender PDF", type="pdf")

if uploaded_file:
    if not api_key_input:
        st.warning("Please enter API key.")
    else:
        if st.button("Analyze Tender", type="primary"):
            with st.spinner("Dynamically selecting model and analyzing document..."):
                text = extract_and_clean_text(uploaded_file)
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
