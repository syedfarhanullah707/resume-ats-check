"""AI Resume ATS Checker - Streamlit + Gemini Flash."""

import json
import os
import re
from io import BytesIO

import streamlit as st
from docx import Document
from google import genai
from google.genai import types
from pypdf import PdfReader

MODEL_NAME = "gemini-3.8-flash"
MAX_RESUME_CHARS = 20_000
MAX_JD_CHARS = 8_000

# (label, weight). Weights sum to 100.
CATEGORIES = {
    "keywords": ("Keywords & Relevance", 25),
    "impact": ("Experience & Impact", 25),
    "formatting": ("Formatting & Structure", 20),
    "skills": ("Skills Presentation", 10),
    "contact": ("Contact & Completeness", 10),
    "clarity": ("Grammar & Clarity", 10),
}

PROMPT = """You are an expert ATS (Applicant Tracking System) analyst and professional resume reviewer.

Evaluate the resume text below{jd_clause}. Be strict, honest and specific. Do not invent
information that is not in the resume.

Return ONLY a JSON object with exactly this structure:
{{
  "category_scores": {{
    "keywords": <0-100>,
    "impact": <0-100>,
    "formatting": <0-100>,
    "skills": <0-100>,
    "contact": <0-100>,
    "clarity": <0-100>
  }},
  "summary": "<2-3 sentence overall assessment>",
  "strengths": ["<specific strength>", ...],
  "improvements": [
    {{"priority": "High|Medium|Low", "area": "<section or topic>",
      "issue": "<what is wrong>", "fix": "<concrete action to take>"}}
  ],
  "missing_keywords": ["<keyword>", ...],
  "rewrite_examples": [
    {{"original": "<weak bullet copied from the resume>",
      "improved": "<stronger version using action verb + metric>"}}
  ]
}}

Scoring guide:
- keywords: relevant industry/role keywords and skills{jd_keywords_note}
- impact: quantified achievements, action verbs, results over duties
- formatting: standard section headings, consistent structure, reasonable length, ATS-parseable layout
- skills: clear, organised, relevant skills section
- contact: email, phone, location, LinkedIn/portfolio, education and experience present
- clarity: grammar, concision, tone, no filler

Give 4-8 improvements, 3-5 strengths, up to 10 missing keywords, and 2-3 rewrite examples.
{jd_block}
RESUME TEXT:
\"\"\"
{resume}
\"\"\"
"""


# ----------------------------- File parsing ----------------------------- #
def extract_text(uploaded_file) -> str:
    """Extract plain text from a PDF, DOCX or TXT upload."""
    name = uploaded_file.name.lower()
    data = uploaded_file.getvalue()

    if name.endswith(".pdf"):
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise ValueError("This PDF is password-protected.")
        pages = [(page.extract_text() or "") for page in reader.pages]
        text = "\n".join(pages)
    elif name.endswith(".docx"):
        doc = Document(BytesIO(data))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        text = "\n".join(parts)
    elif name.endswith(".txt"):
        text = data.decode("utf-8", errors="ignore")
    else:
        raise ValueError("Unsupported file type. Upload a PDF, DOCX or TXT file.")

    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


# ----------------------------- Gemini call ------------------------------ #
def parse_json_response(raw: str) -> dict:
    """Parse JSON from the model, tolerating markdown fences or extra text."""
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError("The AI response was not valid JSON. Please try again.")


def _clamp(value) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0


def normalize_result(data: dict) -> dict:
    """Validate the model output and compute the weighted overall ATS score."""
    if not isinstance(data, dict):
        raise ValueError("Unexpected AI response format.")

    raw_scores = data.get("category_scores") or {}
    scores = {key: _clamp(raw_scores.get(key)) for key in CATEGORIES}
    overall = round(sum(scores[k] * CATEGORIES[k][1] for k in CATEGORIES) / 100)

    def str_list(key):
        items = data.get(key) or []
        return [str(i).strip() for i in items if str(i).strip()]

    improvements = []
    for item in data.get("improvements") or []:
        if isinstance(item, dict):
            priority = str(item.get("priority", "Medium")).title()
            if priority not in ("High", "Medium", "Low"):
                priority = "Medium"
            improvements.append(
                {
                    "priority": priority,
                    "area": str(item.get("area", "General")),
                    "issue": str(item.get("issue", "")),
                    "fix": str(item.get("fix", "")),
                }
            )
    order = {"High": 0, "Medium": 1, "Low": 2}
    improvements.sort(key=lambda i: order[i["priority"]])

    rewrites = []
    for item in data.get("rewrite_examples") or []:
        if isinstance(item, dict) and item.get("original") and item.get("improved"):
            rewrites.append(
                {"original": str(item["original"]), "improved": str(item["improved"])}
            )

    return {
        "overall": overall,
        "category_scores": scores,
        "summary": str(data.get("summary", "")).strip(),
        "strengths": str_list("strengths"),
        "improvements": improvements,
        "missing_keywords": str_list("missing_keywords"),
        "rewrite_examples": rewrites,
    }


def build_prompt(resume_text: str, job_description: str) -> str:
    jd = job_description.strip()[:MAX_JD_CHARS]
    return PROMPT.format(
        jd_clause=" against the provided job description" if jd else "",
        jd_keywords_note=" (match them against the job description)" if jd else "",
        jd_block=f'\nJOB DESCRIPTION:\n"""\n{jd}\n"""\n' if jd else "",
        resume=resume_text[:MAX_RESUME_CHARS],
    )


