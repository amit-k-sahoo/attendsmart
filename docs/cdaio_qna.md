# "Think Like a CDAIO" — Discussion Prep (Group 9, AttendSmart)

Draft answers for the 7 questions in the brief. These are starting points —
adapt them in your own words for the live Q&A.

## 1. What data would IIT Kanpur need to provide for a production version?
- Real attendance system logs (swipe/QR/LMS check-in) per session, per
  student, with timestamps.
- LMS activity logs (logins, resource views, assignment submissions,
  forum/discussion activity).
- Assessment records (quiz/assignment scores) at a granularity finer than
  final grades, so early-term signal exists.
- A program/course calendar (session dates, credit weight) to compute
  accurate rolling attendance percentages.
- Explicit consent records and a data-processing agreement covering use of
  this data for an early-warning system (see Q4).
- Historical outcomes (did past at-risk students actually drop below the
  attendance threshold?) to validate and retrain the model each term.

## 2. How would you measure whether the solution is successful?
- **Model quality:** precision/recall/ROC-AUC on held-out terms (not just
  LOO-CV on one small cohort — see the Model Card's honesty note about
  n=39).
- **Operational impact:** did advisor outreach to flagged students actually
  improve their second-half attendance, compared to a control group or to
  prior terms without the tool?
- **Adoption:** are advisors actually opening the dashboard and using the
  override feature, or is it being ignored?
- **Trust:** false-positive rate low enough that advisors don't tune the
  tool out; track override reasons (a spike in "not actually at risk"
  overrides is an early signal the model or threshold needs revisiting).
- **Equity check:** confirm the flagged population isn't skewed by any
  proxy variable (see Q4/fairness note in the Model Card) once real
  demographic-adjacent context is available for audit (not for the model).

## 3. What happens if the ML prediction is wrong?
- **Design stance:** every prediction is advisory, never automatic. Nothing
  in AttendSmart penalizes, grades, or restricts a student — it only
  surfaces a flag for a human advisor to review (see the Governance tab's
  human-in-the-loop override, logged with a mandatory reason).
- **False positive** (flagged but fine): costs an advisor a low-stakes
  check-in; logged as an override so the model/threshold can be tuned over
  time.
- **False negative** (missed, actually at risk): mitigated by the dashboard
  being a recurring weekly view, not a one-time verdict, plus advisors'
  own independent judgment — the tool augments attention, it doesn't
  replace it.
- The Model Card documents current LOO-CV precision/recall openly so users
  know the error rates going in, rather than treating the score as ground
  truth.

## 4. How would you protect student/faculty data?
- Minimize collection to what's needed for the specific prediction (no
  unrelated personal data).
- Align with India's **DPDP Act 2023**: explicit, informed consent before
  processing; a stated, limited purpose; retention limits; a way for
  students to access/correct/withdraw consent for their own data.
- Role-based access control (already demonstrated in the app — student vs.
  advisor views) so no one sees more than their role requires.
- No protected attributes (gender, religion, disability, etc.) used as
  model features, by design (see Model Card §6).
- Full audit logging of who viewed or acted on whose prediction (already
  implemented — see the Governance tab).
- Encryption in transit/at rest, and a defined data-retention/deletion
  policy at term end for anything beyond aggregate model-improvement data.

## 5. How would you scale the application beyond your demo dataset?
- Move from a single 39-person cohort to a multi-cohort, multi-term
  dataset — this both improves model stability (see the small-n caveats in
  the Model Card) and lets the model generalize across programs.
- Move the local FastAPI/scikit-learn stand-in to a managed Azure ML
  endpoint with autoscaling (see `docs/deployment_guide.md`).
- Automate retraining per term rather than a one-off fit.
- Add monitoring for data drift (are new terms' students structurally
  different from training data?) and model-performance decay.
- Integrate directly with the institution's actual attendance/LMS systems
  instead of a CSV upload step.

## 6. Where would human approval or intervention be required?
- Before any flag reaches a student directly (today, only advisors see
  individual predictions — students see their own, framed as "early
  warning," never as a decision already made about them).
- Before any action with real consequences (academic standing, probation,
  eligibility) is taken based on a flag — the model informs, a human
  decides.
- When overriding a prediction (already built: the Governance tab requires
  a reason for every override, creating an accountable audit trail).
- Periodically, to review whether the model's flags still make sense as
  the program/cohort changes term to term (model owner sign-off on
  retraining, not just automatic redeployment).

## 7. What would be required to move from prototype to production?
- Real, consented data pipelines (Q1) replacing synthetic CSVs.
- A larger, validated training set and a re-run of the honesty checks in
  the Model Card (the current model is intentionally simple and
  small-sample — that was the right call for a demo, not for production
  without revalidation).
- Managed hosting for both the ML endpoint (Azure ML managed online
  endpoint) and the chatbot (Dialogflow in production tier, or a hosted
  webhook with proper uptime/monitoring).
- Formal governance sign-off: data protection impact assessment (DPDP-
  aligned), a named data owner, and a documented human-override process
  (already prototyped here, but needs institutional policy backing).
- Integration with IIT Kanpur's actual identity/auth system (real login,
  not a name-picker dropdown) and its LMS/attendance systems.
- A support/feedback loop so advisors can flag bad predictions back to the
  model owners, closing the loop between the audit log and retraining.
