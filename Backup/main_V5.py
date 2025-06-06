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
    full_df.drop(columns=["created_at", "updated_at"], inplace=True, errors="ignore")

    # Ajouter colonne "date_livraison" extraite du champ "name"
    full_df["date_livraison"] = full_df["name"].apply(extract_date_from_name)

    # Garder uniquement les lignes à partir de cette semaine
    today = datetime.today()
    start_week = today - timedelta(days=today.weekday())
    df_semaine = full_df[
        full_df["date_livraison"].notnull() &
        (full_df["date_livraison"] >= start_week)
    ].copy()

    # Renommer colonne name → Plat
    df_semaine.rename(columns={"name": "Plat"}, inplace=True)

    # Ajouter colonnes nécessaires
    df_semaine["index_ligne"] = range(1, len(df_semaine) + 1)
    df_semaine["order_number"] = df_semaine["order_number"].astype(str)
    if "Itinéraire" not in df_semaine.columns:
        df_semaine["Itinéraire"] = ""

    # Dropdowns
    plats_disponibles = sorted(df_semaine["Plat"].dropna().unique())
    noms_clients = sorted(df_semaine["Nom"].dropna().unique())
    sources = ["web", "non web"]

    # Map client
    info_cols = ["Nom", "customer_id", "email", "telephone", "adresse", "ville"]
    clients_df_unique = clients_df[info_cols].drop_duplicates()
    nom_counts = clients_df_unique["Nom"].value_counts()
    noms_uniques = nom_counts[nom_counts == 1].index
    clients_df_filtered = clients_df_unique[clients_df_unique["Nom"].isin(noms_uniques)]

    if nom_counts[nom_counts > 1].any():
        st.warning("⚠️ Certains noms ont des infos différentes. Seuls les noms uniques sont utilisés.")

    client_info_map = clients_df_filtered.set_index("Nom").to_dict("index")

    # Numéro de commande max pour génération
    max_order_number = (
        df_semaine["order_number"].dropna()
        .astype(str)
        .str.extract(r"(\d+)")
        .astype(float)
        .max()[0]
        if not df_semaine["order_number"].dropna().empty else 0
    )
    next_order_number = int(max_order_number) + 1

    # === TABLE ÉDITABLE ===
    st.subheader("📝 Édition des commandes à partir de cette semaine")
    base_df = df_semaine.copy()

    edited_df = st.data_editor(
        base_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "index_ligne": st.column_config.NumberColumn("Ligne #", required=True, disabled=True),
            "Plat": st.column_config.SelectboxColumn("Plat", options=plats_disponibles, required=True),
            "Nom": st.column_config.SelectboxColumn("Nom", options=noms_clients, required=True),
            "order_number": st.column_config.TextColumn("Numéro de commande"),
            "quantity": st.column_config.NumberColumn("Quantité", default=1, min_value=1),
            "price": st.column_config.NumberColumn("Prix (€)", default=0.0, step=0.5),
            "Itinéraire": st.column_config.SelectboxColumn("Itinéraire", options=[str(i) for i in range(1, 6)], required=False),
            "source_name": st.column_config.SelectboxColumn("Source", options=sources, required=True),
        }
    )

    for idx, row in edited_df.iterrows():
        nom = row.get("Nom")
        if nom in client_info_map:
            for champ in ["email", "telephone", "adresse", "ville", "customer_id"]:
                edited_df.at[idx, champ] = client_info_map[nom].get(champ, "")

        if pd.isna(row.get("index_ligne")):
            edited_df.at[idx, "index_ligne"] = idx + 1
        if pd.isna(row.get("order_number")) or str(row.get("order_number")).strip() == "":
            edited_df.at[idx, "order_number"] = f"999{next_order_number + idx}"

    # === TABLE NON ÉDITABLE ===
    st.subheader("📋 Données actualisées")
    st.dataframe(edited_df, use_container_width=True)

    # === SAUVEGARDE DES DONNÉES ===
    if st.button("💾 Sauvegarder les modifications"):
        fichier_csv = "commandes.csv"
        if os.path.exists(fichier_csv):
            df_exist = pd.read_csv(fichier_csv)
            # Retirer les lignes de cette semaine
            def extract_date_from_plat(plat):
                match = re.search(r"\b(\d{2}/\d{2})\b", str(plat))
                if match:
                    try:
                        return datetime.strptime(match.group(1) + f"/{datetime.today().year}", "%d/%m/%Y")
                    except:
                        return None
                return None

            df_exist["date_plat"] = df_exist["Plat"].apply(extract_date_from_plat)
            df_exist = df_exist[
                df_exist["date_plat"].isnull() | (df_exist["date_plat"] < start_week)
            ].drop(columns=["date_plat"], errors="ignore")

            df_final = pd.concat([df_exist, edited_df], ignore_index=True)
        else:
            df_final = edited_df

        df_final.to_csv(fichier_csv, index=False)
        st.success("✅ Données sauvegardées dans commandes.csv !")

else:
    st.warning("Aucune commande récupérée.")
