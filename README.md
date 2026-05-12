# Resume Structured Extractor

A GenAI skill that extracts structured fields from resumes (.docx, .pdf, .txt) for HR workflows.

---

## Context, User, and Problem

**User**: HR staff at a mid-size company processing 50–100 resumes per week.

**Problem**: Resumes arrive in wildly different formats — chronological, creative, international. Manual data entry into ATS systems is slow, error-prone, and scales poorly. Rule-based parsers (regex) can extract email and phone but fail on education, experience, and skills — the fields that matter most for screening.

**Why GenAI**: LLMs can read layout-agnostic text and infer structure from context, handling formats that no regex can anticipate.

---

## Solution and Design

**Type**: Callable skill — a Python function with clear inputs and outputs, invokable from a script, agent, or automation pipeline.

```
Input:  path to a .docx, .pdf, or .txt resume file
Output: structured JSON dict
```

**Output schema**:
```json
{
  "name": "string or null",
  "email": "string or null",
  "phone": "string or null",
  "location": "string or null",
  "education": [{"degree": "...", "major": "...", "school": "...", "year": "..."}],
  "experience": [{"company": "...", "title": "...", "start_year": "...", "end_year": "..."}],
  "skills": ["skill1", "skill2"],
  "years_total_experience": 5.0,
  "missing_fields": ["field_name"]
}
```

**As a skill**: `extract_resume()` is a callable function with a single file-path input and a structured dict output. It can be invoked directly by a human, called from a script, or used as a tool by an agent that needs to process resumes as part of a larger pipeline (e.g. auto-filling an ATS, filtering candidates by skill, or generating a shortlist).

**Key design choices**:
- `missing_fields` — the model explicitly flags absent information rather than guessing
- `years_total_experience` — inferred from date ranges, not just copied from text
- Prompt rule: "never fabricate" — if a field is absent, return null
- Retry logic (up to 2 retries) handles occasional malformed JSON from the model
- Model: `gemini-2.5-flash` via Google AI API (free tier)

**Supported input formats**: `.docx`, `.pdf`, `.txt`

**Batch mode**: process an entire folder and export results as JSON or CSV

---

## Evaluation and Results

### Baseline

`baseline.py` — regex + keyword matching, no AI. Represents the current status quo:
- Email and phone: extracted via regex patterns
- Name: first-line heuristic (first non-empty line with 2–5 words)
- Skills: matched against a fixed keyword list of ~40 common skills
- Location / Education / Experience: not attempted, always returns null / empty

### Test Set

5 resumes across different formats and candidate profiles:

| File | Format | Profile |
|------|--------|---------|
| resume1.txt | Plain text | Standard SWE (US) |
| resume2.docx | Word document | Senior healthcare AI professional |
| resume3.pdf | PDF | International candidate (Germany) |
| resume4.txt | Plain text | Senior professional, company acquisitions |
| resume5.txt | Plain text | Candidate with no phone number |

Ground truth for each resume is stored in `data/*_gt.json`. Run `evaluate.py` to reproduce results.

### Rubric

- Scalar fields (name, email, phone, location): exact match (case-insensitive) = 1.0, wrong = 0.0
- `years_total_experience`: within ±1 year of ground truth = 1.0
- Skills / experience companies / education schools: recall = fraction of ground-truth items found in prediction

### Results

| Field | LLM (Gemini 2.5 Flash) | Baseline (Regex) |
|-------|----------------------|-----------------|
| Name | 100% | 80% |
| Email | 100% | 100% |
| Phone | 100% | 100% |
| Location | 100% | 0% |
| Years Experience | 100% | 0% |
| Skills (recall) | 93% | 73% |
| Experience (recall) | 87% | 0% |
| Education (recall) | 80% | 0% |
| **Overall** | **94.8%** | **42.7%** |

The baseline matches the LLM only on the simplest structured fields (email, phone). For every field requiring contextual understanding — location, work history, education, and computing years from date ranges — the baseline returns nothing. The LLM extracts all fields reliably across .txt, .docx, and .pdf formats.

### Where it breaks down

- **Scanned PDFs** (image-only): `pdfplumber` extracts no text, the model never sees the content — extraction fails entirely
- **Company name normalization**: if the LLM writes "N26" instead of "N26 GmbH", the exact-match recall metric counts it as a miss even though the extraction is semantically correct
- **Skills buried in job descriptions**: if skills appear inline rather than in a dedicated section, recall drops ~10–15%
- **Malformed JSON from model**: resolved by retry logic (up to 2 attempts), but adds latency

