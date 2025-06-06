import streamlit as st
import pandas as pd
import requests
import os
import re
from datetime import datetime, timedelta

st.set_page_config(page_title="Commandes Shopify enrichies", layout="wide")
st.title("🛍️ Commandes Shopify enrichies avec données clients")

# === Lecture des paramètres depuis param.txt ===
params = {}
with open("param.txt", "r") as f:
    exec(f.read(), params)

SHOPIFY_DOMAIN = params["SHOPIFY_DOMAIN"]
ACCESS_TOKEN = params["ACCESS_TOKEN"]
CUSTOMER_PATH = params["CUSTOMER_PATH"]
API_VERSION = "2025-01"

# === Récupération des commandes Shopify ===
@st.cache_data(show_spinner="Chargement des commandes depuis Shopify...")
def get_shopify_orders_dataframe():
    url = f"https://{SHOPIFY_DOMAIN}/admin/api/{API_VERSION}/orders.json?status=any&limit=250"
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": ACCESS_TOKEN
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        orders = response.json().get("orders", [])
        rows = []
        for order in orders:
            created_at = order.get("created_at")
            order_number = order.get("order_number")
            source_name = order.get("source_name", "non web")
            note = order.get("note")
            financial_status = order.get("financial_status")
            customer = order.get("customer", {})
            customer_id = customer.get("id", None)
            for item in order.get("line_items", []):
                name = item.get("name")
                quantity = item.get("quantity", 1)
                price = float(item.get("price", 0))
                rows.append({
                    "order_number": order_number,
                    "created_at": created_at,
                    "customer_id": customer_id,
                    "name": name,
                    "quantity": quantity,
                    "price": price,
                    "source_name": source_name if source_name == "web" else "non web",
                    "note": note,
                    "financial_status": financial_status
                })
        return pd.DataFrame(rows)
    else:
        st.error(f"Erreur Shopify : {response.status_code}")
        return pd.DataFrame()

# === Chargement des infos clients depuis les fichiers CSV ===
def get_client_details_df(customer_ids, folder_path=CUSTOMER_PATH):
    client_data = []
    for cid in customer_ids:
        file_path = os.path.join(folder_path, f"{cid}.csv")
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    line = f.readline().strip()
                    fields = line.split(";")
                    if len(fields) >= 8:
                        client_data.append({
                            "customer_id": cid,
                            "email": fields[0],
                            "Nom": f"{fields[3]} {fields[4]}",
                            "telephone": fields[5],
                            "adresse": fields[6],
                            "ville": fields[7]
                        })
            except Exception as e:
                st.warning(f"Erreur lecture fichier client {cid}: {e}")
    return pd.DataFrame(client_data)

# === Extraire date DD/MM du champ name ===
def extract_date_from_name(name):
    match = re.search(r"\b(\d{2}/\d{2})\b", str(name))
    if match:
        try:
            return datetime.strptime(match.group(1) + f"/{datetime.today().year}", "%d/%m/%Y")
        except:
            return None
    return None

# === MAIN LOGIC ===
orders_df = get_shopify_orders_dataframe()

