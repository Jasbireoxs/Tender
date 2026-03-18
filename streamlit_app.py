parsed_json = json.loads(raw_response)
        validated = TenderIntelligence(**parsed_json)
        return validated
    except Exception as e:
        st.error(f"❌ Error parsing Gemini response using model {target_model_name}: {e}")
        return None

def generate_draft_response(tender_data: TenderIntelligence):
    return f"""DRAFT SUBMISSION COVER LETTER

Subject: Submission for Tender - {tender_data.scope_summary.value}

Dear Sir/Madam,

We confirm submission before the deadline of {tender_data.submission_deadline.value}.
We comply with financial criteria: {tender_data.financial_criteria.value}
Technical eligibility met: {tender_data.technical_eligibility.value}
EMD enclosed: {tender_data.emd_amount.value}

We acknowledge all commercial and risk clauses and look forward to executing this project successfully.

Sincerely,
Iron Throne Engineering
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
# 3️⃣ STREAMLIT DASHBOARD UI
# -------------------------------
st.set_page_config(page_title="Iron Throne AI Operations", layout="wide")

if "tender_result" not in st.session_state:
    st.session_state.tender_result = None

# Sidebar Setup
with st.sidebar:
    # Inject Iron Throne Logo
    if os.path.exists("image_6d399e.png"):
        st.image("image_6d399e.png", use_container_width=True)
    else:
        st.header("⚙️ Iron Throne Engineering")
        
    st.divider()
    st.header("System Config")
    api_key_input = st.text_input("Enter Gemini API Key", type="password")
    st.markdown("Required for AI Agents to function.")

st.title("🚀 Iron Throne AI Control Center")
st.markdown("Unified dashboard for Tender Analysis, Vendor Comparison & Operational Tracking")

# Tabs
tab1, tab2, tab3 = st.tabs(["📄 Tender Intelligence", "📊 Vendor Comparison", "⏰ Follow-up Tracker"])

# -------------------------------
# 📄 TAB 1: TENDER SYSTEM
# -------------------------------
with tab1:
    st.header("Tender Intelligence System")

    uploaded_file = st.file_uploader("Upload Tender PDF", type="pdf")

    if uploaded_file:
        if not api_key_input:
            st.warning("Please enter your API key in the sidebar.")
        else:
            if st.button("Analyze Tender"):
                with st.spinner("Analyzing document structure..."):
                    text = extract_and_clean_text(uploaded_file)
                    st.session_state.tender_result = analyze_tender_with_gemini(text, api_key_input)

            if st.session_state.tender_result:
                result = st.session_state.tender_result

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
                risk_levels = []
                for risk in result.risk_clauses:
                    risk_levels.append(risk.risk_level)
                    if risk.risk_level == "High":
                        st.error(f"- {risk.description}")
                    elif risk.risk_level == "Medium":
                        st.warning(f"- {risk.description}")
                    else:
                        st.info(f"- {risk.description}")

                if "High" in risk_levels:
                    st.error("🚨 Overall Risk: HIGH")
                elif "Medium" in risk_levels:
                    st.warning("⚠️ Overall Risk: MEDIUM")
                else:
                    st.success("✅ Overall Risk: LOW")
                    
                st.subheader("⚡ Unusual Liabilities")
                for item in result.unusual_liabilities:
                    st.write("-", item)

                st.subheader("📝 Draft Submission Letter")
                st.text_area("Generated Draft", generate_draft_response(result), height=250)
                
                # Downloads
                col_dl1, col_dl2 = st.columns(2)
                with col_dl1:
                    result_dict = result.model_dump()
                    st.download_button("📥 Download JSON", data=json.dumps(result_dict, indent=2), file_name="iron_throne_tender.json", mime="application/json")
                with col_dl2:
                    st.download_button("📊 Download Excel", data=generate_excel(result), file_name="iron_throne_tender.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# -------------------------------
# 📊 TAB 2: VENDOR COMPARISON (VISION AI)
# -------------------------------
with tab2:
    st.header("AI Quotation Comparison")
    st.markdown("Upload vendor quotation images. The Vision AI will extract and compare the terms.")

    quote_files = st.file_uploader("Upload Vendor Quotes (Images)", type=["png", "jpg", "jpeg"], accept_multiple_files=True)

    if quote_files:
        if not api_key_input:
            st.warning("⚠️ Please enter your Gemini API Key in the sidebar.")
        else:
            if st.button("Extract & Compare Quotes", type="primary"):
                with st.spinner("Processing documents with Vision AI..."):
                    genai.configure(api_key=api_key_input)
                    model = genai.GenerativeModel("gemini-1.5-flash") 
                    
                    extracted_vendors = []
                    
                    for file in quote_files:
                        image_data = {"mime_type": file.type, "data": file.getvalue()}
                        
                        prompt = """
                        Extract the following from this quotation image and return strictly valid JSON:
                        {
                            "vendor_name": "Name of company",
                            "price": Numeric value only (no currency symbols),
                            "delivery_days": Numeric value only (estimate if necessary),
                            "credit_days": Numeric value only
                        }
                        """
                        try:
                            response = model.generate_content([prompt, image_data])
                            clean_json = re.sub(r"^
