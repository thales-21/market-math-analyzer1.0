import json
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

try:
    from supabase import create_client, Client
except Exception:
    create_client = None
    Client = Any

st.set_page_config(page_title="Atlas V2", page_icon="☀️", layout="wide")

# =========================
# APP STYLING
# =========================
st.markdown(
    """
<style>
    .main-title {
        font-size: 2.1rem;
        font-weight: 800;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        color: #9fb0c6;
        margin-bottom: 1rem;
    }
    .atlas-card {
        border: 1px solid rgba(49,130,206,0.35);
        border-radius: 18px;
        padding: 1rem 1.1rem;
        background: linear-gradient(180deg, rgba(15,23,42,0.92) 0%, rgba(9,15,28,0.96) 100%);
        box-shadow: 0 0 24px rgba(59,130,246,0.08);
    }
    .atlas-kpi {
        border: 1px solid rgba(59,130,246,0.25);
        border-radius: 16px;
        padding: 0.8rem 1rem;
        background: rgba(2,6,23,0.7);
        min-height: 108px;
    }
    .atlas-kpi .label {
        color: #9fb0c6;
        font-size: 0.95rem;
    }
    .atlas-kpi .value {
        color: #dbeafe;
        font-size: 1.8rem;
        font-weight: 800;
        margin-top: 0.2rem;
    }
    .atlas-kpi .detail {
        color: #60a5fa;
        font-size: 0.9rem;
        margin-top: 0.3rem;
    }
    .small-note {
        color: #93a4bd;
        font-size: 0.9rem;
    }
    .section-header {
        font-size: 1.25rem;
        font-weight: 700;
        margin-top: 0.4rem;
        margin-bottom: 0.6rem;
    }
    .pill {
        display: inline-block;
        padding: 0.35rem 0.65rem;
        border-radius: 999px;
        margin-right: 0.4rem;
        background: rgba(30,64,175,0.2);
        border: 1px solid rgba(96,165,250,0.25);
        color: #bfdbfe;
        font-size: 0.85rem;
        font-weight: 600;
    }
</style>
""",
    unsafe_allow_html=True,
)

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

SUPABASE_URL = st.secrets.get("SUPABASE_URL", "") if hasattr(st, "secrets") else ""
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "") if hasattr(st, "secrets") else ""

# =========================
# AUTH
# =========================
DEMO_USERS = {
    "atlas_admin": {"password": "AtlasSecure2026!", "name": "Atlas Admin", "role": "Admin"},
    "atlas_sales": {"password": "SolarField2026!", "name": "Atlas Sales", "role": "Sales"},
}


def get_users():
    try:
        secret_users = st.secrets.get("auth_users", {})
        if secret_users:
            normalized = {}
            for username, payload in secret_users.items():
                normalized[username] = {
                    "password": payload.get("password", ""),
                    "name": payload.get("name", username),
                    "role": payload.get("role", "User"),
                }
            return normalized
    except Exception:
        pass
    return DEMO_USERS