if not orders_df.empty:
    orders_df["created_at"] = pd.to_datetime(orders_df["created_at"])
    debut_annee = pd.Timestamp(datetime(datetime.today().year, 1, 1)).tz_localize("UTC")
    orders_df = orders_df[orders_df["created_at"] >= debut_annee]

    # Ajouter date livraison
    orders_df["date_livraison"] = orders_df["name"].apply(extract_date_from_name)
    start_week = datetime.today() - timedelta(days=datetime.today().weekday())
    orders_df = orders_df[
        orders_df["date_livraison"].notnull() &
        (orders_df["date_livraison"] >= start_week)
    ]

    # Préparer données clients
    unique_ids = orders_df["customer_id"].dropna().unique()
    clients_df = get_client_details_df(unique_ids, folder_path=CUSTOMER_PATH)
    full_df = orders_df.merge(clients_df, on="customer_id", how="left")

    full_df.rename(columns={"name": "Plat"}, inplace=True)
    full_df["order_number"] = full_df["order_number"].astype(str)

    # Dropdown options
    plats_disponibles = sorted(full_df["Plat"].dropna().unique())
    noms_clients = sorted(full_df["Nom"].dropna().unique())
    sources = ["web", "non web"]

    # Dictionnaire Plat → prix
    prix_par_plat = full_df.dropna(subset=["Plat", "price"]).drop_duplicates("Plat").set_index("Plat")["price"].to_dict()

    # Dictionnaire Nom → infos clients
    clients_info = clients_df.drop_duplicates("Nom").set_index("Nom").to_dict("index")

    # === TABLEAU 1 : Données Shopify (éditable) ===
    st.subheader("🟦 Commandes Shopify existantes")

    # S'assurer que la colonne Itinéraire existe
    if "Itinéraire" not in full_df.columns:
        full_df["Itinéraire"] = ""


    base_shopify = full_df[["order_number", "Plat", "Nom", "quantity", "source_name", "Itinéraire"]].copy()
    # Préparer les options dropdown
    plats_disponibles = sorted(full_df["Plat"].dropna().unique())
    noms_clients = sorted(full_df["Nom"].dropna().unique())
    sources = ["web", "non web"]
    itineraire_options = [str(i) for i in range(1, 6)]
    edited_shopify = st.data_editor(
        base_shopify,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Plat": st.column_config.SelectboxColumn("Plat", options=plats_disponibles, required=True),
            "Nom": st.column_config.SelectboxColumn("Nom", options=noms_clients, required=True),
            "source_name": st.column_config.SelectboxColumn("Source", options=sources, required=True),
            "Itinéraire": st.column_config.SelectboxColumn("Itinéraire", options=itineraire_options, required=False)
        }
    )

    # === TABLEAU 2 : Nouvelles lignes (vide, éditable) ===
    st.subheader("🟨 Ajouter de nouvelles commandes")
    colonnes = ["order_number", "Plat", "Nom", "quantity", "source_name", "Itinéraire"]
    empty_df = pd.DataFrame(columns=colonnes)
    # Préparer les options dropdown
    plats_disponibles = sorted(full_df["Plat"].dropna().unique())
    noms_clients = sorted(full_df["Nom"].dropna().unique())
    sources = ["web", "non web"]
    itineraire_options = [str(i) for i in range(1, 6)]
    edited_new = st.data_editor(
        empty_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Plat": st.column_config.SelectboxColumn("Plat", options=plats_disponibles, required=True),
            "Nom": st.column_config.SelectboxColumn("Nom", options=noms_clients, required=True),
            "source_name": st.column_config.SelectboxColumn("Source", options=sources, required=True),
            "Itinéraire": st.column_config.SelectboxColumn("Itinéraire", options=itineraire_options, required=False)
        }
    )

    # === COMBINAISON des deux ===
    combined = pd.concat([edited_shopify, edited_new], ignore_index=True).fillna("")

    # Remplissage automatique : client + prix + total
    for idx, row in combined.iterrows():
        nom = row.get("Nom")
        plat = row.get("Plat")
        combined.at[idx, "price"] = prix_par_plat.get(plat, 0.0)
        combined.at[idx, "total"] = combined.at[idx, "price"] * float(row.get("quantity") or 0)

        if nom in clients_info:
            for champ in ["email", "telephone", "adresse", "ville", "customer_id"]:
                combined.at[idx, champ] = clients_info[nom].get(champ, "")

    # === TABLEAU FINAL NON ÉDITABLE ===
    st.subheader("🟩 Commandes consolidées (non éditables)")
    st.dataframe(combined, use_container_width=True)

    # === SAUVEGARDE ===
    if st.button("💾 Sauvegarder dans commandes.csv"):
        combined.to_csv("commandes.csv", index=False)
        st.success("✅ Données sauvegardées dans commandes.csv !")

else:
    st.warning("Aucune commande récupérée depuis Shopify.")
