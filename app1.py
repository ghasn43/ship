# app.py
# Ship Management System (Streamlit + SQLite)
# Full app with Fleet photos (multi-upload), Crew, Voyages, Finance, Maintenance, Dashboard
# Paste Part 1, then Part 2, then Part 3 into ONE file.

import streamlit as st
import sqlite3
import pandas as pd
from datetime import date
import matplotlib.pyplot as plt
import os
from contextlib import contextmanager

st.set_page_config(page_title="Ship Management System", page_icon="🚢", layout="wide")

DB_PATH = "ship_mgmt.db"
PHOTO_DIR = "photos"
os.makedirs(PHOTO_DIR, exist_ok=True)

# ---------------------------
# DB helpers
# ---------------------------
@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.commit()
        conn.close()

def init_db():
    with get_conn() as conn:
        c = conn.cursor()

        c.execute("""CREATE TABLE IF NOT EXISTS vessels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            imo TEXT UNIQUE,
            flag TEXT,
            vessel_type TEXT,
            gross_tonnage REAL,
            deadweight REAL,
            built_year INTEGER,
            owner TEXT,
            status TEXT
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vessel_id INTEGER,
            file_name TEXT,
            upload_date TEXT,
            FOREIGN KEY(vessel_id) REFERENCES vessels(id) ON DELETE CASCADE
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS crew (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            rank TEXT,
            nationality TEXT,
            cert_expiry TEXT,
            day_rate REAL,
            vessel_id INTEGER,
            FOREIGN KEY (vessel_id) REFERENCES vessels(id) ON DELETE SET NULL
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS voyages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vessel_id INTEGER NOT NULL,
            origin TEXT,
            destination TEXT,
            etd TEXT,
            eta TEXT,
            distance_nm REAL,
            charter_income REAL,
            notes TEXT,
            FOREIGN KEY (vessel_id) REFERENCES vessels(id) ON DELETE CASCADE
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS cargo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voyage_id INTEGER NOT NULL,
            description TEXT,
            quantity REAL,
            unit TEXT,
            FOREIGN KEY (voyage_id) REFERENCES voyages(id) ON DELETE CASCADE
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS bunkers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voyage_id INTEGER NOT NULL,
            entry_date TEXT,
            fuel_type TEXT,
            qty_tons REAL,
            price_per_ton REAL,
            FOREIGN KEY (voyage_id) REFERENCES voyages(id) ON DELETE CASCADE
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS finance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voyage_id INTEGER,
            entry_date TEXT,
            category TEXT,
            amount REAL,
            currency TEXT DEFAULT 'USD',
            notes TEXT,
            FOREIGN KEY (voyage_id) REFERENCES voyages(id) ON DELETE SET NULL
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS maintenance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vessel_id INTEGER NOT NULL,
            entry_date TEXT,
            maint_type TEXT,
            description TEXT,
            cost REAL,
            status TEXT,
            FOREIGN KEY (vessel_id) REFERENCES vessels(id) ON DELETE CASCADE
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS drills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vessel_id INTEGER NOT NULL,
            entry_date TEXT,
            drill_type TEXT,
            remarks TEXT,
            FOREIGN KEY (vessel_id) REFERENCES vessels(id) ON DELETE CASCADE
        )""")

def df(sql, params=None):
    with get_conn() as conn:
        return pd.read_sql_query(sql, conn, params=params or ())

def exec_sql(sql, params=None):
    with get_conn() as conn:
        conn.execute(sql, params or ())

def safe_float(x):
    try:
        return float(x)
    except:
        return 0.0

