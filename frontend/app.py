import os
import sys
from pathlib import Path
from datetime import datetime

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="AI Transaction Monitor | Multi-Tenant Fraud Risk Platform",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom High-Contrast, Clip-Free Modern Financial Styling
st.markdown("""
<style>
/* Root layout and typography */
.block-container {
    padding-top: 1.5rem;
    padding-bottom: 2.5rem;
}

/* ============================================================
   TAB NAVIGATION — VERTICAL CLIPPING FIX (v3, root-cause)

   Streamlit 1.65 DOM structure (from JS source inspection):
     [data-testid="stTabs"]        ← outer wrapper (jf, e1ac7blb0)
       └── div                     ← column flex wrapper (Nf, e1ac7blb2)
           └── div (gc/Pf)         ← scroll container   (Pf, e1ac7blb3)
               └── [data-baseweb="tab-list"]
                   └── [data-baseweb="tab"]

   The ACTUAL clipper is the Pf scroll container which JS source sets:
       overflowX: `auto`, overflowY: `clip`

   overflow-y:clip is a paint-clipping boundary — children cannot
   escape it with overflow:visible. Emoji ascenders (🏠📜👤 etc.)
   and font metrics extend above the container top, so they are cut.

   Fix strategy:
   1. Override overflow-y on the Pf container via its structural
      position: [data-testid="stTabs"] > div > div
   2. Add padding-top to the tab-list so ascenders have headroom
      INSIDE the container before it scrolls
   3. Keep overflow-x:auto intact so horizontal scrolling works
   ============================================================ */

/* 1. The Pf scroll container — this is the ACTUAL vertical clipper.
      Structural path: stTabs > first div child > first div child */
[data-testid="stTabs"] > div > div {
    overflow-y: visible !important;
    padding-top: 8px !important;
}

/* 2. The outer stTabs wrapper can also clip when height is set */
[data-testid="stTabs"] {
    overflow: visible !important;
}

/* 3. The Nf column flex wrapper */
[data-testid="stTabs"] > div {
    overflow: visible !important;
}

/* 4. The BaseWeb tab-list itself */
[data-baseweb="tab-list"] {
    overflow: visible !important;
    padding-top: 4px !important;
    padding-bottom: 0 !important;
    align-items: flex-end !important;
}

/* 5. Individual tab buttons */
[data-baseweb="tab"] {
    font-size: 14px !important;
    font-weight: 600 !important;
    padding: 8px 16px !important;
    white-space: nowrap !important;
    overflow: visible !important;
    height: auto !important;
    min-height: 44px !important;
    line-height: 1.6 !important;
    color: #374151 !important;
    background: transparent !important;
    border: none !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
}

/* 6. Inner label wrapper inside each tab button */
[data-baseweb="tab"] > div,
[data-baseweb="tab"] > span {
    overflow: visible !important;
    line-height: 1.6 !important;
}

/* 7. Active tab color */
[data-baseweb="tab"][aria-selected="true"] {
    color: #1d4ed8 !important;
}

/* 8. Animated underline highlight bar */
div[data-baseweb="tab-highlight"] {
    background-color: #1d4ed8 !important;
}

/* 9. Static border below the tab bar */
div[data-baseweb="tab-border"] {
    background-color: #e2e8f0 !important;
}


/* Card metrics */
[data-testid="stMetric"] {
    background: #f8fafc;
    padding: 14px 18px;
    border-radius: 10px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

[data-testid="stMetricLabel"] {
    font-size: 13px !important;
    font-weight: 600 !important;
    color: #64748b !important;
}

[data-testid="stMetricValue"] {
    font-size: 24px !important;
    font-weight: 700 !important;
    color: #0f172a !important;
}

/* Badges */
.risk-high {
    background-color: #fee2e2;
    color: #991b1b;
    padding: 3px 8px;
    border-radius: 6px;
    font-weight: 700;
}
.risk-med {
    background-color: #fef3c7;
    color: #92400e;
    padding: 3px 8px;
    border-radius: 6px;
    font-weight: 700;
}
.risk-low {
    background-color: #dcfce7;
    color: #166534;
    padding: 3px 8px;
    border-radius: 6px;
    font-weight: 700;
}

/* Tenant tag */
.tenant-pill {
    display: inline-block;
    background: #e0e7ff;
    color: #3730a3;
    padding: 4px 12px;
    border-radius: 9999px;
    font-size: 13px;
    font-weight: 700;
    margin-bottom: 12px;
}
</style>
""", unsafe_allow_html=True)