def analyze_resume(api_key: str, resume_text: str, job_description: str = "") -> dict:
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=build_prompt(resume_text, job_description),
        config=types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )
    return normalize_result(parse_json_response(response.text))


# --------------------------------- UI ----------------------------------- #
def score_color(score: int) -> str:
    return "#16a34a" if score >= 75 else "#d97706" if score >= 50 else "#dc2626"


def score_label(score: int) -> str:
    if score >= 80:
        return "Excellent"
    if score >= 65:
        return "Good"
    if score >= 50:
        return "Needs work"
    return "Poor"


def build_report(result: dict) -> str:
    lines = [f"ATS SCORE: {result['overall']}/100 ({score_label(result['overall'])})", ""]
    lines.append(result["summary"])
    lines += ["", "CATEGORY SCORES"]
    for key, (label, weight) in CATEGORIES.items():
        lines.append(f"- {label} ({weight}%): {result['category_scores'][key]}/100")
    lines += ["", "STRENGTHS"] + [f"- {s}" for s in result["strengths"]]
    lines += ["", "IMPROVEMENTS"]
    for i in result["improvements"]:
        lines.append(f"- [{i['priority']}] {i['area']}: {i['issue']} -> {i['fix']}")
    lines += ["", "MISSING KEYWORDS", ", ".join(result["missing_keywords"]) or "None"]
    lines += ["", "REWRITE EXAMPLES"]
    for r in result["rewrite_examples"]:
        lines += [f"Before: {r['original']}", f"After:  {r['improved']}", ""]
    return "\n".join(lines)


def get_api_key() -> str:
    try:
        key = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        key = ""
    return key or os.environ.get("GEMINI_API_KEY", "")


def render_results(result: dict) -> None:
    overall = result["overall"]
    color = score_color(overall)

    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown(
            f"""
            <div style="text-align:center;padding:24px;border-radius:16px;
                        border:3px solid {color};">
              <div style="font-size:64px;font-weight:700;color:{color};line-height:1;">{overall}</div>
              <div style="font-size:14px;opacity:.7;">out of 100</div>
              <div style="font-size:18px;font-weight:600;color:{color};margin-top:6px;">
                {score_label(overall)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.subheader("Summary")
        st.write(result["summary"] or "No summary returned.")

    st.subheader("Score breakdown")
    for key, (label, weight) in CATEGORIES.items():
        value = result["category_scores"][key]
        st.write(f"**{label}** · weight {weight}% · {value}/100")
        st.progress(value / 100)

    left, right = st.columns(2)
    with left:
        st.subheader("✅ Strengths")
        for s in result["strengths"] or ["No strengths returned."]:
            st.markdown(f"- {s}")
    with right:
        st.subheader("🔑 Missing keywords")
        if result["missing_keywords"]:
            st.markdown(" ".join(f"`{k}`" for k in result["missing_keywords"]))
        else:
            st.write("No major keywords missing.")

    st.subheader("🛠 Suggested improvements")
    icons = {"High": "🔴", "Medium": "🟠", "Low": "🟢"}
    for i in result["improvements"]:
        with st.expander(f"{icons[i['priority']]} {i['priority']} · {i['area']}"):
            st.markdown(f"**Issue:** {i['issue']}")
            st.markdown(f"**Fix:** {i['fix']}")

    if result["rewrite_examples"]:
        st.subheader("✍️ Rewrite examples")
        for r in result["rewrite_examples"]:
            st.markdown(f"**Before:** {r['original']}")
            st.markdown(f"**After:** {r['improved']}")
            st.divider()

    st.download_button(
        "⬇️ Download report (.txt)",
        build_report(result),
        file_name="ats_report.txt",
        mime="text/plain",
    )


def main() -> None:
    st.set_page_config(page_title="AI Resume ATS Checker", page_icon="📄", layout="wide")
    st.title("📄 AI Resume ATS Checker")
    st.caption("Upload your resume to get an ATS score and actionable improvements, powered by Gemini.")

    with st.sidebar:
        st.header("Settings")
        api_key = get_api_key()
        if api_key:
            st.success("API key loaded from secrets/environment.")
        else:
            api_key = st.text_input(
                "Gemini API key",
                type="password",
                help="Get a free key at https://aistudio.google.com/apikey",
            )
        st.markdown("---")
        st.markdown(
            "**Tip:** paste a job description to get keyword matching "
            "tailored to a specific role."
        )

    uploaded = st.file_uploader("Upload your resume", type=["pdf", "docx", "txt"])
    job_description = st.text_area(
        "Job description (optional)",
        height=150,
        placeholder="Paste the job posting here for a role-specific score...",
    )

    if st.button("Analyze resume", type="primary", disabled=uploaded is None):
        if not api_key:
            st.error("Please enter your Gemini API key in the sidebar.")
            return
        try:
            with st.spinner("Reading your resume..."):
                text = extract_text(uploaded)
            if len(text) < 100:
                st.error(
                    "Could not read enough text. If your PDF is a scanned image, "
                    "upload a text-based PDF or a DOCX instead."
                )
                return
            with st.spinner("Analyzing with Gemini..."):
                st.session_state["result"] = analyze_resume(api_key, text, job_description)
        except Exception as exc:  # show a friendly message instead of a traceback
            st.session_state.pop("result", None)
            st.error(f"Something went wrong: {exc}")
            return

    if "result" in st.session_state:
        render_results(st.session_state["result"])


if __name__ == "__main__":
    main()
