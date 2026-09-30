"""
AttendSmart — synthetic dataset generator.

Generates a realistic, fully synthetic attendance + engagement dataset for a
single classroom/course, built around the REAL participant roster (names
only) supplied by the user. Every attribute — attendance, quiz scores,
engagement, risk outcome — is randomly generated demo data and must be
labeled as such in any presentation (per the Smart Classroom AI Challenge
data guidelines).

Design notes (important for the "Think Like a CDAIO" defense):
  - This is a forward-looking prediction task, not a lagging indicator.
    Features are computed ONLY from the first 60% of the term (weeks 1-6,
    sessions 1-12). The label is computed from actual outcomes in the
    remaining 40% of the term (weeks 7-10, sessions 13-20): did the
    student's attendance fall below the 75% institutional threshold in the
    back half of the course? This avoids leaking the answer into the
    features and mirrors a real early-warning use case.
  - Latent per-student traits (base reliability, workload trend, a
    "travel/conflict" shock for a subset of the cohort) drive both
    attendance AND engagement signals independently with their own noise,
    so the model has to learn a genuine multi-feature pattern rather than
    parrot a single hidden variable.

Run: python3 generate_dataset.py
Outputs (into ./data/):
  students.csv, sessions.csv, attendance.csv, engagement_weekly.csv,
  student_features.csv   (the ML-ready training table)
"""

import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from roster_names import ROSTER

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

OUT_DIR = Path(__file__).parent
COURSE_ID = "CDAIO-AI-201"
COURSE_NAME = "AI & Data Systems - Capstone Module"
INSTRUCTOR = "Prof. R. Menon"
TERM_START = date(2026, 7, 6)  # a Monday
WEEKS = 10
SESSIONS_PER_WEEK = 2
TOTAL_SESSIONS = WEEKS * SESSIONS_PER_WEEK  # 20
EARLY_SESSIONS = 12  # weeks 1-6 -> feature window
LATE_SESSIONS = TOTAL_SESSIONS - EARLY_SESSIONS  # weeks 7-10 -> label window
RISK_THRESHOLD = 0.75  # institutional attendance floor

CITIES = ["Bengaluru", "Mumbai", "Pune", "Chennai", "Hyderabad", "Delhi NCR",
          "Kolkata", "Ahmedabad", "Kochi", "Coimbatore"]


def make_students():
    students = []
    for i, name in enumerate(ROSTER, start=1):
        sid = f"S{i:03d}"
        base_reliability = np.clip(np.random.beta(9, 2.2), 0.40, 0.99)
        # workload trend: mostly mildly negative (exec program, work picks up
        # mid-term), a few positive
        trend = np.random.normal(-0.006, 0.008)
        travel_conflict = np.random.random() < 0.16  # ~1 in 6 hit a work/travel crunch
        if travel_conflict:
            trend -= np.random.uniform(0.015, 0.035)
        students.append({
            "student_id": sid,
            "name": name,
            "city": random.choice(CITIES),
            "work_experience_years": int(np.clip(np.random.normal(12, 5), 2, 28)),
            "prior_module_score_pct": round(float(np.clip(np.random.normal(74, 9), 45, 98)), 1),
            "_base_reliability": base_reliability,
            "_trend": trend,
            "_travel_conflict": travel_conflict,
        })
    return students


def make_sessions():
    sessions = []
    d = TERM_START
    week = 1
    sess_in_week = 0
    for idx in range(1, TOTAL_SESSIONS + 1):
        sessions.append({
            "session_id": f"SES{idx:03d}",
            "course_id": COURSE_ID,
            "session_index": idx,
            "week_number": week,
            "session_date": d.isoformat(),
            "topic": f"Session {idx} of {COURSE_NAME}",
        })
        sess_in_week += 1
        d += timedelta(days=3 if sess_in_week % SESSIONS_PER_WEEK == 0 else 2)
        if sess_in_week == SESSIONS_PER_WEEK:
            sess_in_week = 0
            week += 1
    return sessions


