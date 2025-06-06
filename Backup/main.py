import streamlit as st
import pandas as pd
import requests
import re
from datetime import date, datetime

st.set_page_config(page_title="Tableau de commandes Shopify", layout="wide")
st.title("🛍️ Tableau de Commandes - Données Shopify Dynamiques")

# === Lecture des paramètres depuis param.txt ===
params = {}
with open("param.txt", "r") as f:
    exec(f.read(), params)

SHOPIFY_DOMAIN = params["SHOPIFY_DOMAIN"]
ACCESS_TOKEN = params["ACCESS_TOKEN"]
API_VERSION = "2025-01"


# === FONCTION POUR RÉCUPÉRER LES TITRES DES PRODUITS TRIÉS PAR DATE ===
@st.cache_data(show_spinner="Chargement des produits Shopify triés par date...")
def get_shopify_product_titles():
    url = f"https://{SHOPIFY_DOMAIN}/admin/api/{API_VERSION}/orders.json"
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": ACCESS_TOKEN
    }
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        orders = response.json().get("orders", [])
        all_line_items = []
        for order in orders:
            for item in order.get("line_items", []):
                title = item.get("title", "")
                all_line_items.append(title)

        unique_titles = list(set(all_line_items))

        # Fonction pour extraire la date du titre (format DD/MM)
        def extract_date(title):
            match = re.search(r"\b(\d{2}/\d{2})\b", title)
            if match:
                try:
                    return datetime.strptime(match.group(1) + "/2025", "%d/%m/%Y")
                except ValueError:
                    return None
            return None

        # Associer chaque titre à sa date
        title_with_dates = [
            (title, extract_date(title)) for title in unique_titles
        ]

        # Garder uniquement les titres avec date valide
        title_with_dates = [t for t in title_with_dates if t[1] is not None]

        # Trier par date
        title_with_dates.sort(key=lambda x: x[1])

        # Retourner la liste triée des titres
        sorted_titles = [t[0] for t in title_with_dates]
        return sorted_titles

    else:
        st.error(f"Erreur Shopify {response.status_code}: {response.text}")
        return []


# === RÉCUPÉRATION DES TITRES PRODUITS POUR DROPDOWN ===
liste_plats = get_shopify_product_titles()
if not liste_plats:
    liste_plats = ["Pizza", "Sushi", "Burger", "Fallback"]  # fallback si Shopify vide ou erreur

# === DONNÉES INITIALES ===
data = {
    "Ville": ["Paris", "Lyon", "Marseille"],
    "Date": [date(2025, 4, 10), date(2025, 4, 11), date(2025, 4, 12)],
    "Client": ["Alice", "Bob", "Charlie"],
    "Plat": [liste_plats[0], liste_plats[1], liste_plats[2] if len(liste_plats) > 2 else liste_plats[0]],
    "Type de plat": ["Italien", "Japonais", "Américain"],
    "Sous-type de plat": ["Margherita", "Saumon", "Cheese"],
    "Prix": [12.5, 15.0, 10.0],
    "Quantité": [2, 1, 3]
}

df = pd.DataFrame(data)

# === TABLEAU ÉDITABLE AVEC DROPDOWN SUR "Plat" ===
st.subheader("Modifier les commandes")
edited_df = st.data_editor(
    df,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Plat": st.column_config.SelectboxColumn(
            label="Plat",
            options=liste_plats,
            required=True
        )
    }
)

# === CALCUL DU TOTAL ===
if "Prix" in edited_df.columns and "Quantité" in edited_df.columns:
    edited_df["Total"] = edited_df["Prix"] * edited_df["Quantité"]
    total_ventes = edited_df["Total"].sum()
    st.markdown(f"### 💰 Total des ventes : **{total_ventes:.2f} €**")

# === APERÇU FINAL ===
st.subheader("Aperçu des données enregistrées")
st.dataframe(edited_df, use_container_width=True)
