import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
from datetime import datetime

# Set page configuration with a professional theme
st.set_page_config(
    page_title="Calibration Compliance Portal",
    page_icon="🛡️",
    layout="wide"
)

# Header Section
st.title("🛡️ Calibration Compliance & Ingestion Portal")
st.markdown("""
Upload PDF calibration certificates to automatically extract device metadata, map calibration reference standards, 
evaluate active compliance status, and export structured validation records.
""")



def evaluate_compliance(record):
    """
    Evaluates the parsed calibration record against compliance and safety guidelines.
    """
    flags = []
    status = "Active"
    risk_level = "Low"
    
    # Get the current date for expiration validation
    today = datetime.now().date()
    
    # 1. Device Expiration Audit
    if record["Next Due Date"] != "N/A":
        try:
            due_date = datetime.strptime(record["Next Due Date"], "%Y-%m-%d").date()
            if due_date < today:
                status = "Expired"
                flags.append("🚨 Calibration expired")
                risk_level = "High"
        except ValueError:
            pass
    else:
        status = "Unknown"
        flags.append("❓ Missing Next Due Date")
        risk_level = "Medium"

    # 2. Critical Word Analysis in Remarks
    risk_words = ["discontinued", "fail", "out of tolerance", "repaired", "adjust", "replace"]
    if record["Remarks"] and record["Remarks"] != "N/A":
        found_risks = [word for word in risk_words if word in record["Remarks"].lower()]
        if found_risks:
            flags.append(f"⚠️ Flagged keyword in remarks: {', '.join(found_risks)}")
            if risk_level != "High":
                risk_level = "Medium"

    # 3. Reference Standards Integrity Checks
    for i in range(1, 5):
        equip = record.get(f"Reference Equpment {i}")
        sn = record.get(f"Reference Equipment {i} SN")
        if equip and (not sn or sn in ["*", "N/A", ""]):
            flags.append(f"🔍 Missing S/N for Standard {i} ({equip})")
            if risk_level == "Low":
                risk_level = "Medium"

    return {
        "Validation Status": status,
        "Risk Level": risk_level,
        "Validation Notes": " | ".join(flags) if flags else "Passed Check ✅"
    }


