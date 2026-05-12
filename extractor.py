"""
Resume Structured Extractor — core skill
Supports PDF and plain-text (.txt) input.
Returns a structured JSON dict with resume fields.
"""

import json
import os
from datetime import date
import pdfplumber
import docx
from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])


PROMPT = """You are a resume parser. Extract structured information from the resume below.

Return a JSON object with exactly these fields:
- name: full name (string or null)
- email: email address (string or null)
- phone: phone number as written (string or null)
- location: city and/or country (string or null)
- education: list of objects, each with:
    - degree (string or null)
    - major (string or null)
    - school (string or null)
    - year (graduation year as string or null)
- experience: list of objects, each with:
    - company (string or null)
    - title (string or null)
    - start_year (string or null)
    - end_year (string or null, use "Present" if current)
    - description (one-sentence summary or null)
- skills: flat list of skill strings
- years_total_experience: total years of work experience calculated from date ranges (number or null). Today is {today} — use this as the end date for any "Present" or ongoing role.
- missing_fields: list of field names that are absent from the resume

Rules:
- Return ONLY the JSON object, no explanation, no markdown fences
- Do not invent information not present in the resume
- If a section is missing entirely, return [] for lists or null for scalars

Resume:
{text}"""


def _load_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        with pdfplumber.open(file_path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages)
    if ext in (".docx", ".doc"):
        doc = docx.Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def _parse_json(raw: str) -> dict:
    raw = raw.strip()

    # Strip markdown code fences
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Extract the outermost JSON object by matching braces
    start = raw.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model response")
    depth, end = 0, -1
    for i, ch in enumerate(raw[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        raise ValueError("Unmatched braces in model response")

    return json.loads(raw[start:end + 1])


def extract_resume(file_path: str, retries: int = 2) -> dict:
    """
    Extract structured fields from a resume file.

    Args:
        file_path: Path to .docx, .pdf, or .txt resume file.
        retries:   Number of retry attempts if JSON parsing fails.

    Returns:
        dict with keys: name, email, phone, location, education,
        experience, skills, years_total_experience, missing_fields
    """
    text = _load_text(file_path)
    last_err = None
    for attempt in range(1 + retries):
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=PROMPT.format(text=text, today=date.today().strftime("%B %d, %Y")),
        )
        try:
            return _parse_json(response.text)
        except Exception as e:
            last_err = e
    raise ValueError(f"Failed to parse JSON after {1 + retries} attempts: {last_err}")


def batch_extract(folder_path: str, output_file: str = "results.json") -> None:
    """
    Process all resumes in a folder. Output format is determined by file extension:
      .json -> save structured JSON only
      .csv  -> save flat CSV only

    Args:
        folder_path: Directory containing resume files (.docx, .pdf, .txt).
        output_file: Output file path ending in .json or .csv.
    """
    import csv

    ext = os.path.splitext(output_file)[1].lower()
    supported = {".docx", ".doc", ".pdf", ".txt"}
    files = sorted([
        os.path.join(folder_path, f)
        for f in os.listdir(folder_path)
        if os.path.splitext(f)[1].lower() in supported
    ])

    if not files:
        print(f"No supported resume files found in {folder_path}")
        return

    results = []
    for path in files:
        fname = os.path.basename(path)
        print(f"  Processing: {fname} ...", end=" ", flush=True)
        try:
            data = extract_resume(path)
            results.append({"file": fname, **data})
            print("✓")
        except Exception as e:
            print(f"✗ ({e})")
            results.append({"file": fname, "error": str(e)})

    if ext == ".json":
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\nDone. {len(results)} resume(s) → {output_file}")

    else:
        def flat(data):
            return {
                "file": data.get("file"),
                "name": data.get("name"),
                "email": data.get("email"),
                "phone": data.get("phone"),
                "location": data.get("location"),
                "years_experience": data.get("years_total_experience"),
                "skills": ", ".join(data.get("skills") or []),
                "education": "; ".join(
                    f"{e.get('degree')} {e.get('major')} @ {e.get('school')} ({e.get('year')})"
                    for e in (data.get("education") or [])
                ),
                "experience": "; ".join(
                    f"{e.get('title')} @ {e.get('company')} ({e.get('start_year')}-{e.get('end_year')})"
                    for e in (data.get("experience") or [])
                ),
                "missing_fields": ", ".join(data.get("missing_fields") or []),
                "error": data.get("error", ""),
            }
        fieldnames = ["file", "name", "email", "phone", "location", "years_experience",
                      "skills", "education", "experience", "missing_fields", "error"]
        with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows([flat(r) for r in results])
        print(f"\nDone. {len(results)} resume(s) → {output_file}")


if __name__ == "__main__":
    import sys
    import pprint

    if len(sys.argv) < 2:
        print("Usage:")
        print("  Single file:  python extractor.py <resume_file>")
        print("  Batch folder: python extractor.py <folder> [output.csv]")
        sys.exit(1)

    target = sys.argv[1]

    if os.path.isdir(target):
        out = sys.argv[2] if len(sys.argv) > 2 else "results.json"
        batch_extract(target, out)
    else:
        result = extract_resume(target)
        pprint.pprint(result)
