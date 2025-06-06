import streamlit as st
import pandas as pd
import requests
import os

st.set_page_config(page_title="Commandes Shopify enrichies", layout="wide")
st.title("🛍️ Commandes Shopify enrichies avec données clients")

# === Lecture des paramètres depuis param.txt ===
params = {}
with open("param.txt", "r") as f:
    exec(f.read(), params)

SHOPIFY_DOMAIN = params["SHOPIFY_DOMAIN"]
ACCESS_TOKEN = params["ACCESS_TOKEN"]
API_VERSION = "2025-01"

# === Fonction pour récupérer les commandes Shopify ===
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
                rows.append({
                    "order_number": order_number,
                    "customer_id": customer_id,
                    "name": name,
                    "source_name": source_name,
                    "note": note,
                    "financial_status": financial_status
                })
        return pd.DataFrame(rows)
    else:
        st.error(f"Erreur lors de la récupération des commandes : {response.status_code}")
        return pd.DataFrame()

# === Fonction pour charger les données clients depuis fichiers CSV ===
def get_client_details_df(customer_ids, folder_path="onedrive_data"):
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
                            "created_at": fields[1],
                            "updated_at": fields[2],
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

# === Traitement et affichage final ===
st.subheader("📦 Chargement des données")
orders_df = get_shopify_orders_dataframe()

if not orders_df.empty:
    st.success(f"{len(orders_df)} lignes de commandes chargées.")

    # Lecture des fichiers clients
    unique_ids = orders_df["customer_id"].dropna().unique()
    clients_df = get_client_details_df(unique_ids, folder_path="C:\\Users\\MGE\\OneDrive\\Documents\\Qlik Clef")

    # Fusion des données
    full_df = orders_df.merge(clients_df, on="customer_id", how="left")

    # Affichage
    st.subheader("🧾 Commandes enrichies avec infos clients")
    st.dataframe(full_df, use_container_width=True)

    # Option d’export CSV
    csv = full_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📁 Télécharger au format CSV",
        data=csv,
        file_name="commandes_shopify_enrichies.csv",
        mime="text/csv"
    )
else:
    st.warning("Aucune commande récupérée.")
