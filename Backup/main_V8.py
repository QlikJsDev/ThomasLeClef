# Streamlit multi-page app for Shopify enriched orders
import streamlit as st
import pandas as pd
import requests
import os
import re
from datetime import datetime, timedelta

st.set_page_config(page_title="Commandes Shopify enrichies", layout="wide")
st.title("🛍️ Gestion des commandes Shopify")

# === Paramètres ===
params = {}
with open("param.txt", "r") as f:
    exec(f.read(), params)

SHOPIFY_DOMAIN = params["SHOPIFY_DOMAIN"]
ACCESS_TOKEN = params["ACCESS_TOKEN"]
CUSTOMER_PATH = params["CUSTOMER_PATH"]
API_VERSION = "2025-01"

# === Récupération des commandes Shopify ===
@st.cache_data(show_spinner="Chargement des commandes depuis Shopify...")
def get_shopify_orders():
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
                    "source_name": source_name,
                    "note": note,
                    "financial_status": financial_status
                })
        return pd.DataFrame(rows)
    else:
        st.error(f"Erreur Shopify : {response.status_code}")
        return pd.DataFrame()

# === Extraction infos clients depuis fichiers CSV ou Shopify ===
def get_client_details(customer_ids, path=CUSTOMER_PATH):
    client_data = []
    for cid in customer_ids:
        file_path = os.path.join(path, f"{cid}.csv")
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    fields = f.readline().strip().split(";")
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

# === Extraction date DD/MM depuis le champ name ===
def extract_date_from_name(name):
    match = re.search(r"(\d{2}/\d{2})", str(name))  # 🔁 enlevé les \b
    if match:
        try:
            return datetime.strptime(match.group(1) + f"/{datetime.today().year}", "%d/%m/%Y")
        except:
            return None
    return None




# === Pages / Onglets ===
tabs = st.tabs(["Commandes Shopify", "Ajouter des commandes", "Clients", "Synthèse", "pivot"])

# === Commandes Shopify ===
with tabs[0]:
    st.header("🟦 Commandes Shopify")
    orders_df = get_shopify_orders()
    if not orders_df.empty:
        print(orders_df)
        orders_df["created_at"] = pd.to_datetime(orders_df["created_at"].str[:10], format="%Y-%m-%d")
        debut_annee = pd.to_datetime(f"{datetime.today().year}-01-01"[:10], format="%Y-%m-%d") 
        print(orders_df["created_at"])
        print(debut_annee)
        orders_df = orders_df[orders_df["created_at"] >= debut_annee]
        print(orders_df)
        orders_df["date_livraison"] = orders_df["name"].apply(extract_date_from_name)
        start_week = datetime.today() - timedelta(days=datetime.today().weekday())
        orders_df = orders_df[
            orders_df["date_livraison"].notnull() &
            (orders_df["date_livraison"] >= start_week)
        ]

        # Récupération infos client
        client_df = get_client_details(orders_df["customer_id"].dropna().unique())
        full_df = orders_df.merge(client_df, on="customer_id", how="left")
        full_df.rename(columns={"name": "Plat"}, inplace=True)
        if "Itinéraire" not in full_df.columns:
            full_df["Itinéraire"] = ""

        plats_disponibles = sorted(full_df["Plat"].dropna().unique())
        noms_clients = sorted(full_df["Nom"].dropna().unique())
        sources = ["web", "non web"]
        itineraire_options = [str(i) for i in range(1, 6)]

        shopify_display = full_df[["order_number", "Plat", "Nom", "quantity", "source_name", "Itinéraire", "note"]]
        edited_shopify = st.data_editor(
            shopify_display,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Plat": st.column_config.SelectboxColumn("Plat", options=plats_disponibles, required=True),
                "Nom": st.column_config.SelectboxColumn("Nom", options=noms_clients, required=True),
                "source_name": st.column_config.SelectboxColumn("Source", options=sources),
                "Itinéraire": st.column_config.SelectboxColumn("Itinéraire", options=itineraire_options)
            }
        )

        if st.button("💾 Sauvegarder commandes Shopify"):
            edited_shopify.to_csv("commandes.csv", index=False)
            st.success("Commandes Shopify sauvegardées.")