def login_panel():
    users = get_users()
    st.markdown('<div class="main-title">Atlas V2 — Eastern Washington Solar OS</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-title">Private CRM for Atlas Solar • Lead Intelligence • Pipeline • ROI • Routes • Eastern Washington</div>',
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([1.2, 1])
    with c1:
        st.markdown('<div class="atlas-card">', unsafe_allow_html=True)
        st.markdown("### Sign in")
        username = st.text_input("Username", placeholder="atlas_admin")
        password = st.text_input("Password", type="password", placeholder="••••••••")
        col_a, col_b = st.columns([1, 1])
        with col_a:
            login_clicked = st.button("Log in", use_container_width=True)
        with col_b:
            if st.button("Load demo credentials", use_container_width=True):
                st.info("Demo users are listed in the panel to the right.")
        if login_clicked:
            user = users.get(username)
            if user and password == user["password"]:
                st.session_state["authenticated"] = True
                st.session_state["username"] = username
                st.session_state["name"] = user["name"]
                st.session_state["role"] = user["role"]
                st.rerun()
            st.error("Invalid username or password.")
        st.markdown("</div>", unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="atlas-card">', unsafe_allow_html=True)
        st.markdown("### Private V2 access")
        st.markdown(
            """
**Default demo users**
- `atlas_admin` / `AtlasSecure2026!`
- `atlas_sales` / `SolarField2026!`

Replace these in `/.streamlit/secrets.toml` before any real deployment.
"""
        )
        st.markdown(
            """
<div class="small-note">
This merge keeps the V1 Eastern Washington niche and satellite map, then layers in
ROI, route planning, proposal generation, and optional CRM persistence.
</div>
""",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)



def logout_button():
    if st.sidebar.button("Log out", use_container_width=True):
        for key in ["authenticated", "username", "name", "role", "selected_prospect_id"]:
            st.session_state.pop(key, None)
        st.rerun()


# =========================
# DATA GENERATION / STORAGE
# =========================
COUNTY_CENTERS = {
    "Benton": (46.2857, -119.2845),
    "Franklin": (46.2396, -119.1006),
    "Yakima": (46.6021, -120.5059),
    "Walla Walla": (46.0646, -118.3430),
    "Grant": (47.1301, -119.2781),
    "Adams": (46.9754, -118.5602),
}

CITY_BY_COUNTY = {
    "Benton": ["Richland", "Kennewick", "West Richland", "Prosser"],
    "Franklin": ["Pasco", "Connell", "Mesa"],
    "Yakima": ["Yakima", "Sunnyside", "Grandview", "Toppenish"],
    "Walla Walla": ["Walla Walla", "College Place"],
    "Grant": ["Moses Lake", "Quincy"],
    "Adams": ["Othello", "Ritzville"],
}

UTILITIES = {
    "Benton": ["Benton PUD", "City Utility"],
    "Franklin": ["Franklin PUD", "Pacific Power"],
    "Yakima": ["Pacific Power", "Yakima Valley Utility"],
    "Walla Walla": ["Pacific Power", "Columbia REA"],
    "Grant": ["Grant PUD"],
    "Adams": ["Adams County PUD", "Columbia REA"],
}

PROPERTY_TYPES = [
    ("Residential", 0.65),
    ("Commercial", 0.18),
    ("Agricultural", 0.10),
    ("Industrial", 0.07),
]

PIPELINE_STAGES = [
    "New Lead",
    "Contact Attempted",
    "Contact Made",
    "Qualified",
    "Site Review Scheduled",
    "Proposal Sent",
    "Negotiation",
    "Won",
    "Lost",
]

LEAD_SOURCES = ["Public Parcel", "Business List", "Referral", "Walk-In", "Campaign"]
REPS = ["Atlas Admin", "Atlas Sales", "Unassigned"]


@dataclass
class SolarScoreResult:
    solar_potential_score: float
    annual_kwh_estimate: float
    annual_savings_usd: float
    payback_years: float
    roi_20yr_pct: float
    recommended_system_kw: float
    confidence: float


class SupabaseService:
    """Real CRM persistence layer for Atlas.

    This uses the Supabase tables you created:
    companies, activities, tasks, stage_history.
    If Supabase is unavailable, the rest of Atlas V2 still runs in local demo mode.
    """

    def __init__(self, url: str, key: str):
        self.enabled = bool(url and key and create_client)
        self.client: Optional[Client] = None
        self.error: Optional[str] = None
        if self.enabled:
            try:
                self.client = create_client(url, key)
            except Exception as exc:
                self.enabled = False
                self.error = str(exc)

    def _safe_execute(self, query, fallback=None):
        if not self.enabled or not self.client:
            return fallback
        try:
            result = query.execute()
            return result.data if hasattr(result, "data") else fallback
        except Exception as exc:
            self.error = str(exc)
            return fallback

    # ---------- Companies ----------
    def fetch_companies(self):
        return self._safe_execute(
            self.client.table("companies").select("*").order("created_at", desc=True),
            fallback=[],
        ) or []

    def create_company(self, payload: Dict[str, Any]):
        if not self.enabled:
            return None
        data = self._safe_execute(self.client.table("companies").insert(payload), fallback=[])
        if not data:
            return None
        company = data[0]
        actor = payload.get("assigned_rep") or st.session_state.get("name", "System")
        self.add_activity(company["id"], "Lead Created", f"Lead created: {company.get('company_name', 'Unknown')}", "", actor)
        self.add_stage_history(company["id"], None, company.get("stage", "New Lead"), actor)
        return company

    def update_company(self, company_id: str, updates: Dict[str, Any], actor: str = "System"):
        if not self.enabled:
            return None
        current = self._safe_execute(
            self.client.table("companies").select("*").eq("id", company_id).single(),
            fallback=None,
        )
        old_stage = current.get("stage") if isinstance(current, dict) else None
        data = self._safe_execute(self.client.table("companies").update(updates).eq("id", company_id), fallback=[])
        new_stage = updates.get("stage", old_stage)
        if old_stage and new_stage != old_stage:
            self.add_stage_history(company_id, old_stage, new_stage, actor)
            self.add_activity(company_id, "Stage Changed", f"Moved from {old_stage} to {new_stage}", "", actor)
        return data

    def find_company_by_email_or_name(self, email: str, company_name: str):
        if not self.enabled:
            return None
        if email:
            data = self._safe_execute(self.client.table("companies").select("*").eq("email", email).limit(1), fallback=[])
            if data:
                return data[0]
        if company_name:
            data = self._safe_execute(self.client.table("companies").select("*").eq("company_name", company_name).limit(1), fallback=[])
            if data:
                return data[0]
        return None

    def upsert_lead_snapshot(self, row: Dict[str, Any]) -> bool:
        """Compatibility button from the original app; now writes into companies instead of atlas_leads."""
        if not self.enabled:
            return False
        payload = company_payload_from_prospect(row)
        existing = self.find_company_by_email_or_name(payload.get("email", ""), payload.get("company_name", ""))
        if existing:
            self.update_company(existing["id"], payload, actor=st.session_state.get("name", "System"))
            return True
        created = self.create_company(payload)
        return bool(created)

    # ---------- Activities ----------
    def fetch_activities(self, company_id: str):
        return self._safe_execute(
            self.client.table("activities").select("*").eq("company_id", company_id).order("activity_date", desc=True),
            fallback=[],
        ) or []

    def add_activity(self, company_id: str, activity_type: str, summary: str, details: str = "", performed_by: str = "System"):
        if not self.enabled:
            return None
        payload = {
            "company_id": company_id,
            "activity_type": activity_type,
            "summary": summary or f"{activity_type} logged",
            "details": details,
            "performed_by": performed_by or "System",
        }
        return self._safe_execute(self.client.table("activities").insert(payload), fallback=[])

    # ---------- Tasks ----------
    def fetch_tasks(self, company_id: str):
        return self._safe_execute(
            self.client.table("tasks").select("*").eq("company_id", company_id).order("due_date", desc=False),
            fallback=[],
        ) or []

    def fetch_all_tasks(self):
        return self._safe_execute(
            self.client.table("tasks").select("*").order("due_date", desc=False),
            fallback=[],
        ) or []

    def create_task(self, company_id: str, title: str, description: str, due_date_value, assigned_rep: str, priority: str):
        if not self.enabled:
            return None
        payload = {
            "company_id": company_id,
            "title": title or "Follow up",
            "description": description,
            "due_date": str(due_date_value) if due_date_value else None,
            "assigned_rep": assigned_rep,
            "priority": priority,
            "status": "Open",
        }
        data = self._safe_execute(self.client.table("tasks").insert(payload), fallback=[])
        self.add_activity(company_id, "Task Created", f"Task created: {payload['title']}", description, assigned_rep or "System")
        return data

    def complete_task(self, task_id: str, company_id: str, task_title: str, actor: str):
        if not self.enabled:
            return None
        data = self._safe_execute(
            self.client.table("tasks").update({
                "status": "Completed",
                "completed_at": datetime.utcnow().isoformat(),
            }).eq("id", task_id),
            fallback=[],
        )
        self.add_activity(company_id, "Task Completed", f"Completed task: {task_title}", "", actor or "System")
        return data

    # ---------- Stage history ----------
    def add_stage_history(self, company_id: str, old_stage: Optional[str], new_stage: str, changed_by: str = "System"):
        if not self.enabled:
            return None
        return self._safe_execute(
            self.client.table("stage_history").insert({
                "company_id": company_id,
                "old_stage": old_stage,
                "new_stage": new_stage,
                "changed_by": changed_by or "System",
            }),
            fallback=[],
        )


def company_payload_from_prospect(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Atlas intelligence prospect fields into the normalized CRM companies schema."""
    display = str(row.get("display_name") or row.get("company_name") or row.get("contact_name") or "Unknown Prospect")
    company_name = str(row.get("company_name") or display)
    monthly_bill = row.get("est_monthly_bill", 0)
    system_kw = row.get("system_kw_roi", row.get("estimated_system_kw", 0))
    estimated_value = float(system_kw or 0) * 2550
    notes = f"""Imported from Atlas intelligence.
Prospect ID: {row.get('prospect_id', '')}
City: {row.get('city', '')}
Utility: {row.get('utility', '')}
Solar fit score: {row.get('solar_fit_score', '')}
Solar potential score: {row.get('solar_potential_score', '')}
Estimated monthly bill: ${monthly_bill}
Estimated system size: {system_kw} kW
20Y ROI: {row.get('roi_20yr_pct', '')}%
Fit notes: {row.get('fit_notes', '')}
""".strip()
    return {
        "company_name": company_name,
        "contact_name": row.get("contact_name") or display,
        "phone": row.get("phone", ""),
        "email": row.get("email", ""),
        "county": row.get("county", ""),
        "property_type": row.get("property_type", ""),
        "lead_source": row.get("lead_source", "Atlas Intelligence"),
        "assigned_rep": row.get("assigned_rep", st.session_state.get("name", "Unassigned")),
        "stage": row.get("stage", "New Lead"),
        "estimated_value": round(estimated_value, 2),
        "probability": int(float(row.get("close_probability", 0.1)) * 100) if float(row.get("close_probability", 0.1)) <= 1 else int(row.get("close_probability", 10)),
        "next_followup_date": str(date.today() + timedelta(days=3)),
        "status_temperature": row.get("sales_temperature", "Warm"),
        "notes": notes,
    }


def normalize_crm_df(rows):
    df = pd.DataFrame(rows or [])
    expected = [
        "id", "company_name", "contact_name", "phone", "email", "county", "property_type",
        "lead_source", "assigned_rep", "stage", "estimated_value", "probability",
        "next_followup_date", "status_temperature", "notes", "created_at", "updated_at"
    ]
    if df.empty:
        return pd.DataFrame(columns=expected)
    for col in expected:
        if col not in df.columns:
            df[col] = None
    df["estimated_value"] = pd.to_numeric(df["estimated_value"], errors="coerce").fillna(0)
    df["probability"] = pd.to_numeric(df["probability"], errors="coerce").fillna(0).astype(int)
    return df


def weighted_choice(items):
    rnd = random.random()
    acc = 0
    for val, wt in items:
        acc += wt
        if rnd <= acc:
            return val
    return items[-1][0]



def random_name():
    first = ["James", "Maria", "Luis", "Sarah", "Daniel", "Rachel", "Jorge", "Anna", "Ethan", "Isabel", "Noah", "Elena"]
    last = ["Rivera", "Walker", "Taylor", "Ortiz", "Sanchez", "Cooper", "Howard", "Mendoza", "Bennett", "Lopez", "Diaz", "Mitchell"]
    return f"{random.choice(first)} {random.choice(last)}"



def random_business():
    parts_a = ["Columbia", "Blue Basin", "Sun Ridge", "Tri-City", "Yakima Valley", "Frontier", "Atlas Prospect", "Riverbend", "Harvest"]
    parts_b = ["Cold Storage", "Farms", "Logistics", "Auto Center", "Metal Works", "Warehouse", "Market", "Vineyards", "Processing"]
    return f"{random.choice(parts_a)} {random.choice(parts_b)}"



def estimate_consumption(property_type, sqft):
    if property_type == "Residential":
        annual_kwh = max(7000, min(24000, sqft * random.uniform(4.5, 7.2)))
    elif property_type == "Commercial":
        annual_kwh = max(18000, sqft * random.uniform(8.0, 14.0))
    elif property_type == "Agricultural":
        annual_kwh = max(24000, sqft * random.uniform(6.5, 13.5))
    else:
        annual_kwh = max(40000, sqft * random.uniform(10.0, 18.0))
    return round(annual_kwh)



def estimate_bill(annual_kwh, utility):
    base_rate = 0.075 if "PUD" in utility else 0.098
    monthly = annual_kwh / 12 * base_rate + random.uniform(18, 85)
    return round(monthly, 2)



def solar_fit_score(row):
    value_score = min(100, row["assessed_value"] / 12000)
    size_score = min(100, row["sqft"] / 80)
    bill_score = min(100, row["est_monthly_bill"] * 0.42)
    type_bonus = {
        "Residential": 8,
        "Commercial": 15,
        "Agricultural": 18,
        "Industrial": 12,
    }[row["property_type"]]
    interest_bonus = {"Warm": 15, "Cold": 0, "Hot": 9}[row["sales_temperature"]]
    score = (0.28 * value_score) + (0.24 * size_score) + (0.30 * bill_score) + type_bonus + interest_bonus
    return round(min(99, max(25, score)), 1)



def close_probability(score, stage):
    stage_mult = {
        "New Lead": 0.42,
        "Contact Attempted": 0.48,
        "Contact Made": 0.56,
        "Qualified": 0.68,
        "Site Review Scheduled": 0.76,
        "Proposal Sent": 0.81,
        "Negotiation": 0.88,
        "Won": 1.0,
        "Lost": 0.02,
    }[stage]
    return round(min(0.98, max(0.03, (score / 100) * stage_mult)), 2)



def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))



def get_energy_price_region(county: str, utility: str) -> Dict[str, Any]:
    if "PUD" in utility:
        cents = 7.8
    elif utility == "Pacific Power":
        cents = 10.2
    else:
        cents = 9.1
    county_bump = {
        "Benton": 0.1,
        "Franklin": 0.2,
        "Yakima": 0.3,
        "Walla Walla": 0.2,
        "Grant": -0.1,
        "Adams": 0.0,
    }
    cents += county_bump.get(county, 0.0)
    return {
        "price_cents_per_kwh": round(cents, 2),
        "source": "regional placeholder",
        "effective_date": datetime.utcnow().date().isoformat(),
    }



def estimate_roi_metrics(row) -> SolarScoreResult:
    shade_pct = {"High": 8, "Medium": 16, "Low": 28}.get(row["roof_confidence"], 16)
    roof_area_sqft = max(1200, float(row["sqft"]) * 0.72)
    usable_ratio = clamp((100 - shade_pct) / 100.0, 0.2, 1.0)
    usable_area = roof_area_sqft * 0.65 * usable_ratio
    recommended_system_kw = round(clamp(usable_area / 100.0, 4.0, 40.0), 1)

    county_sun_factor = {
        "Benton": 1680,
        "Franklin": 1675,
        "Yakima": 1640,
        "Walla Walla": 1600,
        "Grant": 1660,
        "Adams": 1650,
    }
    annual_kwh_estimate = round(recommended_system_kw * county_sun_factor.get(row["county"], 1640), 0)
    region = get_energy_price_region(row["county"], row["utility"])
    annual_savings_usd = annual_kwh_estimate * (region["price_cents_per_kwh"] / 100.0) * 0.84

    install_cost_per_kw = {
        "Residential": 2850,
        "Commercial": 2350,
        "Agricultural": 2200,
        "Industrial": 2450,
    }[row["property_type"]]
    install_cost = recommended_system_kw * install_cost_per_kw
    payback_years = install_cost / annual_savings_usd if annual_savings_usd > 0 else 99.0
    roi_20yr_pct = ((annual_savings_usd * 20) - install_cost) / install_cost * 100 if install_cost > 0 else 0.0
    solar_potential_score = round(clamp((row["solar_fit_score"] * 0.78) + ((100 - shade_pct) * 0.22), 20, 99), 1)
    confidence = round(clamp(0.45 + (solar_potential_score / 100.0) * 0.5, 0.45, 0.95), 2)

    return SolarScoreResult(
        solar_potential_score=solar_potential_score,
        annual_kwh_estimate=annual_kwh_estimate,
        annual_savings_usd=round(annual_savings_usd, 2),
        payback_years=round(payback_years, 1),
        roi_20yr_pct=round(roi_20yr_pct, 1),
        recommended_system_kw=recommended_system_kw,
        confidence=confidence,
    )



def generate_prospects(n=160):
    random.seed(42)
    rows = []
    for i in range(1, n + 1):
        county = random.choice(list(COUNTY_CENTERS.keys()))
        lat0, lon0 = COUNTY_CENTERS[county]
        lat = lat0 + random.uniform(-0.22, 0.22)
        lon = lon0 + random.uniform(-0.26, 0.26)
        city = random.choice(CITY_BY_COUNTY[county])
        property_type = weighted_choice(PROPERTY_TYPES)

        if property_type == "Residential":
            sqft = random.randint(1200, 4200)
            assessed_value = random.randint(240000, 920000)
            name = random_name()
            company_name = ""
        elif property_type == "Commercial":
            sqft = random.randint(4000, 42000)
            assessed_value = random.randint(450000, 4200000)
            name = random_name()
            company_name = random_business()
        elif property_type == "Agricultural":
            sqft = random.randint(3000, 68000)
            assessed_value = random.randint(380000, 5500000)
            name = random_name()
            company_name = random_business()
        else:
            sqft = random.randint(10000, 95000)
            assessed_value = random.randint(900000, 9000000)
            name = random_name()
            company_name = random_business()

        utility = random.choice(UTILITIES[county])
        annual_kwh = estimate_consumption(property_type, sqft)
        monthly_bill = estimate_bill(annual_kwh, utility)
        stage = random.choices(PIPELINE_STAGES, weights=[28, 14, 12, 11, 8, 10, 7, 6, 4], k=1)[0]
        sales_temp = random.choices(["Cold", "Warm", "Hot"], weights=[48, 37, 15], k=1)[0]
        rep = random.choices(REPS, weights=[14, 14, 72], k=1)[0]
        system_kw = round(max(4.0, annual_kwh / 1450), 1)
        created_dt = date.today() - timedelta(days=random.randint(1, 240))

        row = {
            "prospect_id": i,
            "display_name": company_name if company_name else name,
            "contact_name": name,
            "company_name": company_name,
            "county": county,
            "city": city,
            "utility": utility,
            "property_type": property_type,
            "sqft": sqft,
            "assessed_value": assessed_value,
            "estimated_system_kw": system_kw,
            "estimated_annual_kwh": annual_kwh,
            "est_monthly_bill": monthly_bill,
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "stage": stage,
            "sales_temperature": sales_temp,
            "assigned_rep": rep,
            "lead_source": random.choice(LEAD_SOURCES),
            "last_contact_days": random.randint(0, 35),
            "created_date": created_dt.isoformat(),
            "roof_confidence": random.choice(["High", "Medium", "Medium", "Low"]),
            "fit_notes": random.choice([
                "High-value roofline and strong bill-reduction angle.",
                "Promising commercial consumption profile.",
                "Good ag load profile. Storage could be future upsell.",
                "Strong ownership profile and above-median assessed value.",
                "Likely better fit after direct site review.",
            ]),
        }
        row["solar_fit_score"] = solar_fit_score(row)
        row["close_probability"] = close_probability(row["solar_fit_score"], stage)
        row["estimated_annual_savings"] = round(row["est_monthly_bill"] * 12 * random.uniform(0.55, 0.82), 0)

        roi = estimate_roi_metrics(row)
        row["solar_potential_score"] = roi.solar_potential_score
        row["annual_savings_roi"] = roi.annual_savings_usd
        row["payback_years"] = roi.payback_years
        row["roi_20yr_pct"] = roi.roi_20yr_pct
        row["system_kw_roi"] = roi.recommended_system_kw
        rows.append(row)

    df = pd.DataFrame(rows)
    df["priority_rank"] = df["solar_fit_score"].rank(ascending=False, method="dense").astype(int)
    return df



def generate_activity_history(prospects):
    rows = []
    random.seed(7)
    for _, row in prospects.iterrows():
        for _ in range(random.randint(1, 5)):
            event_date = datetime.fromisoformat(row["created_date"]) + timedelta(days=random.randint(0, 90))
            rows.append(
                {
                    "prospect_id": row["prospect_id"],
                    "date": event_date.date().isoformat(),
                    "activity_type": random.choice(["Call", "Email", "Text", "Site Review", "Proposal"]),
                    "summary": random.choice([
                        "Followed up on estimated savings.",
                        "Left voicemail and sent SMS.",
                        "Discussed system sizing and utility territory.",
                        "Reviewed roof suitability and project timeline.",
                        "Shared proposal and financing overview.",
                    ]),
                    "rep": row["assigned_rep"],
                }
            )
    return pd.DataFrame(rows)



def generate_performance_history():
    random.seed(9)
    months = pd.date_range(date.today().replace(day=1) - pd.DateOffset(months=11), periods=12, freq="MS")
    records = []
    base_leads = 18
    for i, dt in enumerate(months):
        leads = base_leads + i * 3 + random.randint(-2, 4)
        qualified = int(leads * random.uniform(0.34, 0.51))
        proposals = int(qualified * random.uniform(0.55, 0.78))
        wins = int(proposals * random.uniform(0.32, 0.58))
        revenue = wins * random.randint(18000, 46000)
        records.append(
            {
                "month": dt.strftime("%Y-%m"),
                "new_leads": leads,
                "qualified": qualified,
                "proposals": proposals,
                "wins": wins,
                "revenue": revenue,
            }
        )
    return pd.DataFrame(records)


@st.cache_data
def load_data():
    prospects_path = DATA_DIR / "prospects_v2.csv"
    activities_path = DATA_DIR / "activities_v2.csv"
    perf_path = DATA_DIR / "performance_v2.csv"

    if prospects_path.exists():
        prospects = pd.read_csv(prospects_path)
    else:
        prospects = generate_prospects()
        prospects.to_csv(prospects_path, index=False)

    if activities_path.exists():
        activities = pd.read_csv(activities_path)
    else:
        activities = generate_activity_history(prospects)
        activities.to_csv(activities_path, index=False)

    if perf_path.exists():
        perf = pd.read_csv(perf_path)
    else:
        perf = generate_performance_history()
        perf.to_csv(perf_path, index=False)

    return prospects, activities, perf


# =========================
# UTILITIES
# =========================
def kpi_card(label, value, detail):
    st.markdown(
        f"""
        <div class="atlas-kpi">
            <div class="label">{label}</div>
            <div class="value">{value}</div>
            <div class="detail">{detail}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )



def money(v):
    return "${:,.0f}".format(v)



def nearest_prospect(df, lat, lon):
    if df.empty:
        return None
    work = df.copy()
    work["dist"] = ((work["latitude"] - lat) ** 2 + (work["longitude"] - lon) ** 2) ** 0.5
    idx = work["dist"].idxmin()
    return work.loc[idx]



def suggestion_text(df):
    if df.empty:
        return ["No leads match the current filters. Widen the county or stage filters."]
    top_county = df.groupby("county")["solar_fit_score"].mean().sort_values(ascending=False).index[0]
    top_type = df.groupby("property_type")["close_probability"].mean().sort_values(ascending=False).index[0]
    stale = df[df["last_contact_days"] >= 14]
    return [
        f"Prioritize **{top_county} County** first — it currently has the strongest average fit score in the filtered book.",
        f"Lean into **{top_type.lower()}** outreach — that segment shows the best expected close probability right now.",
        f"{len(stale)} active leads are stale for 14+ days. A fast follow-up cycle should lift conversion.",
    ]



def stage_color(stage):
    return {
        "New Lead": "#60a5fa",
        "Contact Attempted": "#38bdf8",
        "Contact Made": "#22c55e",
        "Qualified": "#84cc16",
        "Site Review Scheduled": "#eab308",
        "Proposal Sent": "#f97316",
        "Negotiation": "#a855f7",
        "Won": "#10b981",
        "Lost": "#ef4444",
    }.get(stage, "#60a5fa")



def filtered_view(df):
    st.sidebar.markdown("## Filters")
    county = st.sidebar.multiselect("County", sorted(df["county"].unique()), default=["Yakima", "Benton", "Franklin"])
    prop_type = st.sidebar.multiselect("Property Type", sorted(df["property_type"].unique()), default=sorted(df["property_type"].unique()))
    rep = st.sidebar.multiselect("Assigned Rep", sorted(df["assigned_rep"].unique()), default=sorted(df["assigned_rep"].unique()))
    stage = st.sidebar.multiselect("Stage", PIPELINE_STAGES, default=PIPELINE_STAGES)
    min_score = st.sidebar.slider("Minimum solar fit score", 0, 100, 55)
    query = st.sidebar.text_input("Search name / company / city", "")

    out = df[
        df["county"].isin(county)
        & df["property_type"].isin(prop_type)
        & df["assigned_rep"].isin(rep)
        & df["stage"].isin(stage)
        & (df["solar_fit_score"] >= min_score)
    ].copy()

    if query:
        q = query.lower()
        out = out[
            out["display_name"].str.lower().str.contains(q)
            | out["contact_name"].str.lower().str.contains(q)
            | out["city"].str.lower().str.contains(q)
            | out["company_name"].fillna("").str.lower().str.contains(q)
        ]
    return out



def build_map(df):
    center_lat = df["latitude"].mean() if not df.empty else 46.25
    center_lon = df["longitude"].mean() if not df.empty else -119.2

    fmap = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=8,
        tiles=None,
        control_scale=True,
    )
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Satellite",
        overlay=False,
        control=True,
    ).add_to(fmap)

    for _, row in df.iterrows():
        html = f"""
        <div style='width:240px'>
            <b>{row['display_name']}</b><br>
            {row['city']}, {row['county']} County<br>
            Type: {row['property_type']}<br>
            Utility: {row['utility']}<br>
            Fit Score: <b>{row['solar_fit_score']}</b><br>
            ROI 20Y: <b>{row['roi_20yr_pct']}%</b><br>
            Est. Bill: <b>${row['est_monthly_bill']:.0f}/mo</b><br>
            Stage: <b>{row['stage']}</b>
        </div>
        """
        radius = 4 + max(2, row["solar_fit_score"] / 22)
        fill_color = "#10b981" if row["roi_20yr_pct"] > 80 else "#2563eb"
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=radius,
            color="#60a5fa",
            weight=1,
            fill=True,
            fill_color=fill_color,
            fill_opacity=0.82,
            popup=folium.Popup(html, max_width=290),
            tooltip=f"{row['display_name']} • Score {row['solar_fit_score']}",
        ).add_to(fmap)

    folium.LayerControl().add_to(fmap)
    return fmap