# ---------------------------
# Dashboard
# ---------------------------
def page_dashboard():
    st.title("📊 Dashboard")

    vessels = df("SELECT * FROM vessels")
    crew_df = df("SELECT * FROM crew")
    voyages_df = df("SELECT * FROM voyages")
    finance_df = df("SELECT * FROM finance")
    bunkers_df = df("SELECT * FROM bunkers")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Vessels", len(vessels))
    c2.metric("Active Crew", len(crew_df))
    c3.metric("Voyages", len(voyages_df))
    total_cost = finance_df["amount"].sum() if not finance_df.empty else 0
    c4.metric("Total Costs (USD)", f"${total_cost:,.0f}")

    st.divider()
    st.subheader("Voyage Profit / Loss Snapshot")

    if voyages_df.empty:
        st.info("No voyages yet. Add voyages in **Voyages & Cargo**.")
        return

    # bunker costs per voyage
    if not bunkers_df.empty:
        bunkers_df["bunker_cost"] = bunkers_df["qty_tons"].fillna(0) * bunkers_df["price_per_ton"].fillna(0)
        bunker_costs = bunkers_df.groupby("voyage_id")["bunker_cost"].sum().reset_index()
    else:
        bunker_costs = pd.DataFrame(columns=["voyage_id", "bunker_cost"])

    # finance costs per voyage
    if not finance_df.empty:
        fin_costs = finance_df.groupby("voyage_id")["amount"].sum().reset_index().fillna(0)
        fin_costs.rename(columns={"amount": "finance_cost"}, inplace=True)
    else:
        fin_costs = pd.DataFrame(columns=["voyage_id", "finance_cost"])

    pl = voyages_df[["id", "origin", "destination", "charter_income"]].copy()
    pl = pl.merge(bunker_costs, left_on="id", right_on="voyage_id", how="left").drop(columns=["voyage_id"])
    pl = pl.merge(fin_costs, left_on="id", right_on="voyage_id", how="left").drop(columns=["voyage_id"])
    pl["bunker_cost"] = pl["bunker_cost"].fillna(0.0)
    pl["finance_cost"] = pl["finance_cost"].fillna(0.0)
    pl["income"] = pl["charter_income"].fillna(0.0)
    pl["profit"] = pl["income"] - (pl["bunker_cost"] + pl["finance_cost"])
    pl["voyage"] = pl["origin"].fillna("?") + " → " + pl["destination"].fillna("?")

    st.dataframe(
        pl[["id", "voyage", "income", "bunker_cost", "finance_cost", "profit"]]
        .rename(columns={
            "id": "Voyage ID",
            "income": "Income (USD)",
            "bunker_cost": "Bunker Cost (USD)",
            "finance_cost": "Finance Cost (USD)",
            "profit": "Profit (USD)"
        }),
        use_container_width=True
    )

    fig, ax = plt.subplots()
    ax.bar(pl["voyage"], pl["profit"])
    ax.set_title("Profit by Voyage")
    ax.set_xlabel("Voyage")
    ax.set_ylabel("Profit (USD)")
    plt.xticks(rotation=30, ha="right")
    st.pyplot(fig)

