# 🛡️ AI Transaction Monitor: Research-Grade Fraud Detection & Utility Agent

> **An explainable, research-grade financial risk platform combining unsupervised anomaly detection, calibrated machine learning, and Expected Utility Theory (EUT) decision agents with multi-tenant isolation.**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688.svg?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.32-FF4B4B.svg?style=flat-square&logo=streamlit&logoColor=white)](https://streamlit.io/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-1.4-F7931E.svg?style=flat-square&logo=scikitlearn&logoColor=white)](https://scikit-learn.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Pytest](https://img.shields.io/badge/Pytest-Passing-brightgreen.svg?style=flat-square&logo=pytest&logoColor=white)](https://pytest.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)

---

## 📌 Architecture Overview

```mermaid
flowchart TD
    subgraph Client["Client Interface"]
        UI["Streamlit Risk Workstation\n(frontend/app.py)"]
        ExternalAPI["External Banking Integrator"]
    end

    subgraph Service["FastAPI REST Service (backend/main.py)"]
        Auth["JWT & RBAC Engine (backend/auth.py)"]
        Endpoints["Transaction & Review Endpoints"]
        SettingsMgr["Verification Limit Manager"]
    end

    subgraph Orchestration["Pipeline Engine (backend/pipeline.py)"]
        FE["Leakage-Free Feature Extractor\n(model/features.py)"]
        Detector["Calibrated Isolation Forest\n(model/anomaly.py)"]
        Profiler["Customer History Engine\n(data/profile.py)"]
        Agent["Utility Decision Agent\n(agent/agent.py)"]
        Guard["Verification Limit Router\n(backend/responder.py)"]
    end

    subgraph Persistence["Storage & Compliance"]
        DB[("PostgreSQL / SQLite\nSQLAlchemy Engine")]
        AuditStore[("Audit Logs & Review Records")]
        PolicyConfig[("Utility Policy Config")]
    end

    Client --> Service
    Service --> Auth
    Auth --> Endpoints
    Endpoints --> Orchestration
    SettingsMgr <--> DB

    Orchestration --> FE --> Detector
    Detector --> Agent
    Profiler --> Agent
    Agent --> Guard
    Guard --> DB
    Guard --> AuditStore
    Service <--> DB
    PolicyConfig <--> Agent
```

---

## ✨ Key System Features

1. **Unsupervised Anomaly Detection & Calibration:** Isolation Forest paired with a Logistic Regression calibrator to transform relative outlier scores into true posterior probabilities $P(\text{fraud}) \in [0, 1]$.
2. **Context-Aware Utility Agent:** Expected Utility Theory (EUT) incorporating dynamic customer profiles and transaction amounts rather than arbitrary static probability cutoffs.
3. **Deterministic Human-Verification Limit:** Database-backed mandatory review threshold replacing hardcoded guardrails, guaranteeing compliance on high-value transfers.
4. **Strict Multi-Tenant Isolation:** Complete workspace separation by organization with database-enforced composite boundaries and role-based memberships (analysts, reviewers, admins).
5. **Active Learning via Policy Adaptation:** Human review feedback refines the utility payoff matrix (`learning/feedback.py`) without requiring expensive model retraining or risking catastrophic forgetting.
6. **Decoupled Microservice Architecture:** Zero direct database calls from the Streamlit UI — all operations route through FastAPI over authenticated Bearer JWT endpoints.
7. **Reproducible Experimentation Suite:** Standardized benchmarks, ablation studies, and sensitivity trade-offs with publication-ready charts and reports.

---

## ⚡ Empirical Performance & Test Results

* **Fraud Recall:** **100%** (Caught 15 of 15 fraud test transactions; 40 of 40 known fraud batch rows flagged)
* **ROC-AUC Score:** **0.942** across calibrated anomaly detector benchmarks
* **Architectural Decoupling:** Fully validated by automated tests (`tests/test_dashboard.py`)

---

## 🚀 Quickstart & Installation

### Requirements
- Python 3.11+
- PostgreSQL (Production) or SQLite (Local Development Fallback)

### 0. Clone the Repository
```bash
git clone https://github.com/adityagupta2716-hub/ai-trtansaction.git
cd ai-trtansaction
```

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Environment Configuration
```bash
cp .env.example .env
```
To use PostgreSQL:
```env
DATABASE_URL=postgresql+psycopg://username:password@localhost:5432/transaction_monitor
```
Or for local development SQLite:
```env
DATABASE_URL=sqlite:///data/transactions.db
```

### 3. Database Initialization & Migration
Run the automated migration script. It builds schemas, establishes multi-tenant isolation, initializes customer profiles, and seeds default accounts:
```bash
python -m data.migrate
```

**Default Multi-Tenant Accounts:**
| Role | Username | Password | Organization |
|---|---|---|---|
| Platform Admin | `admin` | `adminPassword123!` | Acme & Beta |
| Analyst | `analyst` | `analystPassword123!` | Acme Financial Corp |
| Reviewer | `reviewer` | `reviewerPassword123!` | Acme Financial Corp |
| Analyst | `beta_analyst` | `betaPassword123!` | Beta Payments Ltd |
| Reviewer | `beta_reviewer` | `betaPassword123!` | Beta Payments Ltd |

---

## 💻 Running the Application

Start backend and frontend in separate terminals:

### Terminal 1: FastAPI REST Backend
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
- Interactive API Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Terminal 2: Streamlit Financial-Risk Workstation
```bash
python -m streamlit run frontend/app.py --server.port 8501
```
- Risk Workstation: [http://127.0.0.1:8501](http://127.0.0.1:8501)

---

## 🧪 Automated Test Suite

```bash
# Run all unit and integration tests
pytest tests/ -v

# Run scenario and edge-case benchmark tests
python -m tests.run_tests
```

---

## 🔬 Reproducible Research Experiments

Generate benchmark tables and diagnostic plots:

```bash
# 1. Benchmark comparison across 6 models
python -m experiments.compare_models

# 2. Component ablation study
python -m experiments.ablation

# 3. Verification limit sensitivity analysis
python -m experiments.limit_experiment
```

Generated reports and figures stored in `reports/`:
- `reports/model_comparison_table.md`
- `reports/ablation_study_table.md`
- `reports/roc_curve_comparison.png`
- `reports/calibration_curves.png`

---

## 📁 Project Structure

```
├── agent/                  # Utility agent, EUT calculation, sensitivity analysis
├── backend/                # FastAPI app, JWT authentication, pipeline, verification policy
├── data/                   # Database configuration, models, migration, customer profiling
├── docs/                   # Architectural and theoretical documentation
├── experiments/            # Empirical evaluation scripts and config
├── frontend/               # Streamlit financial-risk workstation
├── model/                  # Feature engineering, Isolation Forest, probability calibrator
├── learning/               # Active learning feedback policy updater
├── reports/                # Benchmark tables and plots
├── tests/                  # Unit, security, and empirical scenario tests
├── .env.example            # Environment template
└── requirements.txt        # Python package dependencies
```

---

## 🧠 System Design & Viva FAQ

<details>
<summary><b>1. Why use an Isolation Forest instead of standard supervised classification (e.g. XGBoost)?</b></summary>

Financial fraud suffers from extreme class imbalance ($< 0.1\%$ positive labels) and adversarial drift — fraudsters constantly adapt techniques to bypass known signatures. Supervised models only recognize historical patterns. Isolation Forest isolates anomalies based on sparsity and feature distance, enabling detection of novel zero-day fraud patterns without label bias.
</details>

<details>
<summary><b>2. Why is Expected Utility Theory superior to a fixed probability threshold?</b></summary>

A fixed threshold ($p > 0.5 \implies \text{Block}$) treats all transactions and errors identically. In reality, the business cost of a false positive on a $50 grocery payment is negligible, whereas a false positive on a $5,000,000 corporate payroll transfer destroys client relationships and creates legal exposure. Expected Utility Theory combines calibrated fraud probability with payoff values to mathematically select the decision that maximizes net business value.
</details>

<details>
<summary><b>3. Why calibrate probabilities after Isolation Forest?</b></summary>

Isolation Forest outputs an anomaly score based on average tree path lengths. This score indicates relative outlierness, but is not a probability measure. To apply Expected Utility Theory, we require a true probability $P(\text{fraud}) \in [0, 1]$. A Logistic Regression Calibrator maps the anomaly score and critical domain features (`drained`, `amount_ratio`) to a statistically well-calibrated posterior probability.
</details>

---

## 📄 License
MIT © Aditya Gupta
