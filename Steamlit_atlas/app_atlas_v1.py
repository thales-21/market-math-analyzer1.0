
import math
import random
from datetime import date, datetime, timedelta
from pathlib import Path

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

st.set_page_config(page_title="Atlas V1", page_icon="☀️", layout="wide")

# =========================
# APP STYLING
# =========================
st.markdown("""
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
""", unsafe_allow_html=True)

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

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
    st.markdown('<div class="main-title">Atlas V1 — Solar Growth OS</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-title">Private CRM for Atlas Solar • Lead Intelligence • Pipeline • Performance • Eastern Washington</div>',
        unsafe_allow_html=True
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
        st.markdown("### Private V1 access")
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
            This V1 uses private application login for two users. For production, move to Supabase Auth,
            hash passwords, and keep all secrets server-side.
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
        stage = random.choices(
            PIPELINE_STAGES,
            weights=[28, 14, 12, 11, 8, 10, 7, 6, 4],
            k=1,
        )[0]
        sales_temp = random.choices(["Cold", "Warm", "Hot"], weights=[48, 37, 15], k=1)[0]
        rep = random.choices(REPS, weights=[14, 14, 72], k=1)[0]
        score_base = {
            "Residential": random.uniform(46, 82),
            "Commercial": random.uniform(55, 91),
            "Agricultural": random.uniform(58, 94),
            "Industrial": random.uniform(54, 88),
        }[property_type]
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
    prospects_path = DATA_DIR / "prospects.csv"
    activities_path = DATA_DIR / "activities.csv"
    perf_path = DATA_DIR / "performance.csv"

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
        return [
            "No leads match the current filters. Widen the county or stage filters.",
        ]
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
    county = st.sidebar.multiselect("County", sorted(df["county"].unique()), default=sorted(df["county"].unique()))
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
            Est. Bill: <b>${row['est_monthly_bill']:.0f}/mo</b><br>
            Stage: <b>{row['stage']}</b>
        </div>
        """
        radius = 4 + max(2, row["solar_fit_score"] / 22)
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=radius,
            color="#60a5fa",
            weight=1,
            fill=True,
            fill_color="#2563eb",
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
        st.write(f"**Estimated Monthly Bill:** ${selected['est_monthly_bill']:.0f}")
        st.write(f"**Estimated Annual kWh:** {selected['estimated_annual_kwh']:,}")
        st.write(f"**Estimated System Size:** {selected['estimated_system_kw']} kW")
        st.write(f"**Estimated Annual Savings:** {money(selected['estimated_annual_savings'])}")
        st.write(f"**Close Probability:** {int(selected['close_probability'] * 100)}%")
        st.write(f"**Assessed Value:** {money(selected['assessed_value'])}")
        st.write(f"**Building Size:** {selected['sqft']:,} sq ft")
        st.markdown("</div>", unsafe_allow_html=True)

# =========================
# APP
# =========================
if not st.session_state.get("authenticated"):
    login_panel()
    st.stop()

prospects, activities, perf = load_data()
filtered = filtered_view(prospects)

st.sidebar.markdown("---")
st.sidebar.write(f"Signed in as **{st.session_state['name']}**")
st.sidebar.write(f"Role: **{st.session_state['role']}**")
logout_button()

st.markdown('<div class="main-title">Atlas V1 — Solar Growth OS</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Private lead intelligence + CRM pipeline + performance tracking for Atlas Solar in Eastern Washington</div>',
    unsafe_allow_html=True,
)

k1, k2, k3, k4 = st.columns(4)
with k1:
    kpi_card("Filtered leads", f"{len(filtered):,}", "Prospects in current intelligence view")
with k2:
    kpi_card("Avg fit score", f"{filtered['solar_fit_score'].mean():.1f}" if not filtered.empty else "0.0", "Higher = stronger solar sales target")
with k3:
    projected = filtered["estimated_annual_savings"].sum()
    kpi_card("Est. annual savings pool", money(projected), "Combined savings narrative across filtered leads")
with k4:
    open_pipeline = filtered[~filtered["stage"].isin(["Won", "Lost"])]
    pipeline_value = (open_pipeline["estimated_system_kw"] * 2800).sum() if not open_pipeline.empty else 0
    kpi_card("Open pipeline est. value", money(pipeline_value), "Rough placeholder sales value for active book")

tabs = st.tabs(["Command Center", "Lead Intelligence", "Pipeline CRM", "Performance"])

# COMMAND CENTER
with tabs[0]:
    left, right = st.columns([1.2, 0.8])
    with left:
        st.markdown("### AI suggestions")
        for item in suggestion_text(filtered):
            st.markdown(f"- {item}")
        top_targets = filtered.sort_values(["solar_fit_score", "close_probability"], ascending=False).head(10)
        view_cols = [
            "priority_rank", "display_name", "county", "property_type", "stage",
            "solar_fit_score", "est_monthly_bill", "estimated_system_kw", "assigned_rep"
        ]
        st.markdown("### Recommended targets")
        st.dataframe(
            top_targets[view_cols].rename(
                columns={
                    "priority_rank": "Rank",
                    "display_name": "Prospect",
                    "property_type": "Type",
                    "solar_fit_score": "Fit Score",
                    "est_monthly_bill": "Est. Bill/mo",
                    "estimated_system_kw": "System kW",
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
            fig = px.bar(stage_mix, x="stage", y="count", color="stage", color_discrete_map={s: stage_color(s) for s in stage_mix["stage"]})
            fig.update_layout(height=360, showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No stage data for the current filters.")

# LEAD INTELLIGENCE
with tabs[1]:
    c1, c2 = st.columns([1.3, 0.7])
    with c1:
        st.markdown("### Satellite lead map")
        st.caption("Blue dots are AI-ranked Atlas prospects. Click a dot to inspect that target.")
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
        "solar_fit_score", "close_probability", "est_monthly_bill", "estimated_system_kw", "assigned_rep"
    ]].rename(columns={
        "prospect_id": "ID",
        "display_name": "Prospect",
        "property_type": "Type",
        "solar_fit_score": "Fit Score",
        "close_probability": "Close %",
        "est_monthly_bill": "Est. Bill/mo",
        "estimated_system_kw": "System kW",
        "assigned_rep": "Rep",
    })
    st.dataframe(lead_table, use_container_width=True, hide_index=True)

# PIPELINE CRM
with tabs[2]:
    c1, c2 = st.columns([1.0, 1.0])
    with c1:
        st.markdown("### Pipeline board")
        stage_counts = filtered.groupby("stage").size().reindex(PIPELINE_STAGES, fill_value=0)
        board_cols = st.columns(4)
        cards = list(stage_counts.items())
        for idx, (stage_name, count) in enumerate(cards):
            with board_cols[idx % 4]:
                st.markdown(
                    f"""
                    <div class="atlas-card">
                        <div class="section-header" style="font-size:1rem">{stage_name}</div>
                        <div style="font-size:1.9rem;font-weight:800;color:{stage_color(stage_name)}">{count}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        st.markdown("### Active opportunities")
        active = filtered[~filtered["stage"].isin(["Won", "Lost"])].sort_values("close_probability", ascending=False)
        st.dataframe(
            active[[
                "display_name", "county", "property_type", "stage", "assigned_rep",
                "solar_fit_score", "close_probability", "last_contact_days"
            ]].rename(columns={
                "display_name": "Prospect",
                "property_type": "Type",
                "assigned_rep": "Rep",
                "solar_fit_score": "Fit Score",
                "close_probability": "Close %",
                "last_contact_days": "Days Since Contact",
            }),
            use_container_width=True,
            hide_index=True,
        )
    with c2:
        st.markdown("### Activity feed")
        if st.session_state.get("selected_prospect_id") is not None:
            sel_acts = activities[activities["prospect_id"] == st.session_state["selected_prospect_id"]].sort_values("date", ascending=False)
            if sel_acts.empty:
                st.info("No activity yet for the selected lead.")
            else:
                st.dataframe(sel_acts.rename(columns={"activity_type": "Activity", "summary": "Summary", "rep": "Rep"}), use_container_width=True, hide_index=True)
        else:
            latest = activities.sort_values("date", ascending=False).head(20)
            st.dataframe(latest.rename(columns={"activity_type": "Activity", "summary": "Summary", "rep": "Rep"}), use_container_width=True, hide_index=True)

        st.markdown("### Win / loss intelligence")
        won = filtered[filtered["stage"] == "Won"]
        lost = filtered[filtered["stage"] == "Lost"]
        st.write(f"**Won in current view:** {len(won)}")
        st.write(f"**Lost in current view:** {len(lost)}")
        if not filtered.empty:
            st.write(f"**Weighted average close probability:** {int(filtered['close_probability'].mean() * 100)}%")
            hottest = filtered.sort_values("close_probability", ascending=False).head(3)["display_name"].tolist()
            st.write("**Best immediate follow-ups:** " + ", ".join(hottest))

# PERFORMANCE
with tabs[3]:
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
        st.dataframe(by_rep.rename(columns={
            "assigned_rep": "Rep",
            "avg_fit": "Avg Fit Score",
            "avg_close": "Avg Close %",
        }), use_container_width=True, hide_index=True)
    with b2:
        county_perf = filtered.groupby("county").agg(
            leads=("prospect_id", "count"),
            avg_fit=("solar_fit_score", "mean"),
            avg_bill=("est_monthly_bill", "mean"),
        ).reset_index().sort_values("avg_fit", ascending=False)
        st.markdown("### County performance snapshot")
        st.dataframe(county_perf.rename(columns={
            "avg_fit": "Avg Fit Score",
            "avg_bill": "Avg Est. Bill/mo",
        }), use_container_width=True, hide_index=True)

st.markdown("---")
st.caption("Atlas V1 uses legally safer public-intelligence patterns: public parcel/context signals, public utility/rate context, internal CRM data, and estimated economics. It does not depend on private utility bill scraping.")