def parse_calibration_pdf(pdf_file):
    """
    Extracts text and matches metadata patterns from an uploaded calibration certificate.
    """
    try:
        with pdfplumber.open(pdf_file) as pdf:
            text = "\n".join([page.extract_text() or "" for page in pdf.pages])
    except Exception as e:
        return {
            "File Name": pdf_file.name,
            "Remarks": f"Failed to open/read PDF structure: {str(e)}"
        }

    # Initialize record matching the target spreadsheet layout
    record = {
        "File Name": pdf_file.name,
        "Serial #": "N/A",
        "Description": "N/A",
        "Completed Date": "N/A",
        "Next Due Date": "N/A",
        "Authority": "N/A",
        "Performed By": "N/A",
        "Reference Equpment 1": "",
        "Reference Equipment 1 SN": "",
        "Reference Equpment 2": "",
        "Reference Equipment 2 SN": "",
        "Reference Equpment 3": "",
        "Reference Equipment 3 SN": "",
        "Reference Equpment 4": "",
        "Reference Equipment 4 SN": "",
        "Remarks": ""
    }

    # Standard Field Extraction Regular Expressions
    patterns = {
        "Serial #": r"Serial Number:\s*(.*)",
        "Description": r"Description:\s*(.*)",
        "Completed Date": r"Completed Date:\s*(\d{1,2}/\d{1,2}/\d{4})",
        "Next Due Date": r"Next Due Date:\s*(\d{1,2}/\d{1,2}/\d{4})",
        "Authority": r"Authority:\s*(.*)",
        "Performed By": r"Performed By:\s*(.*)",
        "Remarks": r"Remarks:\s*([\s\S]*?)(?=\nAuthority:|For questions on this template|\Z)"
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            val = match.group(1).strip()
            if val:
                record[key] = val

    # Standardize extracted date objects into ISO-8601 YYYY-MM-DD strings
    for date_key in ["Completed Date", "Next Due Date"]:
        if record[date_key] != "N/A":
            try:
                parts = record[date_key].split('/')
                record[date_key] = f"{parts[2]}-{int(parts[0]):02d}-{int(parts[1]):02d}"
            except Exception:
                pass

    # Normalize carriage returns and spacing in Multi-line Remarks
    if record["Remarks"]:
        record["Remarks"] = re.sub(r'\s+', ' ', record["Remarks"]).strip()

    # Locate and Parse Reference Equipment Standard Tables (Up to 4 pairs)
    ref_match = re.search(r"Standard/Reference Equipment:([\s\S]*?)(?=\nRemarks:|\nAuthority:)", text)
    if ref_match:
        ref_text = ref_match.group(1)
        # Standard extraction pattern
        lines = re.findall(
            r"^(?!Equipment|Reference Equipment|Calipers)([\w\s/]+?)\s+((?:MET-|FTW-|\*|N/A|Model:).*?)\s+(?:\d{1,2}/\d{1,2}/\d{4}|\d{1,2}-\w{3}-\d{2})?$",
            ref_text,
            re.MULTILINE
        )
        # Sieve standard layout fallback
        if not lines:
            lines = re.findall(r"^(Calipers)\s+(\*|N/A)", ref_text, re.MULTILINE)

        for i, (equip_desc, equip_sn) in enumerate(lines[:4]):
            record[f"Reference Equpment {i + 1}"] = equip_desc.strip()
            record[f"Reference Equipment {i + 1} SN"] = equip_sn.strip()

    return record


# Upload Component UI
uploaded_files = st.file_uploader(
    "Choose PDF calibration files",
    type=["pdf"],
    accept_multiple_files=True,
    help="Select one or multiple calibration certificate PDF documents from your local filesystem."
)

if uploaded_files:
    progress_bar = st.progress(0)
    parsed_records = []

    # Process all uploaded files
    for idx, file in enumerate(uploaded_files):
        # 1. Parse raw text and extract metadata
        record_data = parse_calibration_pdf(file)
        
        # 2. Run extracted metrics through the compliance logic
        compliance_check = evaluate_compliance(record_data)
        record_data.update(compliance_check)
        
        parsed_records.append(record_data)
        progress_bar.progress((idx + 1) / len(uploaded_files))

    # Definitive schema layout sequence
    target_columns = [
        "File Name", "Serial #", "Description", "Completed Date", "Next Due Date",
        "Validation Status", "Risk Level", "Validation Notes",
        "Authority", "Performed By", 
        "Reference Equpment 1", "Reference Equipment 1 SN",
        "Reference Equpment 2", "Reference Equipment 2 SN", 
        "Reference Equpment 3", "Reference Equipment 3 SN", 
        "Reference Equpment 4", "Reference Equipment 4 SN",
        "Remarks"
    ]

    # Load records to DataFrame
    df = pd.DataFrame(parsed_records).reindex(columns=target_columns)

    st.success(f"Processing complete! Successfully resolved {len(uploaded_files)} record(s).")

    # Metrics Summary Cards
    st.subheader("📊 Ingestion Summary Metrics")
    m_col1, m_col2, m_col3 = st.columns(3)
    
    total_records = len(df)
    expired_count = len(df[df["Validation Status"] == "Expired"])
    high_risk_count = len(df[df["Risk Level"] == "High"])

    m_col1.metric("Total Files Uploaded", total_records)
    m_col2.metric("Expired Devices Flagged", expired_count, delta=f"{expired_count} review required" if expired_count > 0 else "0 flagged", delta_color="inverse")
    m_col3.metric("High Risk Violations", high_risk_count, delta=f"{high_risk_count} action needed" if high_risk_count > 0 else "All clear", delta_color="inverse")

    st.markdown("---")

    # Interactive Table with custom styling
    st.subheader("📋 Ingested Records & Compliance Status")
    
    # Apply status colors to the display table for immediate user visual scanning
    def style_status(val):
        if val == "Expired" or val == "High":
            return 'background-color: #ffcccc; color: #cc0000; font-weight: bold;'
        elif val == "Medium":
            return 'background-color: #fff2cc; color: #b38600; font-weight: bold;'
        elif val == "Active" or val == "Low" or "Passed" in str(val):
            return 'background-color: #e2f0d9; color: #385723;'
        return ''

    styled_df = df.style.map(style_status, subset=["Validation Status", "Risk Level", "Validation Notes"])
    st.dataframe(styled_df, use_container_width=True)

    # Spreadsheet Download Exports
    st.subheader("📥 Export Spreadsheet Log")
    col1, col2 = st.columns(2)

    with col1:
        csv_data = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📄 Download as CSV Spreadsheet",
            data=csv_data,
            file_name="calibration_ingestion_log.csv",
            mime="text/csv",
            use_container_width=True
        )

    with col2:
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Compliance Log")
        st.download_button(
            label="📊 Download as formatted Excel (.xlsx)",
            data=excel_buffer.getvalue(),
            file_name="calibration_compliance_log.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
