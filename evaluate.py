"""
Evaluation script: compare LLM extractor vs regex baseline.
Scores field-level accuracy across all resumes in the data directory.

Usage:
    python evaluate.py [data_dir]

Default data_dir: ./data
"""

import json
import os
import sys
from extractor import extract_resume
from baseline import extract_resume_baseline


SCALAR_FIELDS = ["name", "email", "phone", "location", "years_total_experience"]
SKILL_FIELD = "skills"


def normalize(val) -> str:
    if val is None:
        return ""
    return str(val).lower().strip()


def score_scalar(pred, truth, field: str = "") -> float | None:
    """1.0 = exact match (case-insensitive), 0.0 = wrong, None = skip (truth absent).
    For years_total_experience: use tolerance of ±1 year instead of exact match."""
    if truth is None or truth == "":
        return None
    if field == "years_total_experience":
        try:
            return 1.0 if abs(float(pred) - float(truth)) <= 1.0 else 0.0
        except (TypeError, ValueError):
            return 0.0
    return 1.0 if normalize(pred) == normalize(truth) else 0.0


def score_skills_recall(pred_skills: list, truth_skills: list) -> float | None:
    """Fraction of ground-truth skills found in prediction (recall)."""
    if not truth_skills:
        return None
    truth_set = {s.lower().strip() for s in truth_skills}
    pred_set = {s.lower().strip() for s in (pred_skills or [])}
    return len(truth_set & pred_set) / len(truth_set)


def score_experience_recall(pred_exp: list, truth_exp: list) -> float | None:
    """Fraction of ground-truth companies found in prediction."""
    if not truth_exp:
        return None
    truth_companies = {e.get("company", "").lower().strip() for e in truth_exp if e.get("company")}
    pred_companies = {e.get("company", "").lower().strip() for e in (pred_exp or []) if e.get("company")}
    if not truth_companies:
        return None
    return len(truth_companies & pred_companies) / len(truth_companies)


def score_education_recall(pred_edu: list, truth_edu: list) -> float | None:
    """Fraction of ground-truth schools found in prediction."""
    if not truth_edu:
        return None
    truth_schools = {e.get("school", "").lower().strip() for e in truth_edu if e.get("school")}
    pred_schools = {e.get("school", "").lower().strip() for e in (pred_edu or []) if e.get("school")}
    if not truth_schools:
        return None
    return len(truth_schools & pred_schools) / len(truth_schools)


def evaluate_one(pred: dict, gt: dict) -> dict:
    scores = {}
    for field in SCALAR_FIELDS:
        s = score_scalar(pred.get(field), gt.get(field), field)
        if s is not None:
            scores[field] = s
    s = score_skills_recall(pred.get("skills", []), gt.get("skills", []))
    if s is not None:
        scores["skills"] = s
    s = score_experience_recall(pred.get("experience", []), gt.get("experience", []))
    if s is not None:
        scores["experience_companies"] = s
    s = score_education_recall(pred.get("education", []), gt.get("education", []))
    if s is not None:
        scores["education_schools"] = s
    return scores


def run_evaluation(data_dir: str):
    all_fields = SCALAR_FIELDS + ["skills", "experience_companies", "education_schools"]
    llm_scores = {f: [] for f in all_fields}
    base_scores = {f: [] for f in all_fields}

    gt_files = sorted(f for f in os.listdir(data_dir) if f.endswith("_gt.json"))
    if not gt_files:
        print(f"No ground-truth files found in {data_dir}")
        return

    print(f"\nEvaluating {len(gt_files)} resume(s)...\n")

    for gt_file in gt_files:
        stem = gt_file.replace("_gt.json", "")
        gt_path = os.path.join(data_dir, gt_file)

        resume_path = None
        for ext in [".txt", ".pdf", ".docx", ".doc"]:
            candidate = os.path.join(data_dir, stem + ext)
            if os.path.exists(candidate):
                resume_path = candidate
                break

        if not resume_path:
            print(f"  [SKIP] No resume file for {stem}")
            continue

        with open(gt_path, "r", encoding="utf-8") as f:
            gt = json.load(f)

        print(f"  Processing: {stem}", end="", flush=True)

        try:
            llm_pred = extract_resume(resume_path)
            print(" ✓ LLM", end="")
        except Exception as e:
            print(f" ✗ LLM failed ({e})", end="")
            llm_pred = {}

        try:
            base_pred = extract_resume_baseline(resume_path)
            print(" ✓ Baseline")
        except Exception as e:
            print(f" ✗ Baseline failed ({e})")
            base_pred = {}

        llm_s = evaluate_one(llm_pred, gt)
        base_s = evaluate_one(base_pred, gt)

        for field in all_fields:
            if field in llm_s:
                llm_scores[field].append(llm_s[field])
                base_scores[field].append(base_s.get(field, 0.0))

    # --- Print results table ---
    LABELS = {
        "name": "Name",
        "email": "Email",
        "phone": "Phone",
        "location": "Location",
        "years_total_experience": "Years Experience",
        "skills": "Skills (recall)",
        "experience_companies": "Experience (recall)",
        "education_schools": "Education (recall)",
    }

    print(f"\n{'=' * 58}")
    print(f"{'Field':<24} {'LLM':>10} {'Baseline':>10} {'n':>6}")
    print(f"{'=' * 58}")

    total_llm, total_base, total_n = [], [], 0

    for field in all_fields:
        scores_l = llm_scores[field]
        scores_b = base_scores[field]
        if not scores_l:
            continue
        avg_l = sum(scores_l) / len(scores_l)
        avg_b = sum(scores_b) / len(scores_b)
        total_llm.extend(scores_l)
        total_base.extend(scores_b)
        label = LABELS.get(field, field)
        print(f"{label:<24} {avg_l:>9.1%} {avg_b:>9.1%} {len(scores_l):>6}")

    print(f"{'=' * 58}")
    if total_llm:
        oa_l = sum(total_llm) / len(total_llm)
        oa_b = sum(total_base) / len(total_base)
        print(f"{'OVERALL':<24} {oa_l:>9.1%} {oa_b:>9.1%}")
    print(f"{'=' * 58}\n")


if __name__ == "__main__":
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "data"
    run_evaluation(data_dir)