API_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

# -------------------------------------------------------------
# Session & State Management
# -------------------------------------------------------------
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "token" not in st.session_state:
    st.session_state["token"] = None
if "username" not in st.session_state:
    st.session_state["username"] = None
if "role" not in st.session_state:
    st.session_state["role"] = None
if "org_id" not in st.session_state:
    st.session_state["org_id"] = None
if "org_name" not in st.session_state:
    st.session_state["org_name"] = None
if "available_orgs" not in st.session_state:
    st.session_state["available_orgs"] = []

# -------------------------------------------------------------
# API Client Helpers
# -------------------------------------------------------------
def get_auth_headers():
    headers = {}
    if st.session_state.get("token"):
        headers["Authorization"] = f"Bearer {st.session_state['token']}"
    if st.session_state.get("org_id"):
        headers["X-Org-ID"] = str(st.session_state["org_id"])
    return headers

def api_get(path, **params):
    r = requests.get(API_URL + path, params=params, headers=get_auth_headers(), timeout=15)
    r.raise_for_status()
    return r.json()

def api_post(path, body=None):
    r = requests.post(API_URL + path, json=body, headers=get_auth_headers(), timeout=30)
    r.raise_for_status()
    return r.json()

# -------------------------------------------------------------
# Unauthenticated Login-First Flow
# -------------------------------------------------------------
if not st.session_state["authenticated"]:
    col_l, col_center, col_r = st.columns([1, 2, 1])
    with col_center:
        st.markdown("<h2 style='text-align: center;'>🛡️ AI Transaction Monitor</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #64748b;'>Enterprise Multi-Tenant Fraud Risk & Utility Decision Platform</p>", unsafe_allow_html=True)
        st.markdown("---")

        with st.container(border=True):
            st.subheader("Secure Enterprise Sign In")
            with st.form("login_form"):
                username_in = st.text_input("Username or Email", value="admin")
                password_in = st.text_input("Password", type="password", value="adminPassword123!")
                submit_btn = st.form_submit_button("Sign In to Workspace", use_container_width=True, type="primary")

                if submit_btn:
                    try:
                        res = requests.post(
                            f"{API_URL}/auth/login",
                            json={"username": username_in, "password": password_in},
                            timeout=10,
                        )
                        if res.status_code == 200:
                            data = res.json()
                            st.session_state["authenticated"] = True
                            st.session_state["token"] = data["access_token"]
                            st.session_state["username"] = data["username"]
                            st.session_state["role"] = data["role"]
                            st.session_state["org_id"] = data["org_id"]
                            st.session_state["org_name"] = data["org_name"]
                            st.session_state["available_orgs"] = data.get("available_organizations", [])
                            st.success(f"Authenticated as {data['username']} ({data['role'].upper()})")
                            st.rerun()
                        else:
                            st.error(res.json().get("detail", "Invalid username or password."))
                    except Exception as e:
                        st.error(f"Cannot connect to Backend API: {e}")

            st.caption("📋 Evaluation Credentials:")
            st.caption("• **Acme Admin:** `admin` / `adminPassword123!`")
            st.caption("• **Acme Analyst:** `analyst` / `analystPassword123!`")
            st.caption("• **Acme Reviewer:** `reviewer` / `reviewerPassword123!`")
            st.caption("• **Beta Analyst:** `beta_analyst` / `betaPassword123!`")
            st.caption("• **Beta Reviewer:** `beta_reviewer` / `betaPassword123!`")

    st.stop()