# ---------------------------
# Fleet (with multi-photo upload in the vessel entry form)
# ---------------------------
def page_fleet():
    st.title("🛳 Fleet Management")

    with st.expander("➕ Add a new vessel", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            v_name = st.text_input("Vessel Name *")
            v_imo = st.text_input("IMO Number")
            v_flag = st.text_input("Flag")
            v_type = st.text_input("Vessel Type (e.g., Bulk, Tanker, Container)")
        with c2:
            v_gt = st.number_input("Gross Tonnage", min_value=0.0, value=0.0, step=1.0)
            v_dwt = st.number_input("Deadweight (DWT)", min_value=0.0, value=0.0, step=1.0)
            v_year = st.number_input("Built Year", min_value=1900, max_value=2100, value=2000, step=1)
        with c3:
            v_owner = st.text_input("Owner")
            v_status = st.selectbox("Status", ["Active", "In Dock", "Laid-up", "Repair"], index=0)
            v_photos = st.file_uploader("Upload Photos", type=["jpg","jpeg","png"], accept_multiple_files=True)

        if st.button("Add Vessel", type="primary", use_container_width=True):
            if not v_name.strip():
                st.error("Vessel name is required.")
            else:
                exec_sql("""
                    INSERT INTO vessels (name, imo, flag, vessel_type, gross_tonnage, deadweight, built_year, owner, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (v_name.strip(), v_imo.strip() or None, v_flag.strip() or None, v_type.strip() or None,
                      float(v_gt), float(v_dwt), int(v_year), v_owner.strip() or None, v_status))

                vessel_id = df("SELECT id FROM vessels WHERE name=? ORDER BY id DESC LIMIT 1", (v_name.strip(),)).iloc[0,0]

                # Save photos (if any)
                if v_photos:
                    for photo in v_photos:
                        filepath = os.path.join(PHOTO_DIR, photo.name)
                        with open(filepath, "wb") as f:
                            f.write(photo.getbuffer())
                        exec_sql("INSERT INTO photos (vessel_id, file_name, upload_date) VALUES (?, ?, ?)",
                                 (vessel_id, photo.name, str(date.today())))
                st.success("✅ Vessel added!")

    st.divider()
    st.subheader("Fleet Overview")
    vessels = df("SELECT * FROM vessels")
    st.dataframe(vessels, use_container_width=True)

    # Delete vessel
    if not vessels.empty:
        st.markdown("#### Delete a vessel")
        del_id = st.selectbox("Select Vessel ID to delete", vessels["id"].tolist())
        if st.button("Delete Selected Vessel", type="secondary"):
            exec_sql("DELETE FROM vessels WHERE id = ?", (int(del_id),))
            st.success("Vessel deleted. Refresh the page to see changes.")

    # Show photos under each vessel
    if not vessels.empty:
        st.subheader("Vessel Photos")
        for _, v in vessels.iterrows():
            photos = df("SELECT file_name, upload_date FROM photos WHERE vessel_id=?", (v["id"],))
            if not photos.empty:
                st.markdown(f"**{v['name']}**")
                cols = st.columns(3)
                for i, (_, row) in enumerate(photos.iterrows()):
                    with cols[i % 3]:
                        st.image(os.path.join(PHOTO_DIR, row["file_name"]),
                                 caption=f"{row['file_name']} ({row['upload_date']})",
                                 use_container_width=True)

# ---------------------------
# Crew
# ---------------------------
def page_crew():
    st.title("👨‍✈️ Crew Management")

    vessels = df("SELECT id, name FROM vessels")
    vessel_options = ["-- Unassigned --"] + (vessels["name"].tolist() if not vessels.empty else [])
    vessel_map = {row["name"]: row["id"] for _, row in vessels.iterrows()} if not vessels.empty else {}

    with st.expander("➕ Add a crew member", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            name = st.text_input("Name *")
            rank = st.text_input("Rank (e.g., Master, Chief Engineer)")
            nationality = st.text_input("Nationality")
        with c2:
            cert_expiry = st.date_input("Certificate Expiry", value=date.today())
            day_rate = st.number_input("Day Rate (USD)", min_value=0.0, value=0.0, step=1.0)
        with c3:
            vessel_sel = st.selectbox("Assigned Vessel", vessel_options)

        if st.button("Add Crew", type="primary", use_container_width=True):
            if not name.strip():
                st.error("Name is required.")
            else:
                vessel_id = None if vessel_sel == "-- Unassigned --" else vessel_map.get(vessel_sel)
                exec_sql("""
                    INSERT INTO crew (name, rank, nationality, cert_expiry, day_rate, vessel_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (name.strip(), rank.strip() or None, nationality.strip() or None,
                      str(cert_expiry), float(day_rate), vessel_id))
                st.success("Crew member added.")

    st.divider()
    st.subheader("Crew List")
    crew_df = df("""
        SELECT c.id, c.name, c.rank, c.nationality, c.cert_expiry, c.day_rate, v.name AS vessel
        FROM crew c LEFT JOIN vessels v ON c.vessel_id = v.id
        ORDER BY c.name
    """)
    st.dataframe(crew_df, use_container_width=True)

    # Reassign
    if not crew_df.empty:
        st.markdown("#### Reassign crew to vessel")
        crew_id = st.selectbox("Crew ID", crew_df["id"].tolist())
        new_vessel = st.selectbox("New Vessel", vessel_options, index=0)
        if st.button("Reassign"):
            vessel_id = None if new_vessel == "-- Unassigned --" else vessel_map.get(new_vessel)
            exec_sql("UPDATE crew SET vessel_id = ? WHERE id = ?", (vessel_id, int(crew_id)))
            st.success("Crew reassigned.")

# ---------------------------
# Voyages & Cargo & Bunkers
# ---------------------------
def page_voyages():
    st.title("📦 Voyages & Cargo")

    vessels = df("SELECT id, name FROM vessels")
    if vessels.empty:
        st.info("Add vessels first in **Fleet**.")
        return
    vessel_map = {row["name"]: row["id"] for _, row in vessels.iterrows()}

    with st.expander("➕ Plan a voyage", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            vessel_name = st.selectbox("Vessel *", vessels["name"].tolist())
            origin = st.text_input("Origin")
            destination = st.text_input("Destination")
        with c2:
            etd = st.date_input("ETD", value=date.today())
            eta = st.date_input("ETA", value=date.today())
            distance = st.number_input("Distance (nm)", min_value=0.0, value=0.0, step=1.0)
        with c3:
            income = st.number_input("Charter Income (USD)", min_value=0.0, value=0.0, step=1000.0)
            notes = st.text_input("Notes")

        if st.button("Create Voyage", type="primary", use_container_width=True):
            exec_sql("""
                INSERT INTO voyages (vessel_id, origin, destination, etd, eta, distance_nm, charter_income, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (vessel_map[vessel_name], origin.strip() or None, destination.strip() or None,
                  str(etd), str(eta), float(distance), float(income), notes.strip() or None))
            st.success("Voyage created.")

    st.divider()
    voyages = df("""
        SELECT vo.id, v.name AS vessel, vo.origin, vo.destination, vo.etd, vo.eta, vo.distance_nm, vo.charter_income
        FROM voyages vo JOIN vessels v ON vo.vessel_id = v.id
        ORDER BY vo.id DESC
    """)
    st.dataframe(voyages, use_container_width=True)
    if voyages.empty:
        return

    st.markdown("#### Manage Cargo & Bunkers")
    vid_list = voyages["id"].tolist()
    vid = st.selectbox("Voyage ID", vid_list)

    # Cargo
    with st.expander("Cargo", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            cargo_desc = st.text_input("Description")
        with c2:
            cargo_qty = st.number_input("Quantity", min_value=0.0, value=0.0, step=1.0)
        with c3:
            cargo_unit = st.text_input("Unit (e.g., tons, TEU)")
        if st.button("Add Cargo"):
            exec_sql("INSERT INTO cargo (voyage_id, description, quantity, unit) VALUES (?, ?, ?, ?)",
                     (int(vid), cargo_desc.strip() or None, float(cargo_qty), cargo_unit.strip() or None))
            st.success("Cargo added.")
        cargo_df = df("SELECT id, description, quantity, unit FROM cargo WHERE voyage_id = ?", (int(vid),))
        st.dataframe(cargo_df, use_container_width=True)

    # Bunkers
    with st.expander("Bunkers", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            bunker_date = st.date_input("Date", value=date.today(), key="bunker_date")
            fuel_type = st.selectbox("Fuel Type", ["VLSFO", "MGO", "HSFO", "LNG", "Other"], key="fuel_type")
        with c2:
            qty_tons = st.number_input("Quantity (tons)", min_value=0.0, value=0.0, step=0.1, key="qty_tons")
        with c3:
            price_ton = st.number_input("Price per ton (USD)", min_value=0.0, value=0.0, step=1.0, key="price_ton")
        if st.button("Add Bunker Entry", key="add_bunker"):
            exec_sql("""
                INSERT INTO bunkers (voyage_id, entry_date, fuel_type, qty_tons, price_per_ton)
                VALUES (?, ?, ?, ?, ?)
            """, (int(vid), str(bunker_date), fuel_type, float(qty_tons), float(price_ton)))
            st.success("Bunker entry added.")
        bunk_df = df("""
            SELECT id, entry_date, fuel_type, qty_tons, price_per_ton, (qty_tons * price_per_ton) AS total
            FROM bunkers WHERE voyage_id = ?
        """, (int(vid),))
        st.dataframe(bunk_df, use_container_width=True)

# ---------------------------
# Finance (with Voyage P&L)
# ---------------------------
def page_finance():
    st.title("💰 Finance & Accounting")

    st.subheader("Add Expense / Cost")
    voyages = df("SELECT id, origin, destination FROM voyages")
    voyage_opts = ["-- General (no voyage) --"] + ([f"{r['id']} | {r['origin']} → {r['destination']}" for _, r in voyages.iterrows()] if not voyages.empty else [])
    voyage_id_map = {}
    if not voyages.empty:
        for _, r in voyages.iterrows():
            voyage_id_map[f"{r['id']} | {r['origin']} → {r['destination']}"] = r["id"]

    c1, c2, c3 = st.columns(3)
    with c1:
        voyage_sel = st.selectbox("Voyage", voyage_opts, index=0)
        entry_date = st.date_input("Date", value=date.today())
    with c2:
        category = st.selectbox("Category", ["Fuel", "Port Fees", "Repairs", "Crew Salaries", "Agency", "Other"])
        amount = st.number_input("Amount (USD)", min_value=0.0, value=0.0, step=100.0)
    with c3:
        currency = st.text_input("Currency", value="USD")
        notes = st.text_input("Notes")

    if st.button("Add Finance Entry", type="primary"):
        vid = None if voyage_sel.startswith("--") else voyage_id_map.get(voyage_sel)
        exec_sql("""
            INSERT INTO finance (voyage_id, entry_date, category, amount, currency, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (vid, str(entry_date), category, float(amount), currency.strip() or "USD", notes.strip() or None))
        st.success("Finance entry added.")

    st.divider()
    st.subheader("Finance Table")
    finance_df = df("""
        SELECT f.id, f.entry_date, f.category, f.amount, f.currency, f.notes,
               vo.id AS voyage_id, vo.origin, vo.destination
        FROM finance f
        LEFT JOIN voyages vo ON f.voyage_id = vo.id
        ORDER BY f.entry_date DESC, f.id DESC
    """)
    st.dataframe(finance_df, use_container_width=True)

    # Filter & export
    st.markdown("#### Filter & Export")
    colf1, colf2, colf3 = st.columns(3)
    with colf1:
        cat_filter = st.multiselect("Filter Category", sorted(finance_df["category"].dropna().unique().tolist()) if not finance_df.empty else [])
    with colf2:
        voyage_filter = st.multiselect("Filter Voyage",
            [str(v) for v in finance_df["voyage_id"].dropna().unique().tolist()] if not finance_df.empty else [])
    with colf3:
        btn_csv = st.button("Export CSV")

    filtered = finance_df.copy()
    if not filtered.empty and cat_filter:
        filtered = filtered[filtered["category"].isin(cat_filter)]
    if not filtered.empty and voyage_filter:
        filtered = filtered[filtered["voyage_id"].astype(str).isin(voyage_filter)]

    st.dataframe(filtered, use_container_width=True)
    if btn_csv:
        st.download_button("Download finance.csv", filtered.to_csv(index=False).encode(), file_name="finance.csv")

    # P&L
    st.divider()
    st.subheader("Voyage Profit & Loss")
    voyages_pl = df("SELECT id, origin, destination, charter_income FROM voyages ORDER BY id DESC")
    if voyages_pl.empty:
        st.info("No voyages yet.")
        return

    choice = st.selectbox("Select voyage", [f"{r['id']} | {r['origin']} → {r['destination']}" for _, r in voyages_pl.iterrows()])
    v_id = int(choice.split("|")[0].strip())

    costs = df("SELECT category, amount FROM finance WHERE voyage_id = ?", (v_id,))
    total_fin_cost = costs["amount"].sum() if not costs.empty else 0.0
    bunk = df("SELECT qty_tons, price_per_ton FROM bunkers WHERE voyage_id = ?", (v_id,))
    bunk_cost = (bunk["qty_tons"] * bunk["price_per_ton"]).sum() if not bunk.empty else 0.0

    income = float(voyages_pl[voyages_pl["id"] == v_id]["charter_income"].iloc[0] or 0.0)
    profit = income - (total_fin_cost + bunk_cost)

    c1, c2, c3 = st.columns(3)
    c1.metric("Income (USD)", f"${income:,.0f}")
    c2.metric("Total Costs (USD)", f"${(total_fin_cost + bunk_cost):,.0f}")
    c3.metric("Profit/Loss (USD)", f"${profit:,.0f}")

    st.markdown("#### Cost Breakdown (Bar)")
    cost_breakdown = pd.DataFrame([
        {"Category": "Finance Costs (excl. bunkers)", "Amount": total_fin_cost},
        {"Category": "Bunker Costs", "Amount": bunk_cost},
    ])
    fig, ax = plt.subplots()
    ax.bar(cost_breakdown["Category"], cost_breakdown["Amount"])
    ax.set_title("Cost Breakdown")
    ax.set_ylabel("USD")
    plt.xticks(rotation=15)
    st.pyplot(fig)

# ---------------------------
# Maintenance & Safety
# ---------------------------
def page_maintenance():
    st.title("⚙️ Maintenance & Safety")

    vessels = df("SELECT id, name FROM vessels")
    if vessels.empty:
        st.info("Add vessels first in **Fleet**.")
        return
    vessel_map = {row["name"]: row["id"] for _, row in vessels.iterrows()}

    with st.expander("➕ Add Maintenance", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            vessel_name = st.selectbox("Vessel *", vessels["name"].tolist())
            entry_date = st.date_input("Date", value=date.today())
        with c2:
            maint_type = st.selectbox("Type", ["Planned", "Corrective", "Dry-dock", "Inspection"])
            cost = st.number_input("Cost (USD)", min_value=0.0, value=0.0, step=100.0)
        with c3:
            status = st.selectbox("Status", ["Planned", "In-progress", "Done"])
            description = st.text_input("Description")

        if st.button("Add Maintenance", type="primary"):
            exec_sql("""
                INSERT INTO maintenance (vessel_id, entry_date, maint_type, description, cost, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (vessel_map[vessel_name], str(entry_date), maint_type, description.strip() or None, float(cost), status))
            st.success("Maintenance entry added.")

    with st.expander("➕ Add Safety Drill", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            vessel_name2 = st.selectbox("Vessel", vessels["name"].tolist(), key="drill_vessel")
            drill_date = st.date_input("Drill Date", value=date.today(), key="drill_date")
        with c2:
            drill_type = st.selectbox("Drill Type", ["Fire", "Abandon Ship", "Enclosed Space", "Oil Spill", "Man Overboard", "Other"])
            remarks = st.text_input("Remarks")
        if st.button("Add Drill"):
            exec_sql("""
                INSERT INTO drills (vessel_id, entry_date, drill_type, remarks)
                VALUES (?, ?, ?, ?)
            """, (vessel_map[vessel_name2], str(drill_date), drill_type, remarks.strip() or None))
            st.success("Drill logged.")

    st.divider()
    st.subheader("Maintenance Log")
    mt = df("""
        SELECT m.id, v.name AS vessel, m.entry_date, m.maint_type, m.description, m.cost, m.status
        FROM maintenance m JOIN vessels v ON m.vessel_id = v.id
        ORDER BY m.entry_date DESC, m.id DESC
    """)
    st.dataframe(mt, use_container_width=True)

    st.subheader("Drill Log")
    dr = df("""
        SELECT d.id, v.name AS vessel, d.entry_date, d.drill_type, d.remarks
        FROM drills d JOIN vessels v ON d.vessel_id = v.id
        ORDER BY d.entry_date DESC, d.id DESC
    """)
    st.dataframe(dr, use_container_width=True)

# ---------------------------
# About
# ---------------------------
def page_about():
    st.title("ℹ️ About")
    st.write(
        "This prototype demonstrates core ship-management workflows:\n"
        "- Fleet records & photos\n"
        "- Crew profiles & assignments\n"
        "- Voyage planning with cargo & bunker logs\n"
        "- Finance costs & voyage P&L\n"
        "- Maintenance & safety drills\n\n"
        "You can evolve it into a production system using FastAPI/Django, PostgreSQL, user auth, and role-based access."
    )

# ---------------------------
# Router
# ---------------------------
def main():
    init_db()
    st.sidebar.title("🚢 Ship Management")
    page = st.sidebar.radio(
        "Go to",
        ["Dashboard", "Fleet", "Crew", "Voyages & Cargo", "Finance", "Maintenance & Safety", "About"]
    )

    if page == "Dashboard":
        page_dashboard()
    elif page == "Fleet":
        page_fleet()
    elif page == "Crew":
        page_crew()
    elif page == "Voyages & Cargo":
        page_voyages()
    elif page == "Finance":
        page_finance()
    elif page == "Maintenance & Safety":
        page_maintenance()
    else:
        page_about()

if __name__ == "__main__":
    main()