### Where a human should stay involved

- Final candidate screening decisions
- Verifying `years_total_experience` on senior hires where date ranges are ambiguous
- Any resume where `missing_fields` flags critical items (e.g. no contact info)

---

## Artifact Snapshot

### Demo video

**[Watch demo on YouTube](https://youtu.be/adkSpHNRM7Q)**

The demo shows batch processing on 3 resumes due to time constraints. In practice, the skill processes any number of files in a single command — the same workflow scales to thousands of resumes without modification.

### Single file extraction

```bash
python extractor.py data/resume1.txt
```

**Output:**
```json
{
  "name": "Jane Smith",
  "email": "jane.smith@email.com",
  "phone": "(415) 555-0192",
  "location": "San Francisco, CA",
  "education": [
    {
      "degree": "B.S.",
      "major": "Computer Science",
      "school": "University of California, Berkeley",
      "year": "2019"
    }
  ],
  "experience": [
    {
      "company": "Stripe",
      "title": "Senior Software Engineer",
      "start_year": "2021",
      "end_year": "Present",
      "description": "Led backend development for payment reconciliation service"
    },
    {
      "company": "Airbnb",
      "title": "Software Engineer",
      "start_year": "2019",
      "end_year": "2021",
      "description": "Built real-time pricing recommendation engine using Python and TensorFlow"
    }
  ],
  "skills": ["Python", "Go", "SQL", "PostgreSQL", "Redis", "Docker", "Kubernetes", "AWS", "TensorFlow", "Git", "React", "REST APIs"],
  "years_total_experience": 6.75,
  "missing_fields": []
}
```

### Baseline on the same file

```bash
python baseline.py data/resume1.txt
```

**Output:**
```json
{
  "name": "Jane Smith",
  "email": "jane.smith@email.com",
  "phone": "(415) 555-0192",
  "location": null,
  "education": [],
  "experience": [],
  "skills": ["python", "sql", "react", "tensorflow", "docker", "kubernetes", "aws", "git"],
  "years_total_experience": null,
  "missing_fields": ["location", "education", "experience", "years_total_experience"]
}
```

### Batch processing

```bash
# Export all resumes as JSON
python extractor.py data/ results.json

# Export all resumes as CSV
python extractor.py data/ results.csv
```

**Terminal output:**
```
  Processing: resume1.txt ... ✓
  Processing: resume2.docx ... ✓
  Processing: resume3.pdf ... ✓
  Processing: resume4.txt ... ✓
  Processing: resume5.txt ... ✓

Done. 5 resume(s) → results.json
```

### Evaluation

```bash
python evaluate.py data/
```

**Terminal output:**
```
==========================================================
Field                           LLM   Baseline      n
==========================================================
Name                        100.0%     80.0%      5
Email                       100.0%    100.0%      5
Phone                       100.0%    100.0%      4
Location                    100.0%      0.0%      5
Years Experience            100.0%      0.0%      5
Skills (recall)              93.1%     73.3%      5
Experience (recall)          86.7%      0.0%      5
Education (recall)           80.0%      0.0%      5
==========================================================
OVERALL                      94.8%     42.7%
==========================================================
```

---

## Setup and Usage

### Requirements
- Python 3.10+
- Google AI API key (free tier at [aistudio.google.com](https://aistudio.google.com))

### Install

```bash
pip install -r requirements.txt
```

### API Key

Copy the example env file and add your key:

```bash
cp .env.example .env
```

Open `.env` and replace the placeholder:

```
GOOGLE_API_KEY=your_google_api_key_here
```

### Run on a single resume

```bash
python extractor.py data/resume1.txt
```

### Run batch on a folder

```bash
# JSON output
python extractor.py data/ results.json

# CSV output (Excel-compatible)
python extractor.py data/ results.csv
```

### Run evaluation (LLM vs baseline)

```bash
python evaluate.py data/
```

### Use as a skill in your own code

```python
from extractor import extract_resume

result = extract_resume("path/to/resume.docx")
print(result["name"])
print(result["skills"])
print(result["missing_fields"])
```

### Supported input formats

| Format | Parser |
|--------|--------|
| `.docx` / `.doc` | python-docx |
| `.pdf` | pdfplumber |
| `.txt` | built-in |