# -------------------------------------------------------------
# Authenticated Sidebar
# -------------------------------------------------------------
with st.sidebar:
    st.title("🛡️ AI Monitor")
    st.caption("Explainable Multi-Tenant Fraud Detection")

    st.markdown(f"<div class='tenant-pill'>🏢 {st.session_state['org_name']}</div>", unsafe_allow_html=True)
    st.write(f"User: **{st.session_state['username']}** (`{st.session_state['role'].upper()}`)")

    # Organization Switcher if user has multiple accessible orgs
    available_orgs = st.session_state.get("available_orgs", [])
    if len(available_orgs) > 1:
        org_names = [o["name"] for o in available_orgs]
        current_idx = 0
        for i, o in enumerate(available_orgs):
            if o["org_id"] == st.session_state["org_id"]:
                current_idx = i
                break

        selected_org_name = st.selectbox("Active Workspace", org_names, index=current_idx)
        selected_org_obj = next(o for o in available_orgs if o["name"] == selected_org_name)

        if selected_org_obj["org_id"] != st.session_state["org_id"]:
            # Trigger switch
            try:
                switch_res = api_post(f"/auth/switch-org/{selected_org_obj['org_id']}")
                st.session_state["token"] = switch_res["access_token"]
                st.session_state["org_id"] = switch_res["org_id"]
                st.session_state["org_name"] = switch_res["org_name"]
                st.session_state["role"] = switch_res["role"]
                st.rerun()
            except Exception as e:
                st.error(f"Failed to switch organization: {e}")

    if st.button("Sign Out", use_container_width=True):
        st.session_state["authenticated"] = False
        st.session_state["token"] = None
        st.session_state["username"] = None
        st.session_state["role"] = None
        st.session_state["org_id"] = None
        st.session_state["org_name"] = None
        st.session_state["available_orgs"] = []
        st.rerun()

    st.markdown("---")
    st.subheader("Tenant Compliance Limits")
    try:
        settings_data = api_get("/settings/verification-limit")
        ACTIVE_LIMIT = float(settings_data.get("limit", 500000.0))
        CURRENCY = settings_data.get("currency", "USD")
        POLICY_VERSION = settings_data.get("policy_version", "2.0.0")
    except Exception:
        ACTIVE_LIMIT = 500000.0
        CURRENCY = "USD"
        POLICY_VERSION = "2.0.0"

    st.metric(f"Verification Limit ({CURRENCY})", f"${ACTIVE_LIMIT:,.0f}")
    st.caption(f"Policy Active: **v{POLICY_VERSION}**")

    try:
        q_count = len(api_get("/review-queue"))
        a_count = len(api_get("/alerts"))
        st.metric("Pending Human Reviews", q_count)
        st.metric("Active System Alerts", a_count)
    except Exception:
        pass

# -------------------------------------------------------------
# Main Application: 9 Comprehensive Multi-Tenant Tabs
# -------------------------------------------------------------
(
    tab_overview,
    tab_history,
    tab_customers,
    tab_analysis,
    tab_review,
    tab_orgs,
    tab_settings,
    tab_eval,
    tab_audit,
) = st.tabs([
    "🏠 Overview",
    "📜 Transaction History",
    "👤 Customer Profiles",
    "🔍 Fraud Analysis",
    "🧑‍⚖️ Human-Review Queue",
    "🏢 Organizations & Users",
    "⚙️ Settings",
    "📊 Model Evaluation",
    "🛡️ Audit Trail",
])

# =============================================================
# Tab 1: Overview
# =============================================================
with tab_overview:
    st.subheader(f"Platform Health — {st.session_state['org_name']}")
    txns_sample = api_get("/transactions", limit=500)
    tx_df = pd.DataFrame(txns_sample) if txns_sample else pd.DataFrame()

    c1, c2, c3, c4 = st.columns(4)
    total_txns = len(tx_df)
    c1.metric("Recent Transactions Monitored", total_txns)
    c2.metric("Active Verification Limit", f"${ACTIVE_LIMIT:,.0f}")

    if not tx_df.empty:
        status_counts = tx_df["status"].value_counts()
        approved = status_counts.get("approve", 0)
        c3.metric("Auto-Approved Rate", f"{(approved / total_txns):.1%}")
        c4.metric("Flagged / Review Rate", f"{((total_txns - approved) / total_txns):.1%}")
    else:
        c3.metric("Auto-Approved Rate", "N/A")
        c4.metric("Flagged / Review Rate", "N/A")

    st.markdown("---")
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.markdown("**Transaction Status Breakdown**")
        if not tx_df.empty:
            st.bar_chart(tx_df["status"].value_counts())
        else:
            st.info("No transaction data available for this organization.")

    with col_right:
        st.markdown("**Monitored Transaction Types**")
        if not tx_df.empty:
            st.bar_chart(tx_df["type"].value_counts())
        else:
            st.info("No transaction data available for this organization.")

