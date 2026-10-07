# resume-ats-check
# 📄 AI Resume ATS Checker

Upload a resume (PDF, DOCX or TXT) and get an **ATS score out of 100**, a score breakdown,
missing keywords, prioritised improvements and rewrite examples. Built with
**Streamlit** and **Google Gemini Flash**.

## Features
- PDF / DOCX / TXT resume upload
- Weighted ATS score across 6 categories (keywords, impact, formatting, skills, contact, clarity)
- Optional job description for role-specific keyword matching
- Prioritised improvements (High / Medium / Low) with concrete fixes
- Before/after bullet rewrite examples
- Downloadable text report

## Run locally
```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Get a free Gemini API key at https://aistudio.google.com/apikey, then provide it in one of these ways:

1. **Paste it in the app sidebar** (simplest), or
2. Set an environment variable: `export GEMINI_API_KEY="your-key"` (Windows: `set GEMINI_API_KEY=your-key`), or
3. Create `.streamlit/secrets.toml`:
   ```toml
   GEMINI_API_KEY = "your-key"
   ```

Start the app:
```bash
streamlit run app.py
```

## Deploy on Streamlit Community Cloud
1. Push this repo to GitHub (keep `app.py` and `requirements.txt` in the root).
2. Go to https://share.streamlit.io and sign in with GitHub.
3. Click **Create app** → choose your repo, branch `main`, main file `app.py`.
4. Open **Advanced settings → Secrets** and add: `GEMINI_API_KEY = "your-key"`
5. Click **Deploy**.

## Notes
- Scanned (image-only) PDFs can't be read; use a text-based PDF or DOCX.
- The score is an AI estimate of ATS-friendliness, not the output of a real ATS.
- Never commit your API key. Add `.streamlit/secrets.toml` to `.gitignore`.

## Project structure
```
app.py            # Streamlit app
requirements.txt  # Python dependencies
README.md
```