def detail_panel(selected):
    if selected is None or len(selected) == 0:
        st.info("Select a lead from the satellite map or table to inspect a recommended target.")
        return

    roi = estimate_roi_metrics(selected)
    c1, c2 = st.columns([1.15, 0.85])
    with c1:
        st.markdown('<div class="atlas-card">', unsafe_allow_html=True)
        st.markdown(f"### {selected['display_name']}")
        st.markdown(
            f"""
            <span class="pill">{selected['county']} County</span>
            <span class="pill">{selected['property_type']}</span>
            <span class="pill">{selected['utility']}</span>
            <span class="pill">{selected['stage']}</span>
            """,
            unsafe_allow_html=True,
        )
        st.write(f"**Contact:** {selected['contact_name']}")
        st.write(f"**City:** {selected['city']}")
        st.write(f"**Assigned rep:** {selected['assigned_rep']}")
        st.write(f"**Lead source:** {selected['lead_source']}")
        st.write(f"**Fit notes:** {selected['fit_notes']}")
        st.markdown("</div>", unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="atlas-card">', unsafe_allow_html=True)
        st.write(f"**Solar Fit Score:** {selected['solar_fit_score']}")
        st.write(f"**Solar Potential Score:** {roi.solar_potential_score}")
        st.write(f"**Estimated Monthly Bill:** ${selected['est_monthly_bill']:.0f}")
        st.write(f"**Estimated Annual kWh:** {roi.annual_kwh_estimate:,.0f}")
        st.write(f"**Recommended System Size:** {roi.recommended_system_kw} kW")
        st.write(f"**Annual Savings:** ${roi.annual_savings_usd:,.0f}")
        st.write(f"**Payback:** {roi.payback_years} years")
        st.write(f"**20Y ROI:** {roi.roi_20yr_pct}%")
        st.markdown("</div>", unsafe_allow_html=True)



def route_sequence(df):
    if df.empty:
        return df
    remaining = df.copy().reset_index(drop=True)
    current_lat = float(remaining.iloc[0]["latitude"])
    current_lon = float(remaining.iloc[0]["longitude"])
    ordered_rows = []

    while not remaining.empty:
        dist = ((remaining["latitude"] - current_lat) ** 2 + (remaining["longitude"] - current_lon) ** 2) ** 0.5
        idx = dist.idxmin()
        row = remaining.loc[idx].copy()
        ordered_rows.append(row)
        current_lat = float(row["latitude"])
        current_lon = float(row["longitude"])
        remaining = remaining.drop(idx).reset_index(drop=True)

    out = pd.DataFrame(ordered_rows).reset_index(drop=True)
    out["stop_number"] = out.index + 1
    return out



def generate_proposal_payload(selected) -> Dict[str, Any]:
    roi = estimate_roi_metrics(selected)
    return {
        "customer": {
            "name": selected["contact_name"],
            "prospect": selected["display_name"],
            "county": selected["county"],
            "city": selected["city"],
            "utility": selected["utility"],
        },
        "system_recommendation": {
            "recommended_system_kw": roi.recommended_system_kw,
            "annual_kwh_estimate": roi.annual_kwh_estimate,
            "annual_savings_usd": roi.annual_savings_usd,
            "payback_years": roi.payback_years,
            "roi_20yr_pct": roi.roi_20yr_pct,
        },
        "reserved_company_inputs": {
            "pricing_logic": "TO_BE_CONNECTED",
            "financing_logic": "TO_BE_CONNECTED",
            "equipment_catalog": "TO_BE_CONNECTED",
            "battery_options": "TO_BE_CONNECTED",
            "contract_terms": "TO_BE_CONNECTED",
        },
        "generated_at": datetime.utcnow().isoformat(),
    }



def proposal_markdown(payload: Dict[str, Any]) -> str:
    c = payload["customer"]
    s = payload["system_recommendation"]
    return f"""
# Atlas Solar Proposal Draft

## Customer
- Contact: {c['name']}
- Prospect: {c['prospect']}
- Territory: {c['city']}, {c['county']} County
- Utility: {c['utility']}

## Recommended System
- Recommended system size: {s['recommended_system_kw']} kW
- Estimated annual production: {s['annual_kwh_estimate']} kWh
- Estimated annual savings: ${s['annual_savings_usd']:,.2f}
- Estimated payback: {s['payback_years']} years
- Estimated 20-year ROI: {s['roi_20yr_pct']}%

## Reserved Business Inputs
- Pricing logic: TO_BE_CONNECTED
- Financing logic: TO_BE_CONNECTED
- Equipment catalog: TO_BE_CONNECTED
- Battery options: TO_BE_CONNECTED
- Contract terms: TO_BE_CONNECTED

## Notes
This is a working Atlas V2 proposal draft designed for Eastern Washington sales workflow.
""".strip()


# =========================
# APP
# =========================
if not st.session_state.get("authenticated"):
    login_panel()
    st.stop()

prospects, activities, perf = load_data()
filtered = filtered_view(prospects)
supabase_service = SupabaseService(SUPABASE_URL, SUPABASE_KEY)

st.sidebar.markdown("---")
st.sidebar.write(f"Signed in as **{st.session_state.get('name', 'Atlas User')}**")
st.sidebar.write(f"Role: **{st.session_state.get('role', 'User')}**")
st.sidebar.write(f"Supabase: **{'Connected' if supabase_service.enabled else 'Local demo mode'}**")
logout_button()

st.markdown('<div class="main-title">Atlas V2 — Solar Growth OS</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Private lead intelligence + CRM pipeline + performance tracking + ROI + routes for Atlas Solar in Eastern Washington</div>',
    unsafe_allow_html=True,
)

k1, k2, k3, k4 = st.columns(4)
with k1:
    kpi_card("Filtered leads", f"{len(filtered):,}", "Prospects in current intelligence view")
with k2:
    avg_fit = f"{filtered['solar_fit_score'].mean():.1f}" if not filtered.empty else "0.0"
    kpi_card("Avg fit score", avg_fit, "Higher = stronger solar sales target")
with k3:
    roi_pool = filtered["annual_savings_roi"].sum() if not filtered.empty else 0
    kpi_card("ROI annual savings pool", money(roi_pool), "Combined ROI-based savings narrative")
with k4:
    open_pipeline = filtered[~filtered["stage"].isin(["Won", "Lost"])]
    pipeline_value = (open_pipeline["system_kw_roi"] * 2550).sum() if not open_pipeline.empty else 0
    kpi_card("Open pipeline est. value", money(pipeline_value), "Rough placeholder sales value for active book")

tabs = st.tabs(["Command Center", "Lead Intelligence", "Pipeline CRM", "Routes + Proposals", "Performance"])

with tabs[0]:
    left, right = st.columns([1.2, 0.8])
    with left:
        st.markdown("### AI suggestions")
        for item in suggestion_text(filtered):
            st.markdown(f"- {item}")
        top_targets = filtered.sort_values(["solar_fit_score", "close_probability", "roi_20yr_pct"], ascending=False).head(10)
        view_cols = [
            "priority_rank", "display_name", "county", "property_type", "stage",
            "solar_fit_score", "roi_20yr_pct", "est_monthly_bill", "assigned_rep"
        ]
        st.markdown("### Recommended targets")
        st.dataframe(
            top_targets[view_cols].rename(
                columns={
                    "priority_rank": "Rank",
                    "display_name": "Prospect",
                    "property_type": "Type",
                    "solar_fit_score": "Fit Score",
                    "roi_20yr_pct": "ROI 20Y %",
                    "est_monthly_bill": "Est. Bill/mo",
                    "assigned_rep": "Rep",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
    with right:
        st.markdown("### Current stage mix")
        stage_mix = filtered.groupby("stage").size().reset_index(name="count")
        if not stage_mix.empty:
            fig = px.bar(
                stage_mix,
                x="stage",
                y="count",
                color="stage",
                color_discrete_map={s: stage_color(s) for s in stage_mix["stage"]},
            )
            fig.update_layout(height=360, showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No stage data for the current filters.")

with tabs[1]:
    c1, c2 = st.columns([1.3, 0.7])
    with c1:
        st.markdown("### Satellite lead map")
        st.caption("Blue and green dots are AI-ranked Atlas prospects. Click a dot to inspect that target.")
        fmap = build_map(filtered)
        map_state = st_folium(fmap, width=None, height=560, returned_objects=["last_object_clicked", "last_object_clicked_tooltip"])
        clicked = map_state.get("last_object_clicked")
        if clicked:
            nearest = nearest_prospect(filtered, clicked["lat"], clicked["lng"])
            if nearest is not None:
                st.session_state["selected_prospect_id"] = int(nearest["prospect_id"])
    with c2:
        st.markdown("### Selected prospect")
        selected = None
        if st.session_state.get("selected_prospect_id") is not None:
            sel = filtered[filtered["prospect_id"] == st.session_state["selected_prospect_id"]]
            if not sel.empty:
                selected = sel.iloc[0]
        detail_panel(selected)

    st.markdown("### Prospect table")
    lead_table = filtered.sort_values(["solar_fit_score", "close_probability"], ascending=False)[[
        "prospect_id", "display_name", "county", "city", "property_type", "utility", "stage",
        "solar_fit_score", "roi_20yr_pct", "close_probability", "est_monthly_bill", "estimated_system_kw", "assigned_rep"
    ]].rename(
        columns={
            "prospect_id": "ID",
            "display_name": "Prospect",
            "property_type": "Type",
            "solar_fit_score": "Fit Score",
            "roi_20yr_pct": "ROI 20Y %",
            "close_probability": "Close %",
            "est_monthly_bill": "Est. Bill/mo",
            "estimated_system_kw": "System kW",
            "assigned_rep": "Rep",
        }
    )
    st.dataframe(lead_table, use_container_width=True, hide_index=True)

with tabs[2]:
    st.markdown("### Pipeline CRM")
    st.caption("This section now uses your real Supabase CRM tables instead of the old demo-only snapshot system.")

    crm_rows = supabase_service.fetch_companies() if supabase_service.enabled else []
    crm_df = normalize_crm_df(crm_rows)

    if not supabase_service.enabled:
        st.warning("Supabase is not connected. The Atlas intelligence views still work, but real CRM saving/editing is offline.")
        if supabase_service.error:
            st.caption(f"Supabase issue: {supabase_service.error}")

    # -------------------------
    # CRM top controls
    # -------------------------
    c_add, c_sync = st.columns([1.05, 0.95])

    with c_add:
        st.markdown('<div class="atlas-card">', unsafe_allow_html=True)
        st.markdown("#### Add company / lead")
        with st.form("crm_add_company_form", clear_on_submit=True):
            company_name = st.text_input("Company / prospect name *")
            contact_name = st.text_input("Contact name")
            phone = st.text_input("Phone")
            email = st.text_input("Email")
            county = st.selectbox("County", sorted(COUNTY_CENTERS.keys()))
            property_type = st.selectbox("Property type", [x[0] for x in PROPERTY_TYPES])
            lead_source = st.selectbox("Lead source", LEAD_SOURCES + ["Manual Entry", "Atlas Intelligence"])
            assigned_rep = st.selectbox("Assigned rep", REPS)
            stage = st.selectbox("Stage", PIPELINE_STAGES)
            estimated_value = st.number_input("Estimated deal value", min_value=0.0, step=1000.0, value=25000.0)
            probability = st.slider("Close probability", 0, 100, 15)
            next_followup_date = st.date_input("Next follow-up", value=date.today() + timedelta(days=3))
            temperature = st.selectbox("Lead temperature", ["Cold", "Warm", "Hot"], index=1)
            notes = st.text_area("Notes")
            create_clicked = st.form_submit_button("Save lead to CRM", use_container_width=True)

            if create_clicked:
                if not company_name.strip():
                    st.error("Company / prospect name is required.")
                elif not supabase_service.enabled:
                    st.error("Supabase is not connected, so this lead cannot be saved yet.")
                else:
                    created = supabase_service.create_company({
                        "company_name": company_name.strip(),
                        "contact_name": contact_name,
                        "phone": phone,
                        "email": email,
                        "county": county,
                        "property_type": property_type,
                        "lead_source": lead_source,
                        "assigned_rep": assigned_rep,
                        "stage": stage,
                        "estimated_value": estimated_value,
                        "probability": probability,
                        "next_followup_date": str(next_followup_date),
                        "status_temperature": temperature,
                        "notes": notes,
                    })
                    if created:
                        st.success("Lead saved to CRM.")
                        st.rerun()
                    else:
                        st.error("Lead could not be saved. Check Supabase policies/schema.")
        st.markdown('</div>', unsafe_allow_html=True)

    with c_sync:
        st.markdown('<div class="atlas-card">', unsafe_allow_html=True)
        st.markdown("#### Convert Atlas prospect into CRM lead")
        if st.session_state.get("selected_prospect_id") is not None:
            selected_df = filtered[filtered["prospect_id"] == st.session_state["selected_prospect_id"]]
        else:
            selected_df = pd.DataFrame()

        if selected_df.empty:
            st.info("Select a prospect from the Lead Intelligence map first, then return here to convert it into a real CRM lead.")
        else:
            prospect = selected_df.iloc[0]
            st.write(f"**Selected:** {prospect['display_name']}")
            st.caption(f"{prospect['city']}, {prospect['county']} • Fit {prospect['solar_fit_score']} • ROI {prospect['roi_20yr_pct']}%")
            payload_preview = company_payload_from_prospect(prospect.to_dict())
            st.write(f"Estimated deal value: **{money(payload_preview['estimated_value'])}**")
            if st.button("Save selected prospect to CRM", use_container_width=True):
                ok = supabase_service.upsert_lead_snapshot(prospect.to_dict())
                if ok:
                    st.success("Selected prospect saved into the real CRM tables.")
                    st.rerun()
                else:
                    st.error("Could not save selected prospect. Check Supabase connection and table policies.")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("---")

    # Refresh CRM data after possible create/sync
    crm_rows = supabase_service.fetch_companies() if supabase_service.enabled else []
    crm_df = normalize_crm_df(crm_rows)

    # -------------------------
    # CRM KPI row
    # -------------------------
    active_crm = crm_df[~crm_df["stage"].isin(["Won", "Lost"])] if not crm_df.empty else crm_df
    won_crm = crm_df[crm_df["stage"] == "Won"] if not crm_df.empty else crm_df
    lost_crm = crm_df[crm_df["stage"] == "Lost"] if not crm_df.empty else crm_df
    weighted_value = (active_crm["estimated_value"] * (active_crm["probability"] / 100)).sum() if not active_crm.empty else 0

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        kpi_card("CRM leads", f"{len(crm_df):,}", "Saved company records")
    with m2:
        kpi_card("Open CRM pipeline", money(active_crm["estimated_value"].sum() if not active_crm.empty else 0), "Active deal value")
    with m3:
        kpi_card("Weighted pipeline", money(weighted_value), "Value × probability")
    with m4:
        kpi_card("Won / Lost", f"{len(won_crm)} / {len(lost_crm)}", "Closed CRM outcomes")

    # -------------------------
    # Pipeline board + active table
    # -------------------------
    c1, c2 = st.columns([1.0, 1.0])
    with c1:
        st.markdown("### Real CRM pipeline board")
        stage_counts = crm_df.groupby("stage").size().reindex(PIPELINE_STAGES, fill_value=0) if not crm_df.empty else pd.Series([0] * len(PIPELINE_STAGES), index=PIPELINE_STAGES)
        board_cols = st.columns(4)
        for idx, (stage_name, count) in enumerate(stage_counts.items()):
            stage_value = crm_df[crm_df["stage"] == stage_name]["estimated_value"].sum() if not crm_df.empty else 0
            with board_cols[idx % 4]:
                st.markdown(
                    f"""
                    <div class="atlas-card">
                        <div class="section-header" style="font-size:1rem">{stage_name}</div>
                        <div style="font-size:1.8rem;font-weight:800;color:{stage_color(stage_name)}">{int(count)}</div>
                        <div class="small-note">{money(stage_value)}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        st.markdown("### Active CRM opportunities")
        if active_crm.empty:
            st.info("No active CRM opportunities yet. Add one above or convert a prospect from the map.")
        else:
            st.dataframe(
                active_crm[[
                    "company_name", "contact_name", "county", "property_type", "stage", "assigned_rep",
                    "estimated_value", "probability", "next_followup_date", "status_temperature"
                ]].rename(columns={
                    "company_name": "Company",
                    "contact_name": "Contact",
                    "property_type": "Type",
                    "assigned_rep": "Rep",
                    "estimated_value": "Value",
                    "next_followup_date": "Next Follow-up",
                    "status_temperature": "Temp",
                }),
                use_container_width=True,
                hide_index=True,
            )

    with c2:
        st.markdown("### Company detail + CRM actions")
        if crm_df.empty:
            st.info("No CRM companies yet.")
        else:
            labels = {
                f"{row['company_name']} | {row.get('stage', '')} | {row.get('assigned_rep', '')}": row["id"]
                for _, row in crm_df.iterrows()
            }
            selected_label = st.selectbox("Select CRM company", list(labels.keys()))
            company_id = labels[selected_label]
            selected_company = crm_df[crm_df["id"] == company_id].iloc[0].to_dict()

            with st.form("crm_edit_company_form"):
                company_name_e = st.text_input("Company", value=selected_company.get("company_name") or "")
                contact_name_e = st.text_input("Contact", value=selected_company.get("contact_name") or "")
                phone_e = st.text_input("Phone", value=selected_company.get("phone") or "")
                email_e = st.text_input("Email", value=selected_company.get("email") or "")
                county_options = sorted(COUNTY_CENTERS.keys())
                county_current = selected_company.get("county") if selected_company.get("county") in county_options else county_options[0]
                county_e = st.selectbox("County", county_options, index=county_options.index(county_current))
                prop_options = [x[0] for x in PROPERTY_TYPES]
                prop_current = selected_company.get("property_type") if selected_company.get("property_type") in prop_options else prop_options[0]
                property_type_e = st.selectbox("Property type", prop_options, index=prop_options.index(prop_current))
                rep_e = st.selectbox("Assigned rep", REPS, index=REPS.index(selected_company.get("assigned_rep")) if selected_company.get("assigned_rep") in REPS else 2)
                stage_current = selected_company.get("stage") if selected_company.get("stage") in PIPELINE_STAGES else "New Lead"
                stage_e = st.selectbox("Stage", PIPELINE_STAGES, index=PIPELINE_STAGES.index(stage_current))
                estimated_value_e = st.number_input("Estimated value", min_value=0.0, step=1000.0, value=float(selected_company.get("estimated_value") or 0))
                probability_e = st.slider("Probability", 0, 100, int(selected_company.get("probability") or 0))
                next_value = pd.to_datetime(selected_company.get("next_followup_date")).date() if selected_company.get("next_followup_date") else date.today()
                next_followup_e = st.date_input("Next follow-up", value=next_value)
                temp_options = ["Cold", "Warm", "Hot"]
                temp_current = selected_company.get("status_temperature") if selected_company.get("status_temperature") in temp_options else "Warm"
                temp_e = st.selectbox("Temperature", temp_options, index=temp_options.index(temp_current))
                notes_e = st.text_area("Notes", value=selected_company.get("notes") or "", height=130)
                save_changes = st.form_submit_button("Save CRM changes", use_container_width=True)

                if save_changes:
                    supabase_service.update_company(company_id, {
                        "company_name": company_name_e,
                        "contact_name": contact_name_e,
                        "phone": phone_e,
                        "email": email_e,
                        "county": county_e,
                        "property_type": property_type_e,
                        "assigned_rep": rep_e,
                        "stage": stage_e,
                        "estimated_value": estimated_value_e,
                        "probability": probability_e,
                        "next_followup_date": str(next_followup_e),
                        "status_temperature": temp_e,
                        "notes": notes_e,
                    }, actor=st.session_state.get("name", "System"))
                    st.success("CRM company updated.")
                    st.rerun()

            a1, a2 = st.columns(2)
            with a1:
                st.markdown("#### Log activity")
                with st.form("crm_activity_form"):
                    activity_type = st.selectbox("Activity type", ["Call", "Email", "Text", "Meeting", "Site Review", "Proposal", "Note", "Other"])
                    summary = st.text_input("Summary")
                    details = st.text_area("Details")
                    add_activity = st.form_submit_button("Add activity", use_container_width=True)
                    if add_activity:
                        supabase_service.add_activity(company_id, activity_type, summary, details, st.session_state.get("name", "System"))
                        st.success("Activity logged.")
                        st.rerun()
            with a2:
                st.markdown("#### Create task")
                with st.form("crm_task_form"):
                    task_title = st.text_input("Task", value="Follow up")
                    task_due = st.date_input("Due", value=date.today() + timedelta(days=2))
                    priority = st.selectbox("Priority", ["Low", "Medium", "High", "Urgent"], index=1)
                    task_desc = st.text_area("Task details")
                    add_task = st.form_submit_button("Create task", use_container_width=True)
                    if add_task:
                        supabase_service.create_task(company_id, task_title, task_desc, task_due, selected_company.get("assigned_rep") or st.session_state.get("name", "System"), priority)
                        st.success("Task created.")
                        st.rerun()

            st.markdown("#### Activity feed")
            acts = pd.DataFrame(supabase_service.fetch_activities(company_id))
            if acts.empty:
                st.info("No activity logged yet.")
            else:
                st.dataframe(
                    acts[["activity_date", "activity_type", "summary", "performed_by"]].rename(columns={
                        "activity_date": "Date", "activity_type": "Type", "performed_by": "By"
                    }),
                    use_container_width=True,
                    hide_index=True,
                )

            st.markdown("#### Tasks")
            task_rows = supabase_service.fetch_tasks(company_id)
            if not task_rows:
                st.info("No tasks for this company.")
            else:
                for task in task_rows:
                    tcols = st.columns([2.4, 1, 1])
                    tcols[0].write(f"**{task.get('title')}**")
                    tcols[0].caption(f"Due: {task.get('due_date')} • Priority: {task.get('priority')} • {task.get('description') or ''}")
                    tcols[1].write(task.get("status"))
                    if task.get("status") != "Completed":
                        if tcols[2].button("Complete", key=f"complete_task_{task['id']}"):
                            supabase_service.complete_task(task["id"], company_id, task.get("title", "Task"), st.session_state.get("name", "System"))
                            st.rerun()

    # -------------------------
    # Legacy/local activity feed still visible for Atlas intelligence
    # -------------------------
    st.markdown("---")
    st.markdown("### Atlas intelligence activity feed")
    if st.session_state.get("selected_prospect_id") is not None:
        sel_acts = activities[activities["prospect_id"] == st.session_state["selected_prospect_id"]].sort_values("date", ascending=False)
        if sel_acts.empty:
            st.info("No generated activity yet for the selected intelligence lead.")
        else:
            st.dataframe(sel_acts.rename(columns={"activity_type": "Activity", "summary": "Summary", "rep": "Rep"}), use_container_width=True, hide_index=True)
    else:
        latest = activities.sort_values("date", ascending=False).head(20)
        st.dataframe(latest.rename(columns={"activity_type": "Activity", "summary": "Summary", "rep": "Rep"}), use_container_width=True, hide_index=True)

with tabs[3]:
    selected = None
    if st.session_state.get("selected_prospect_id") is not None:
        sel = filtered[filtered["prospect_id"] == st.session_state["selected_prospect_id"]]
        if not sel.empty:
            selected = sel.iloc[0]

    left, right = st.columns([0.95, 1.05])
    with left:
        st.markdown("### Knocking route planner")
        route_source = filtered.sort_values(["county", "solar_fit_score", "roi_20yr_pct"], ascending=[True, False, False])
        if not route_source.empty:
            county_choice = st.selectbox("Route county", sorted(route_source["county"].unique()))
            county_df = route_source[route_source["county"] == county_choice].head(12)
            route_df = route_sequence(county_df)
            st.dataframe(
                route_df[["stop_number", "display_name", "city", "solar_fit_score", "roi_20yr_pct", "stage"]].rename(
                    columns={
                        "display_name": "Prospect",
                        "solar_fit_score": "Fit Score",
                        "roi_20yr_pct": "ROI 20Y %",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No route candidates in current filter view.")

    with right:
        st.markdown("### Proposal studio")
        if selected is None:
            st.info("Select a prospect from the map first to generate a proposal draft.")
        else:
            payload = generate_proposal_payload(selected)
            md = proposal_markdown(payload)
            st.markdown(md)
            st.download_button(
                "Download proposal draft (.md)",
                data=md,
                file_name=f"atlas_proposal_{int(selected['prospect_id'])}.md",
                mime="text/markdown",
                use_container_width=True,
            )
            st.download_button(
                "Download proposal payload (.json)",
                data=json.dumps(payload, indent=2),
                file_name=f"atlas_proposal_{int(selected['prospect_id'])}.json",
                mime="application/json",
                use_container_width=True,
            )

with tabs[4]:
    c1, c2 = st.columns([1.1, 0.9])
    with c1:
        st.markdown("### Company performance over time")
        fig = px.line(perf, x="month", y=["new_leads", "qualified", "proposals", "wins"], markers=True)
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig2 = px.bar(perf, x="month", y="revenue")
        fig2.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig2, use_container_width=True)

    b1, b2 = st.columns(2)
    with b1:
        by_rep = filtered.groupby("assigned_rep").agg(
            leads=("prospect_id", "count"),
            avg_fit=("solar_fit_score", "mean"),
            avg_close=("close_probability", "mean"),
        ).reset_index()
        st.markdown("### Rep performance snapshot")
        st.dataframe(
            by_rep.rename(columns={"assigned_rep": "Rep", "avg_fit": "Avg Fit Score", "avg_close": "Avg Close %"}),
            use_container_width=True,
            hide_index=True,
        )
    with b2:
        county_perf = filtered.groupby("county").agg(
            leads=("prospect_id", "count"),
            avg_fit=("solar_fit_score", "mean"),
            avg_bill=("est_monthly_bill", "mean"),
            avg_roi=("roi_20yr_pct", "mean"),
        ).reset_index().sort_values("avg_fit", ascending=False)
        st.markdown("### County performance snapshot")
        st.dataframe(
            county_perf.rename(columns={"avg_fit": "Avg Fit Score", "avg_bill": "Avg Est. Bill/mo", "avg_roi": "Avg ROI 20Y %"}),
            use_container_width=True,
            hide_index=True,
        )

st.markdown("---")
st.caption("Atlas V2 uses the V1 Eastern Washington territory and satellite workflow as the base, then adds ROI, route planning, proposal scaffolding, and optional CRM persistence.")