# =============================================================
# Tab 2: Transaction History
# =============================================================
with tab_history:
    st.subheader(f"Historical Records — {st.session_state['org_name']}")

    f1, f2, f3 = st.columns(3)
    filter_status = f1.selectbox("Filter Status", ["All", "approve", "hold", "escalate", "block", "pending_verification"])
    filter_type = f2.selectbox("Filter Type", ["All", "TRANSFER", "CASH_OUT", "PAYMENT"])
    filter_cust = f3.text_input("Filter Customer ID (optional)", "")

    params = {"limit": 100}
    if filter_status != "All":
        params["status"] = filter_status
    if filter_type != "All":
        params["tx_type"] = filter_type
    if filter_cust.isdigit():
        params["customer_id"] = int(filter_cust)

    history_records = api_get("/transactions", **params)
    if history_records:
        h_df = pd.DataFrame(history_records)
        st.dataframe(h_df, use_container_width=True, hide_index=True)
    else:
        st.info("No transactions found matching criteria in this organization.")

# =============================================================
# Tab 3: Customer Profiles
# =============================================================
with tab_customers:
    st.subheader(f"Customer Risk & Behavioral History — {st.session_state['org_name']}")
    cust_id_in = st.number_input("Enter Customer ID", min_value=1, value=1, step=1)

    if st.button("Load Customer Profile", type="primary"):
        try:
            profile = api_get(f"/customers/{cust_id_in}")
            st.session_state["active_profile"] = profile
        except Exception as e:
            st.error(f"Error fetching profile: {e}")

    profile = st.session_state.get("active_profile")
    if profile and profile.get("customer_id") == cust_id_in:
        st.markdown("---")
        risk_tier = profile["overall_risk"]
        color_class = "risk-high" if risk_tier == "HIGH" else ("risk-med" if risk_tier == "MEDIUM" else "risk-low")
        st.markdown(f"### Profile for Customer #{profile['customer_id']} — Risk Tier: <span class='{color_class}'>{risk_tier}</span>", unsafe_allow_html=True)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Lifetime Transactions", profile["num_transactions"])
        m2.metric("Total Volume", f"${profile['total_volume']:,.2f}")
        m3.metric("Average Amount", f"${profile['average_amount']:,.2f}")
        m4.metric("Frequency (txns/step)", f"{profile['frequency_per_step']:.2f}")

        st.markdown("#### Confirmed Ground-Truth Outcomes vs AI Alerts")
        c_a, c_b, c_c = st.columns(3)
        c_a.metric("Confirmed Fraud Cases", profile["confirmed_fraud_count"])
        c_b.metric("Confirmed Legitimate", profile["confirmed_legit_count"])
        c_c.metric("Unconfirmed AI Alerts", profile["ai_alert_count"])
        st.caption("⚠️ AI Alerts represent statistical anomalies, NOT confirmed fraud. Only verified human review findings constitute ground truth.")

        st.markdown("#### Active Risk Indicators & Evidence")
        if profile["risk_indicators"]:
            for ind in profile["risk_indicators"]:
                sev_icon = "🔴" if ind["severity"] == "HIGH" else ("🟡" if ind["severity"] == "MEDIUM" else "🟢")
                st.markdown(f"**{sev_icon} {ind['type']}** ({ind['severity']}): {ind['evidence']}")
        else:
            st.success("No active anomalous risk indicators detected for this customer.")

        st.markdown("#### Recent Transactions Timeline")
        if profile["recent_transactions"]:
            st.dataframe(pd.DataFrame(profile["recent_transactions"]), use_container_width=True, hide_index=True)