def simulate_attendance(students, sessions):
    attendance_rows = []
    per_student_sessions = {s["student_id"]: [] for s in students}
    for stu in students:
        for sess in sessions:
            idx = sess["session_index"]
            p_present = stu["_base_reliability"] + stu["_trend"] * idx
            p_present += np.random.normal(0, 0.06)  # session noise
            p_present = float(np.clip(p_present, 0.03, 0.99))
            roll = np.random.random()
            if roll < p_present:
                status = "Present"
                delay = max(0, int(np.random.normal(2, 3)))
                if delay > 8:
                    status = "Late"
            else:
                status = "Absent"
                delay = None
            attendance_rows.append({
                "session_id": sess["session_id"],
                "student_id": stu["student_id"],
                "session_index": idx,
                "week_number": sess["week_number"],
                "status": status,
                "check_in_delay_min": delay if delay is not None else "",
            })
            per_student_sessions[stu["student_id"]].append((idx, status))
    return attendance_rows, per_student_sessions


def simulate_engagement(students):
    rows = []
    for stu in students:
        for week in range(1, WEEKS + 1):
            reliability_at_week = np.clip(
                stu["_base_reliability"] + stu["_trend"] * (week * SESSIONS_PER_WEEK), 0.05, 0.99
            )
            lms_logins = max(0, int(np.random.normal(reliability_at_week * 9, 2.2)))
            submitted = np.random.random() < np.clip(reliability_at_week + 0.05, 0, 0.98)
            quiz_score = np.clip(np.random.normal(reliability_at_week * 100, 9), 20, 100)
            forum_posts = max(0, int(np.random.poisson(reliability_at_week * 1.4)))
            rows.append({
                "student_id": stu["student_id"],
                "week_number": week,
                "lms_logins": lms_logins,
                "assignment_submitted": submitted,
                "quiz_score": round(float(quiz_score), 1),
                "forum_posts": forum_posts,
            })
    return rows


def attendance_pct(session_status_list, session_index_filter):
    subset = [s for (idx, s) in session_status_list if idx in session_index_filter]
    if not subset:
        return None
    present_like = sum(1 for s in subset if s in ("Present", "Late"))
    return present_like / len(subset)


def longest_consecutive_absences(session_status_list, session_index_filter):
    subset = sorted([(idx, s) for (idx, s) in session_status_list if idx in session_index_filter])
    longest = cur = 0
    for _, s in subset:
        if s == "Absent":
            cur += 1
            longest = max(longest, cur)
        else:
            cur = 0
    return longest


