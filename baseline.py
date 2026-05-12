"""
Baseline resume extractor using regex and keyword matching.
Represents the current status-quo: no LLM, pure rule-based parsing.
"""

import re
import os
import docx


SKILL_KEYWORDS = [
    "python", "java", "javascript", "typescript", "sql", "r", "c++", "c#",
    "go", "ruby", "swift", "kotlin", "html", "css", "react", "vue", "angular",
    "node.js", "django", "flask", "fastapi", "spring", "tensorflow", "pytorch",
    "machine learning", "deep learning", "data analysis", "data science",
    "excel", "tableau", "power bi", "figma", "photoshop", "illustrator",
    "git", "docker", "kubernetes", "aws", "azure", "gcp", "linux",
    "mongodb", "postgresql", "mysql", "redis", "spark", "hadoop",
    "communication", "leadership", "project management", "agile", "scrum",
    "product management", "ux", "ui", "restful", "graphql",
]


def _load_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        except Exception:
            return ""
    if ext in (".docx", ".doc"):
        doc = docx.Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def extract_resume_baseline(file_path: str) -> dict:
    """
    Extract resume fields using regex and keyword lists.
    No LLM involved — represents the naive baseline.

    Args:
        file_path: Path to .pdf or .txt resume file.

    Returns:
        dict with same schema as extractor.py (many fields will be null/empty).
    """
    text = _load_text(file_path)
    lower = text.lower()

    # --- Email ---
    emails = re.findall(r"[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}", text)
    email = emails[0] if emails else None

    # --- Phone ---
    phones = re.findall(
        r"(?:\+?[\(\d][\d\s\-().]{7,15}\d)", text
    )
    phone = phones[0].strip() if phones else None

    # --- Name: first non-empty line heuristic ---
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    first_line = lines[0] if lines else ""
    words = first_line.split()
    name = first_line if 1 < len(words) <= 5 else None

    # --- Skills: keyword scan ---
    found_skills = [s for s in SKILL_KEYWORDS if s in lower]

    # --- Missing fields ---
    missing = []
    if not name:
        missing.append("name")
    if not email:
        missing.append("email")
    if not phone:
        missing.append("phone")
    if not found_skills:
        missing.append("skills")
    missing += ["location", "education", "experience", "years_total_experience"]

    return {
        "name": name,
        "email": email,
        "phone": phone,
        "location": None,
        "education": [],
        "experience": [],
        "skills": found_skills,
        "years_total_experience": None,
        "missing_fields": missing,
    }


if __name__ == "__main__":
    import sys
    import pprint

    if len(sys.argv) < 2:
        print("Usage: python baseline.py <resume_file>")
        sys.exit(1)

    result = extract_resume_baseline(sys.argv[1])
    pprint.pprint(result)