# =============================================================
# Tab 4: Fraud Analysis
# =============================================================
with tab_analysis:
    st.subheader(f"Risk Scoring & Explainability Inspector — {st.session_state['org_name']}")

    PRESETS = {
        "Normal Payment": ("PAYMENT", 45.0, 5000.0, 4955.0),
        "Drained Account (Transfer)": ("TRANSFER", 90000.0, 90000.0, 0.0),
        "Large Cash-Out": ("CASH_OUT", 120000.0, 120000.0, 0.0),
        "Exceeds Limit (> Limit)": ("TRANSFER", ACTIVE_LIMIT + 50000.0, ACTIVE_LIMIT + 100000.0, 50000.0),
    }

    cols = st.columns(len(PRESETS))
    for col, name in zip(cols, PRESETS):
        if col.button(name, key=f"btn_{name}"):
            t, a, o, n = PRESETS[name]
            st.session_state["p_type"] = t
            st.session_state["p_amount"] = a
            st.session_state["p_old"] = o
            st.session_state["p_new"] = n

    with st.form("manual_analysis_form"):
        r1, r2 = st.columns(2)
        c_id = r1.number_input("Customer ID", min_value=1, value=1)
        tx_t = r2.selectbox("Type", ["TRANSFER", "CASH_OUT", "PAYMENT"], index=["TRANSFER", "CASH_OUT", "PAYMENT"].index(st.session_state.get("p_type", "TRANSFER")))
        amt = r1.number_input("Amount", min_value=0.01, value=float(st.session_state.get("p_amount", 90000.0)))
        old_b = r2.number_input("Pre-Transaction Balance", min_value=0.0, value=float(st.session_state.get("p_old", 90000.0)))
        new_b = r1.number_input("Post-Transaction Balance", min_value=0.0, value=float(st.session_state.get("p_new", 0.0)))
        submit_eval = st.form_submit_button("Submit & Score Transaction", type="primary")

    if submit_eval:
        try:
            res = api_post("/submit", {
                "customer_id": int(c_id),
                "type": tx_t,
                "amount": float(amt),
                "old_balance": float(old_b),
                "new_balance": float(new_b),
            })
            st.session_state["eval_result"] = res
        except Exception as exc:
            st.error(f"Analysis failed: {exc}")

    eval_res = st.session_state.get("eval_result")
    if eval_res:
        st.markdown("---")
        dec = eval_res["decision"]
        dec_color = "success" if dec == "approve" else ("warning" if dec in ("hold", "escalate", "pending_verification") else "error")
        getattr(st, dec_color)(f"Decision: **{dec.upper()}** (Decided by: `{eval_res.get('decided_by', 'agent')}`)")

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Anomaly Score", f"{eval_res.get('anomaly_score', 0.0):.3f}")
        k2.metric("Calibrated P(Fraud)", f"{eval_res.get('p_fraud', 0.0):.1%}")
        k3.metric("Decision Margin", f"{eval_res.get('decision_margin', eval_res.get('confidence', 0.0)):.2f}")
        k4.metric("Active Limit L", f"${eval_res.get('active_limit', ACTIVE_LIMIT):,.0f}")

        st.markdown("**Explainability & Contributing Factors**")
        st.info(eval_res.get("reasoning", "No explanation provided."))

        st.markdown("**Expected Utility of Evaluated Actions**")
        eu_dict = eval_res.get("expected_utilities", {})
        if eu_dict:
            st.bar_chart(pd.DataFrame({"Expected Utility": eu_dict}))

