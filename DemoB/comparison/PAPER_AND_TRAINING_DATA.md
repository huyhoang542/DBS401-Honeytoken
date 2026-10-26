# Demo A, Demo B, paper method, and training data

## How the two demos map to the project

- **Demo A is the paper-inspired reference baseline used for comparison.** Its role in this project is to represent the paper-oriented/static approach against which the extension is assessed; it is not the project's new contribution. It inserts decoy employee records, tracks their IDs in a protected registry, and raises an alert when a decoy is returned by a query.
- **Demo B is the project's main upgrade and contribution.** It adds query behavior telemetry, a Random Forest risk score, scenario history, and a prototype that moves a fixed honeytoken budget between departments. Comparative tables measure B against A under shared datasets and test scenarios.
- The comparison must replay the same query episodes against the same `employee` database. Keep the two registries separate (`honeytoken_security` for A and `honeytoken_security_b` for B).

## Fidelity check against the referenced paper

The paper *Generation and deployment of honeytokens in relational databases for cyber deception* describes extracting a relational database and its metadata, generating coherent multi-table synthetic records with the HMA synthesizer in SDV, deploying decoy records, monitoring their access, and assessing believability with human evaluation. The sample database contains 10,000 employee rows and related tables.

References: [paper landing page and abstract](https://www.sciencedirect.com/science/article/pii/S0167404824003377); [Bytebase employee sample database README](https://github.com/bytebase/employee-sample-database/blob/main/mysql/README.md).

Demo A now includes an SDV `HMASynthesizer` pipeline that stages coherent employee/child-table candidate records. The current active registry still contains the old Faker token set until the owner approves/replaces that database set. It does not reproduce every placement strategy or the paper's human evaluation. Therefore, describe it as a **paper-inspired educational implementation**, not an exact reproduction.

Demo B's Random Forest behavior detector and risk-based department allocation are the **DBS401 extension**, not methods claimed by that paper. The paper's use of machine learning is for generating structurally/statistically similar relational records with HMA; it is not a Random Forest trained to classify attack sessions.

## Where the ML data comes from

There are distinct training/evaluation sources in the repository; do not conflate them:

1. `evaluation/run_common_scenarios.py` creates behavior features and attack/normal labels in memory using seeded NumPy distributions. It writes synthetic scenario results. The downloaded employee database supplies entity IDs only; it supplies no attack labels or query behavior. The prototype model `models/random_forest_synthetic.joblib` was trained on 4,000 generated rows with seed 9001.
2. The current live workflow first runs `evaluation/run_live_attack_simulation.py --capture-only`, which executes bounded, read-only queries against the local shared MySQL `employee` database. It records actual returned row counts, measured query duration, current hour, query table pattern and within-session frequency. Five repeats of eight scenario families produce 980 Demo B query rows across 40 sessions in the current workspace. The simulator labels each session from the scenario it intentionally ran. `evaluation/train_live_model.py` tunes the threshold on four repeats and evaluates the untouched fifth repeat, rotating across all five, then fits the interactive model on all captured Demo B rows. Thus feature values are observed from MySQL, while labels remain controlled-lab ground truth, not labels from real incidents.

The live simulator is not an exploit and does not alter employee, salary, or department records. It only accepts `localhost`/`127.0.0.1`, opens the reader connection as read-only, and writes CSV/JSON/model artifacts locally. It checks each result against the corresponding protected registry. It is a controlled behavior experiment, not proof of production detection effectiveness.

## Public real-data sources to upgrade Demo B

There is no suitable public corpus we found that combines **real MySQL audit queries**, **employee/user context**, and **ground-truth insider attack labels**. Public database logs are rare because schemas and query parameters can expose sensitive information. These are the best relevant sources, with their limitations:

| Source | What is genuinely observed | Labels | Fit for this project |
|---|---|---|---|
| [PhoneLab SQL query trace](https://odin.cse.buffalo.edu/papers/2015/TPCTC-sqlite-final.pdf) | One month of SQL activity from real Android SQLite use; recorded statements, runtimes and returned-row counts. The paper reports 45.4M statements from 11 devices. | Ordinary device use; no attack labels. | Best open source for learning real query/workload patterns. It is SQLite/mobile rather than MySQL/employee, so use it for normal-behavior pretraining or anomaly research and disclose domain shift. |
| [LANL Comprehensive Cyber-Security Events](https://csr.lanl.gov/data/cyber1/) | De-identified enterprise authentication, process, DNS/network-flow events from LANL. | Includes documented Red Team events. | Useful for labeled enterprise attack-behavior research, but it is not SQL/database audit telemetry; do not feed it directly into the current MySQL feature model. |
| [LANL Unified Host and Network Dataset](https://csr.lanl.gov/data/2017/) | Enterprise host and network event subset. | Includes Red Team activity windows. | Same caveat: real enterprise/security telemetry, not DB queries. |
| [Bytebase employee sample database](https://github.com/bytebase/employee-sample-database) | A public sample relational database with employee-like rows. | No query history or attack labels; the rows are sample data, not observed user activity. | Keep as Demo A/Demo B's relational target dataset, not as ML behavior training data. |

**Recommendation:** keep Demo B's model aligned to its target by collecting actual query telemetry from its MySQL gateway. Use PhoneLab only as a separate real-workload baseline if the project needs an external SQL trace. For the current local attack comparison, use the executed MySQL query observations and record labels in a separate reviewed-label field; scripted attack labels are ground truth for the lab scenario only. LANL can be a related-work/source comparison but cannot replace database audit logs. Avoid claiming that CERT Insider Threat logs are real: that corpus is generated/simulated. A public SQL-injection request corpus would also be a different task from detecting anomalous reads by an already-authorized database user.

## Run the controlled live simulation

Prerequisites: both demos' `.env` files must point to `DB_NAME=employee`; Demo A and B reader accounts need `SELECT` on the necessary employee tables, and each monitor account needs `SELECT` on its own registry. Start with a disposable/local MySQL instance and confirm the 50 tokens for each demo are seeded. From `DemoB/` run:

```powershell
python evaluation\run_live_attack_simulation.py --capture-only
python evaluation\train_live_model.py
python -m streamlit run dashboard\app.py
```

The workflow runs five repeats of eight normal/attack-like scenario families for both demos: routine point lookup, legitimate bulk report, maintenance read, rapid ID enumeration, department sweep, broad employee collection, low-and-slow targeting, and token probe validation. The token probe intentionally uses known canary IDs to verify alerts; it is not a claim that an attacker already knows those IDs. The trainer tunes the threshold using four repeats and evaluates on the held-out repeat, rotating over all five repeats, then fits the interactive model on all captured Demo B rows. Output:

- `results/live_attack_query_results.csv` — query-level observed telemetry and labels.
- `results/live_attack_session_results.csv` — one summarized outcome for each complete session (the fairer headline comparison).
- `results/live_attack_scenario_metrics.csv` — alert rate by scenario family.
- `results/live_attack_metrics.json` — common A/B metrics and protocol notes.
- `models/random_forest_live_sim.joblib` and `models/live_sim_model_metadata.json` — Demo B model trained on captured lab telemetry.

“Attack” means an intentionally scripted suspicious query pattern against the local teaching database; it does not attempt authentication bypass, modification, deletion, or access to another host. Current capture: 980 queries and 40 sessions for each demo. Demo B model training uses observed features but simulator-assigned labels.

## Limits of this validation

- The script labels complete query sessions from their scripted scenario. It can show behavior discrimination under these controlled patterns, but it cannot establish a real-world false-positive or detection rate.
- The `hour` feature is the actual host hour. The runner does not alter the system clock; all sessions in one run therefore happen in roughly the same hour, and it does not validate true off-hours detection.
- It runs the SELECT templates directly with the two demos' read-only database identities and checks the two registries; it does not invoke the CLI gateways or test production alert delivery end-to-end.
- The A static rule is a token hit; the B metrics report the Random Forest alone and Random Forest OR token hit. Compare using the same test sessions and disclose the positive-label definition.
- For a paper-faithful reproduction, deploy the staged SDV HMA data, implement and document the paper's actual deployment strategy, and reproduce its human believability evaluation. For a stronger ML claim, collect approved, independently labeled benign/attack sessions and evaluate on users/time periods not present in training.
