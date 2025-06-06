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

# === Récupérer les commandes Shopify ===
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
            order_number = order.get("order_number")
            source_name = order.get("source_name")
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
                    "customer_id": customer_id,
                    "name": name,
                    "quantity": quantity,
                    "price": price,
                    "source_name": source_name,
                    "note": note,
                    "financial_status": financial_status
                })

        return pd.DataFrame(rows)
    else:
        st.error(f"Erreur Shopify : {response.status_code}")
        return pd.DataFrame()

# === Charger infos clients depuis fichiers CSV ===
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
        else:
            st.warning(f"Fichier pour le client {cid} non trouvé.")
    return pd.DataFrame(client_data)

# === Extraire la date du champ "name" ===
def extract_date_from_name(name):
    match = re.search(r"\b(\d{2}/\d{2})\b", name)
    if match:
        try:
            return datetime.strptime(match.group(1) + f"/{datetime.today().year}", "%d/%m/%Y")
        except:
            return None
    return None

# === Début logique principale ===
orders_df = get_shopify_orders_dataframe()

if not orders_df.empty:
    unique_ids = orders_df["customer_id"].dropna().unique()
    clients_df = get_client_details_df(unique_ids, folder_path=CUSTOMER_PATH)

    # Fusion des infos clients
    full_df = orders_df.merge(clients_df, on="customer_id", how="left")

    # Supprimer colonnes inutiles
    if "created_at" in full_df.columns:
        full_df.drop(columns=["created_at", "updated_at"], inplace=True, errors="ignore")

    # Ajouter colonne "date_livraison" extraite du champ "name"
    full_df["date_livraison"] = full_df["name"].apply(extract_date_from_name)

    # Garder uniquement les lignes de cette semaine
    today = datetime.today()
    start_week = today - timedelta(days=today.weekday())
    end_week = start_week + timedelta(days=6)
    df_semaine = full_df[
        full_df["date_livraison"].notnull() &
        (full_df["date_livraison"] >= start_week) &
        (full_df["date_livraison"] <= end_week)
    ].copy()

    # Renommer colonnes pour l'édition
    df_semaine.rename(columns={"name": "Plat"}, inplace=True)
    df_semaine["index_ligne"] = range(1, len(df_semaine) + 1)

    # Colonnes dropdown
    plats_disponibles = sorted(df_semaine["Plat"].dropna().unique())
    noms_clients = sorted(df_semaine["Nom"].dropna().unique())

    # === Table éditable ===
    st.subheader("📝 Édition des commandes de la semaine")

    edited_df = st.data_editor(
        df_semaine.drop(columns=["date_livraison"]),
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Plat": st.column_config.SelectboxColumn(
                label="Plat",
                options=plats_disponibles,
                required=True
            ),
            "Nom": st.column_config.SelectboxColumn(
                label="Nom",
                options=noms_clients,
                required=True
            )
        }
    )

    # === Remplissage auto des infos client à partir du nom ===
    info_cols = ["Nom", "email", "telephone", "adresse", "ville"]
    clients_df_unique = clients_df[info_cols].drop_duplicates()

    # Compter combien de fois chaque nom apparaît
    nom_counts = clients_df_unique["Nom"].value_counts()

    # Garde uniquement les noms qui apparaissent UNE SEULE FOIS
    noms_uniques = nom_counts[nom_counts == 1].index
    clients_df_filtered = clients_df_unique[clients_df_unique["Nom"].isin(noms_uniques)]

    # Prévenir s’il y a des conflits
    if nom_counts[nom_counts > 1].any():
        st.warning("⚠️ Certains clients ont des noms identiques mais des informations différentes. Ils ont été exclus de l'autoremplissage.")

    # Construire la map
    client_info_map = clients_df_filtered.set_index("Nom").to_dict("index")


    for idx, row in edited_df.iterrows():
        nom = row.get("Nom")
        if nom in client_info_map:
            for champ in ["email", "telephone", "adresse", "ville"]:
                edited_df.at[idx, champ] = client_info_map[nom].get(champ, "")

    # === Affichage tableau final ===
    st.subheader("📋 Données actualisées (non éditables)")
    st.dataframe(edited_df, use_container_width=True)
else:
    st.warning("Aucune commande récupérée.")