# =============================================================
# Tab 5: Human-Review Queue
# =============================================================
with tab_review:
    st.subheader(f"Mandatory Review Queue — {st.session_state['org_name']}")
    st.caption("Transactions routed due to mandatory human verification limits or AI escalation require human sign-off.")

    queue = api_get("/review-queue")
    if not queue:
        st.success("🎉 All caught up! No transactions currently pending human review in this workspace.")
    else:
        st.write(f"Total pending cases: **{len(queue)}**")
        for item in queue[:15]:
            tid = item["transaction_id"]
            with st.expander(f"Case #{tid} — {item['type']} | Amount: ${item['amount']:,.2f} | Status: {item['status'].upper()}", expanded=True):
                r_col1, r_col2 = st.columns([2, 1])
                with r_col1:
                    st.write(f"**Customer ID:** {item['customer_id']} | **Old Balance:** ${item['old_balance']:,.2f} | **New Balance:** ${item['new_balance']:,.2f}")
                with r_col2:
                    is_over_limit = item["amount"] > ACTIVE_LIMIT
                    if is_over_limit:
                        st.warning(f"⚠️ Exceeds Verification Limit (${ACTIVE_LIMIT:,.0f})")

                with st.form(f"review_form_{tid}"):
                    rf_col1, rf_col2, rf_col3 = st.columns(3)
                    rev_outcome = rf_col1.selectbox("Review Outcome", ["approve", "block", "unresolved"], key=f"outcome_{tid}")
                    fraud_conf = rf_col2.selectbox("Confirmed Fraud?", ["Unresolved / Unknown", "Confirmed Legitimate (0)", "Confirmed Fraud (1)"], key=f"fraud_{tid}")
                    reason_text = st.text_input("Reviewer Justification", value="Reviewed KYC and transaction context.", key=f"reason_{tid}")
                    submit_rev = st.form_submit_button("Submit Review Judgment", type="primary")

                    if submit_rev:
                        if st.session_state["role"] not in ("reviewer", "admin", "org_admin"):
                            st.error("Permission denied: You must hold the 'reviewer' or 'admin' role to submit judgments.")
                        else:
                            conf_val = 1 if "Confirmed Fraud" in fraud_conf else (0 if "Confirmed Legitimate" in fraud_conf else None)
                            try:
                                api_post(f"/review/{tid}", {
                                    "review_outcome": rev_outcome,
                                    "fraud_confirmed": conf_val,
                                    "review_reason": reason_text,
                                })
                                st.success(f"Review for Case #{tid} saved successfully.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to submit review: {e}")

# =============================================================
# Tab 6: Organization & User Management
# =============================================================
with tab_orgs:
    st.subheader(f"Organization & Membership Management")
    st.caption("Manage tenant workspaces, roles, and authorized members.")

    is_org_admin = st.session_state["role"] in ("admin", "org_admin", "platform_admin")

    col_m_list, col_m_add = st.columns([2, 1])
    with col_m_list:
        st.markdown(f"#### Active Members of `{st.session_state['org_name']}`")
        try:
            members = api_get(f"/organizations/{st.session_state['org_id']}/members")
            if members:
                st.dataframe(pd.DataFrame(members), use_container_width=True, hide_index=True)
            else:
                st.info("No members found.")
        except Exception as e:
            st.error(f"Cannot load members: {e}")

    with col_m_add:
        if is_org_admin:
            st.markdown("#### Add Member to Workspace")
            with st.form("add_member_form"):
                new_uname = st.text_input("Existing Username to Add")
                new_role = st.selectbox("Assign Role", ["analyst", "reviewer", "org_admin"])
                add_sub = st.form_submit_button("Add Member", type="primary")

                if add_sub:
                    try:
                        api_post(f"/organizations/{st.session_state['org_id']}/members", {
                            "username": new_uname,
                            "role": new_role,
                        })
                        st.success(f"User '{new_uname}' added to organization as {new_role}.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to add member: {e}")
        else:
            st.info("🔒 You need the 'org_admin' role to invite or manage members.")