# === Ajouter des commandes manuellement ===
with tabs[1]:
    st.header("🟨 Ajouter des commandes manuellement")
    colonnes = ["order_number", "Plat", "Nom", "quantity", "source_name", "Itinéraire", "note"]

    if os.path.exists("commandes_additionnelles.csv"):
        initial_df = pd.read_csv("commandes_additionnelles.csv")
    else:
        initial_df = pd.DataFrame(columns=colonnes)

    edited_new = st.data_editor(
        initial_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Plat": st.column_config.SelectboxColumn("Plat", options=plats_disponibles, required=True),
            "Nom": st.column_config.SelectboxColumn("Nom", options=noms_clients, required=True),
            "source_name": st.column_config.SelectboxColumn("Source", options=sources),
            "Itinéraire": st.column_config.SelectboxColumn("Itinéraire", options=itineraire_options)
        }
    )

    if st.button("💾 Sauvegarder commandes additionnelles"):
        edited_new.to_csv("commandes_additionnelles.csv", index=False)
        st.success("Commandes additionnelles sauvegardées.")


# === Clients manquants ===
with tabs[2]:
    st.header("👥 Informations clients")

    colonnes_clients = ["Nom", "email", "telephone", "adresse", "ville"]

    if os.path.exists("Clients.csv"):
        initial_clients_df = pd.read_csv("Clients.csv")
    else:
        initial_clients_df = pd.DataFrame(columns=colonnes_clients)

    edited_clients = st.data_editor(
        initial_clients_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Nom": st.column_config.TextColumn("Nom", required=True)
        }
    )

    if st.button("💾 Sauvegarder clients"):
        edited_clients.to_csv("Clients.csv", index=False)
        st.success("Clients sauvegardés dans Clients.csv")



# === Synthèse des commandes ===
with tabs[3]:
    st.header("🧾 Synthèse consolidée des commandes")
    df1 = pd.read_csv("commandes.csv") if os.path.exists("commandes.csv") else pd.DataFrame()
    df2 = pd.read_csv("commandes_additionnelles.csv") if os.path.exists("commandes_additionnelles.csv") else pd.DataFrame()
    df_all = pd.concat([df1, df2], ignore_index=True)
    clients_info = pd.read_csv("Clients.csv") if os.path.exists("Clients.csv") else pd.DataFrame()
    noms_clients = sorted(clients_info["Nom"].dropna().unique()) if "Nom" in clients_info.columns else []
    final_df = df_all.merge(clients_info, on="Nom", how="left")

    # Ajout automatique des prix et totaux si manquants
    if "price" not in final_df.columns:
        prix_map = prix_par_plat if 'prix_par_plat' in globals() else {}
        final_df["price"] = final_df["Plat"].map(prix_map).fillna(0.0)
    final_df["total"] = final_df["price"] * final_df["quantity"].fillna(0)

    st.dataframe(final_df, use_container_width=True)
    st.markdown(f"### 💰 Total global : **{final_df['total'].sum():.2f} €**")

# === Pivot des commandes par plat ===
with tabs[4]:
    st.header("📊 Tableau croisé des commandes par plat")
    df1 = pd.read_csv("commandes.csv") if os.path.exists("commandes.csv") else pd.DataFrame()
    df2 = pd.read_csv("commandes_additionnelles.csv") if os.path.exists("commandes_additionnelles.csv") else pd.DataFrame()
    df_all = pd.concat([df1, df2], ignore_index=True)
    if not df_all.empty:
        all_except_plat = [col for col in df_all.columns if col != "Plat"]
        pivot_df = df_all.pivot_table(index=all_except_plat, columns="Plat", values="quantity", aggfunc="sum", fill_value=0).reset_index()
        st.dataframe(pivot_df, use_container_width=True)
    else:
        st.warning("Aucune commande trouvée pour générer le tableau croisé.")