def build_features(students, per_student_sessions, engagement_rows):
    early_idx = set(range(1, EARLY_SESSIONS + 1))
    late_idx = set(range(EARLY_SESSIONS + 1, TOTAL_SESSIONS + 1))

    eng_by_student = {}
    for row in engagement_rows:
        eng_by_student.setdefault(row["student_id"], []).append(row)

    feature_rows = []
    for stu in students:
        sid = stu["student_id"]
        sess_list = per_student_sessions[sid]

        early_pct = attendance_pct(sess_list, early_idx)
        # trend within the early window: first half vs second half of weeks 1-6
        first_third = set(range(1, 5))
        second_third = set(range(9, 13))
        pct_a = attendance_pct(sess_list, first_third) or 0
        pct_b = attendance_pct(sess_list, second_third) or 0
        early_trend = round(pct_b - pct_a, 3)

        late_status = [(i, s) for (i, s) in sess_list if i in late_idx]
        consecutive_absences_early = longest_consecutive_absences(sess_list, early_idx)
        late_arrival_pct = (
            sum(1 for i, s in sess_list if i in early_idx and s == "Late") / EARLY_SESSIONS
        )

        eng = [r for r in eng_by_student[sid] if r["week_number"] <= 6]
        avg_quiz = np.mean([r["quiz_score"] for r in eng]) if eng else 0
        submission_rate = np.mean([1 if r["assignment_submitted"] else 0 for r in eng]) if eng else 0
        avg_lms_logins = np.mean([r["lms_logins"] for r in eng]) if eng else 0
        avg_forum_posts = np.mean([r["forum_posts"] for r in eng]) if eng else 0

        # LABEL: computed only from the held-out late window (weeks 7-10)
        late_pct = attendance_pct(sess_list, late_idx)
        risk_label = int(late_pct is not None and late_pct < RISK_THRESHOLD)
        if late_pct is None:
            risk_tier = "Unknown"
        elif late_pct >= 0.9:
            risk_tier = "Low"
        elif late_pct >= RISK_THRESHOLD:
            risk_tier = "Medium"
        else:
            risk_tier = "High"

        feature_rows.append({
            "student_id": sid,
            "name": stu["name"],
            "city": stu["city"],
            "work_experience_years": stu["work_experience_years"],
            "prior_module_score_pct": stu["prior_module_score_pct"],
            "attendance_pct_early": round(early_pct, 3) if early_pct is not None else None,
            "attendance_trend_early": early_trend,
            "consecutive_absences_early": consecutive_absences_early,
            "late_arrival_pct_early": round(late_arrival_pct, 3),
            "avg_quiz_score_early": round(float(avg_quiz), 1),
            "assignment_submission_rate_early": round(float(submission_rate), 3),
            "avg_lms_logins_early": round(float(avg_lms_logins), 2),
            "avg_forum_posts_early": round(float(avg_forum_posts), 2),
            # outcome fields (used to build the label; kept for transparency /
            # the "explain" screen, NOT fed to the model as a feature)
            "attendance_pct_actual_late_window": round(late_pct, 3) if late_pct is not None else None,
            "risk_label": risk_label,
            "risk_tier": risk_tier,
        })
    return feature_rows


def write_csv(path, rows, fieldnames=None):
    if not rows:
        return
    fieldnames = fieldnames or list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    students = make_students()
    sessions = make_sessions()
    attendance_rows, per_student_sessions = simulate_attendance(students, sessions)
    engagement_rows = simulate_engagement(students)
    feature_rows = build_features(students, per_student_sessions, engagement_rows)

    # students.csv (public fields only, no leading underscore fields)
    public_students = [{k: v for k, v in s.items() if not k.startswith("_")} for s in students]
    write_csv(OUT_DIR / "students.csv", public_students)

    write_csv(OUT_DIR / "sessions.csv", sessions)
    write_csv(OUT_DIR / "attendance.csv", attendance_rows)
    write_csv(OUT_DIR / "engagement_weekly.csv", engagement_rows)
    write_csv(OUT_DIR / "student_features.csv", feature_rows)

    with open(OUT_DIR / "course_meta.json", "w") as f:
        json.dump({
            "course_id": COURSE_ID,
            "course_name": COURSE_NAME,
            "instructor": INSTRUCTOR,
            "term_start": TERM_START.isoformat(),
            "weeks": WEEKS,
            "sessions_per_week": SESSIONS_PER_WEEK,
            "total_sessions": TOTAL_SESSIONS,
            "early_window_sessions": EARLY_SESSIONS,
            "late_window_sessions": LATE_SESSIONS,
            "risk_threshold": RISK_THRESHOLD,
            "n_students": len(students),
            "data_note": "100% SYNTHETIC DEMO DATA. Only participant names are real; all "
                          "attendance, engagement, quiz and risk figures are randomly generated.",
        }, f, indent=2)

    n_risk = sum(r["risk_label"] for r in feature_rows)
    print(f"Generated {len(students)} students, {len(sessions)} sessions, "
          f"{len(attendance_rows)} attendance records.")
    print(f"Risk label distribution: {n_risk} at-risk / {len(feature_rows) - n_risk} not-at-risk "
          f"out of {len(feature_rows)} students.")


if __name__ == "__main__":
    main()