# =============================================================
# Tab 7: Settings
# =============================================================
with tab_settings:
    st.subheader(f"Tenant Compliance & Policy Settings — {st.session_state['org_name']}")
    st.caption("Manage database-backed operational thresholds. All changes are permanently recorded in the tenant audit log.")

    is_admin = st.session_state["role"] in ("admin", "org_admin", "platform_admin")
    if not is_admin:
        st.warning("🔒 Administrative privileges required to modify compliance settings.")

    current_cfg = api_get("/settings/verification-limit")
    cur_limit = float(current_cfg.get("limit", 500000.0))

    st.write(f"**Active Human-Verification Limit:** `${cur_limit:,.2f} {current_cfg.get('currency', 'USD')}`")
    st.write(f"**Policy Version:** `{current_cfg.get('policy_version', '2.0.0')}`")

    if is_admin:
        with st.form("limit_update_form"):
            new_l = st.number_input("New Human-Verification Limit ($)", min_value=100.0, value=cur_limit, step=10000.0)
            update_btn = st.form_submit_button("Update Limit", type="primary")

            if update_btn:
                try:
                    res = api_post("/settings/verification-limit", {"new_limit": float(new_l)})
                    st.success(f"Verification limit successfully updated from ${res['old_limit']:,.2f} to ${res['new_limit']:,.2f}.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Update failed: {e}")

    st.markdown("---")
    st.subheader("Active Learning & Expected Utility Adaptation")
    st.caption("Re-adapts the agent's expected utility matrix using ground-truth reviewer feedback saved in the database.")
    if st.button("Adapt Utility Policy From Feedback"):
        try:
            fb_res = api_post("/feedback/learn")
            st.success("Utility policy updated successfully!")
            st.dataframe(pd.DataFrame(fb_res["updated_utility"]).T, use_container_width=True)
        except Exception as e:
            st.error(f"Policy adaptation failed: {e}")

# =============================================================
# Tab 8: Model Evaluation
# =============================================================
with tab_eval:
    st.subheader("Empirical Research Benchmarks & Model Comparisons")
    st.caption("Generated directly from reproducible evaluation experiments on held-out test data.")

    rep_dir = ROOT_DIR / "reports"
    bench_file = rep_dir / "model_comparison_table.csv"
    abl_file = rep_dir / "ablation_study_table.csv"
    lim_file = rep_dir / "limit_experiment_table.csv"

    if bench_file.exists():
        st.markdown("#### 1. Baseline Model Comparison")
        st.dataframe(pd.read_csv(bench_file), use_container_width=True, hide_index=True)
    else:
        st.info("Run `python -m experiments.compare_models` to generate baseline benchmarks.")

    if abl_file.exists():
        st.markdown("#### 2. Ablation Study Results")
        st.dataframe(pd.read_csv(abl_file), use_container_width=True, hide_index=True)

    if lim_file.exists():
        st.markdown("#### 3. Verification Limit Sensitivity Analysis")
        st.dataframe(pd.read_csv(lim_file), use_container_width=True, hide_index=True)

    st.markdown("#### 4. Diagnostic Curves")
    img_col1, img_col2 = st.columns(2)
    roc_img = rep_dir / "roc_curve_comparison.png"
    pr_img = rep_dir / "pr_curve_comparison.png"
    calib_img = rep_dir / "calibration_curves.png"
    lim_img = rep_dir / "limit_tradeoff_plot.png"

    if roc_img.exists():
        img_col1.image(str(roc_img), caption="Comparative ROC Curves")
    if pr_img.exists():
        img_col2.image(str(pr_img), caption="Precision-Recall Curves")
    if calib_img.exists():
        img_col1.image(str(calib_img), caption="Reliability Diagram (Calibration)")
    if lim_img.exists():
        img_col2.image(str(lim_img), caption="Review Workload vs Decision Cost Trade-off")

# =============================================================
# Tab 9: Audit Trail
# =============================================================
with tab_audit:
    st.subheader(f"System Audit Trail — {st.session_state['org_name']}")
    st.caption("Immutable log of AI decisions, human reviews, guardrail limit overrides, and administrative changes.")

    try:
        audit_records = api_get("/audit-logs", limit=150)
        if audit_records:
            a_df = pd.DataFrame(audit_records)
            st.dataframe(a_df[["id", "created_at", "actor_type", "actor_id", "action", "entity_type", "entity_id", "details"]], use_container_width=True, hide_index=True)
        else:
            st.info("No audit logs recorded yet for this organization.")
    except Exception as e:
        st.error(f"Could not load audit log: {e}")