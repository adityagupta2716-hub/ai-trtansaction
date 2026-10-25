# AI Transaction Monitor: Research-Grade Fraud Detection & Utility Agent

A reproducible, explainable, research-grade financial fraud detection platform combining:
1. **Unsupervised Anomaly Detection & Calibration:** Isolation Forest + Logistic Regression calibrator.
2. **Context-Aware Utility Agent:** Expected Utility Theory (EUT) incorporating dynamic customer profiles.
3. **Deterministic Human-Verification Limit:** Database-backed mandatory review threshold replacing hardcoded guardrails.
4. **Strict Multi-Tenant Isolation:** Complete workspace separation by organization with database-enforced composite boundaries and role-based memberships.
5. **Active Learning via Policy Adaptation:** Human review feedback refines the utility payoff matrix without catastrophic model forgetting.
6. **Role-Based Financial Risk Workstation:** FastAPI backend and Streamlit multi-tenant compliance dashboard with clip-free navigation styling.
7. **Reproducible Experimentation Suite:** Standardized benchmarks, ablation studies, and sensitivity trade-offs.

---

## 1. Quick Start & Installation

### Requirements
- Python 3.11+
- PostgreSQL (Production) or SQLite (Local Development Fallback)

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
To use PostgreSQL, set:
```env
DATABASE_URL=postgresql+psycopg://username:password@localhost:5432/transaction_monitor
```
Or use the local development SQLite database:
```env
DATABASE_URL=sqlite:///data/transactions.db
```

### Step 3: Database Initialization & Migration
Run the automated migration script. It automatically builds the schema, establishes multi-tenant isolation, migrates legacy records without data loss, initializes customer profiles, and seeds default accounts and settings:
```bash
python -m data.migrate
```

Default Multi-Tenant Accounts:
- **Platform / Acme Admin:** `admin` / `adminPassword123!` (Access to Acme & Beta workspaces)
- **Acme Analyst:** `analyst` / `analystPassword123!` (Acme Financial Corp)
- **Acme Reviewer:** `reviewer` / `reviewerPassword123!` (Acme Financial Corp)
- **Beta Analyst:** `beta_analyst` / `betaPassword123!` (Beta Payments Ltd)
- **Beta Reviewer:** `beta_reviewer` / `betaPassword123!` (Beta Payments Ltd)

---

## 2. Running the Application

Start the backend and frontend in two separate terminals from the project root:

### Terminal 1: FastAPI REST Backend
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
- Interactive API Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Terminal 2: Streamlit Financial-Risk Workstation
```bash
python -m streamlit run frontend/app.py --server.port 8501
```
- Open [http://127.0.0.1:8501](http://127.0.0.1:8501) and sign in using one of the seeded accounts.

---

## 3. Automated Test Suite

Run the full automated test suite (structural tests, security tests, verification limits, Expected Utility, and leakage prevention):

```bash
# Run all unit and integration tests
pytest tests/ -v

# Run scenario and edge-case benchmark tests
python -m tests.run_tests
```

---

## 4. Reproducible Research Experiments

Run the research experimentation framework to generate publication-quality benchmark tables and diagnostic plots:

```bash
# 1. Benchmark comparison across 6 models
python -m experiments.compare_models

# 2. Component ablation study
python -m experiments.ablation

# 3. Verification limit sensitivity analysis
python -m experiments.limit_experiment
```

All generated tables (`.csv`, `.md`) and plots (`.png`) are stored in `reports/`:
- `reports/model_comparison_table.md`
- `reports/ablation_study_table.md`
- `reports/limit_experiment_table.md`
- `reports/roc_curve_comparison.png`
- `reports/pr_curve_comparison.png`
- `reports/calibration_curves.png`
- `reports/limit_tradeoff_plot.png`

---

## 5. System Documentation

- [System Architecture & RBAC](docs/architecture.md)
- [Detection & Decision Methodology](docs/methodology.md)
- [Empirical Experiments & Benchmarks](docs/experiments.md)
- [Assumptions, Limitations & Governance](docs/limitations.md)

---

## 6. Project Layout

```
├── agent/                  # Utility agent, EUT calculation, sensitivity analysis
├── backend/                # FastAPI app, authentication, pipeline, verification limit policy
├── data/                   # Database configuration, models, migration, customer profiling
├── docs/                   # Academic and architectural documentation
├── experiments/            # Reproducible empirical evaluation scripts and config
├── frontend/               # Streamlit financial-risk workstation
├── model/                  # Feature engineering, Isolation Forest, calibrator
├── learning/               # Active learning feedback policy updater
├── reports/                # Generated research benchmark tables and plots
├── tests/                  # Unit, security, and empirical scenario tests
├── .env.example            # Environment template
└── requirements.txt        # Python package dependencies
```
