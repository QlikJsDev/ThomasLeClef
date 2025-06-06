# Streamlit multi-page app for Shopify enriched orders
import streamlit as st
import pandas as pd
import requests
import os
import re
from datetime import datetime, timedelta

st.set_page_config(page_title="Commandes Shopify enrichies", layout="wide")
st.title("🍭️ Gestion des commandes Shopify")

# === Paramètres ===
params = {}
with open("param.txt", "r") as f:
    exec(f.read(), params)

SHOPIFY_DOMAIN = params["SHOPIFY_DOMAIN"]
ACCESS_TOKEN = params["ACCESS_TOKEN"]
CUSTOMER_PATH = params["CUSTOMER_PATH"]
API_VERSION = "2025-01"

# === Précharger noms clients et valeurs dropdowns ===
clients_info = pd.read_csv("Clients.csv") if os.path.exists("Clients.csv") else pd.DataFrame()
noms_clients = sorted(clients_info["Nom"].dropna().unique()) if "Nom" in clients_info.columns else []
sources = ["web", "non web"]

# === Récupération des commandes Shopify ===
@st.cache_data(show_spinner="Chargement des commandes depuis Shopify...")

def load_all_clients(path):
    clients = []
    for file in os.listdir(path):
        if file.endswith(".csv"):
            try:
                with open(os.path.join(path, file), "r", encoding="utf-8") as f:
                    fields = f.readline().strip().split(";")
                    if len(fields) >= 8:
                        clients.append({
                            "Nom": f"{fields[3]} {fields[4]}",
                            "email": fields[0],
                            "telephone": fields[5],
                            "adresse": fields[6],
                            "ville": fields[7],
                            "Itinéraire": ""
                        })
            except Exception as e:
                st.warning(f"Erreur lecture {file} : {e}")
    return pd.DataFrame(clients)



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
    match = re.search(r"(\d{2}/\d{2})", str(name))
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
    st.header("🔵 Commandes Shopify")
    orders_df = get_shopify_orders()
    if not orders_df.empty:
        orders_df["created_at"] = pd.to_datetime(orders_df["created_at"].str[:10], format="%Y-%m-%d")
        debut_annee = pd.to_datetime(f"{datetime.today().year}-01-01", format="%Y-%m-%d")
        orders_df = orders_df[orders_df["created_at"] >= debut_annee]
        orders_df["date_livraison"] = orders_df["name"].apply(extract_date_from_name)
        start_week = datetime.today() - timedelta(days=datetime.today().weekday())
        orders_df = orders_df[
            orders_df["date_livraison"].notnull() &
            (orders_df["date_livraison"] >= start_week)
        ]

        client_df = get_client_details(orders_df["customer_id"].dropna().unique())
        full_df = orders_df.merge(client_df, on="customer_id", how="left")
        full_df.rename(columns={"name": "Plat"}, inplace=True)

        plats_disponibles = sorted(full_df["Plat"].dropna().unique())

        shopify_display = full_df[["order_number", "Plat", "Nom", "quantity", "source_name", "note"]]
        edited_shopify = st.data_editor(
            shopify_display,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Plat": st.column_config.SelectboxColumn("Plat", options=plats_disponibles, required=True),
                "Nom": st.column_config.SelectboxColumn("Nom", options=noms_clients, required=True),
                "source_name": st.column_config.SelectboxColumn("Source", options=sources)
            }
        )

        if st.button("📅 Sauvegarder commandes Shopify"):
            edited_shopify.to_csv("commandes.csv", index=False)
            st.success("Commandes Shopify sauvegardées.")

# === Ajouter des commandes manuellement ===
with tabs[1]:
    st.header("🔹 Ajouter des commandes manuellement")
    colonnes = ["order_number", "Plat", "Nom", "quantity", "source_name", "note"]
    if os.path.exists("commandes_additionnelles.csv"):
        initial_df = pd.read_csv("commandes_additionnelles.csv")
    else:
        initial_df = pd.DataFrame(columns=["Plat", "Nom", "quantity", "source_name", "note"])

    edited_new = st.data_editor(
        initial_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Plat": st.column_config.SelectboxColumn("Plat", options=plats_disponibles, required=True),
            "Nom": st.column_config.SelectboxColumn("Nom", options=noms_clients, required=True),
            "source_name": st.column_config.SelectboxColumn("Source", options=sources)
        }
    )


    if st.button("📅 Sauvegarder commandes additionnelles"):
        existing = pd.read_csv("commandes_additionnelles.csv") if os.path.exists("commandes_additionnelles.csv") else pd.DataFrame()

        # S'assurer que order_number est présent et int
        existing["order_number"] = pd.to_numeric(existing.get("order_number"), errors="coerce").fillna(0).astype(int)
        edited_new = edited_new.copy()
        edited_new["order_number"] = pd.to_numeric(edited_new.get("order_number"), errors="coerce")

        # Séparer nouvelles lignes (sans order_number) et existantes
        to_update = edited_new[edited_new["order_number"].notna()].astype({"order_number": int})
        to_add = edited_new[edited_new["order_number"].isna()]

        # Créer de nouveaux order_numbers pour les lignes à ajouter
        last_number = existing["order_number"].max() if not existing.empty else 1000
        to_add = to_add.copy()
        to_add["order_number"] = range(last_number + 1, last_number + 1 + len(to_add))

        # Mettre à jour les lignes existantes
        if not to_update.empty:
            existing.set_index("order_number", inplace=True)
            to_update.set_index("order_number", inplace=True)
            existing.update(to_update)
            existing.reset_index(inplace=True)

        # Ajouter les nouvelles lignes
        final_df = pd.concat([existing, to_add], ignore_index=True)

        # Sauvegarder
        final_df.to_csv("commandes_additionnelles.csv", index=False)
        st.success("Commandes additionnelles sauvegardées.")



# === Clients manquants ===
with tabs[2]:
    st.header("👥 Informations clients")
    colonnes_clients = ["Nom", "email", "telephone", "adresse", "ville"]

    from_path = load_all_clients(CUSTOMER_PATH)
    from_csv = pd.read_csv("Clients.csv") if os.path.exists("Clients.csv") else pd.DataFrame(columns=colonnes_clients)

    # Concat et dédupli
    initial_clients_df = pd.concat([from_path, from_csv], ignore_index=True)
    initial_clients_df = initial_clients_df.drop_duplicates(subset="Nom", keep="last")

    edited_clients = st.data_editor(
        initial_clients_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Nom": st.column_config.TextColumn("Nom", required=True),
            "Itinéraire": st.column_config.SelectboxColumn("Itinéraire", options=[str(i) for i in range(1, 6)])
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
    final_df = df_all.merge(clients_info, on="Nom", how="left")

    # Supprimer colonnes inutiles
    final_df.drop(columns=[col for col in final_df.columns if col.lower().startswith("unnamed") or col == "customer_id"], inplace=True, errors="ignore")

    # Fusion champs _x/_y
    for col in ["email", "telephone", "adresse", "ville", "Itinéraire"]:
        col_x, col_y = f"{col}_x", f"{col}_y"
        if col_x in final_df.columns and col_y in final_df.columns:
            final_df[col] = final_df[col_x].combine_first(final_df[col_y])
            final_df.drop(columns=[col_x, col_y], inplace=True)

    # Créer dictionnaire prix si besoin
    prix_map = {}
    if "Plat" in df1.columns and "price" in df1.columns:
        prix_map = df1.dropna(subset=["Plat", "price"]).drop_duplicates("Plat").set_index("Plat")["price"].to_dict()

    # Ajouter les prix manquants à partir du dictionnaire
    if "price" not in final_df.columns:
        final_df["price"] = final_df["Plat"].map(prix_map).fillna(0.0)
    else:
        final_df["price"] = final_df["price"].fillna(final_df["Plat"].map(prix_map))

    # Calcul du total
    final_df["total"] = final_df["price"] * final_df["quantity"].fillna(0)

    # Réorganiser les colonnes
    final_order = ["order_number", "Nom", "Plat", "quantity", "price", "total","source_name", "note", "Itinéraire", "email", "telephone", "adresse", "ville"]
    final_df = final_df[[col for col in final_order if col in final_df.columns]]

    st.dataframe(final_df, use_container_width=True)
    st.markdown(f"### 💰 Total global : **{final_df['total'].sum():.2f} €**")



# === Pivot des commandes par plat ===
with tabs[4]:
    st.header("📊 Tableau croisé des commandes par plat")

    df1 = pd.read_csv("commandes.csv") if os.path.exists("commandes.csv") else pd.DataFrame()
    df2 = pd.read_csv("commandes_additionnelles.csv") if os.path.exists("commandes_additionnelles.csv") else pd.DataFrame()
    df_all = pd.concat([df1, df2], ignore_index=True)

    clients_info = pd.read_csv("Clients.csv") if os.path.exists("Clients.csv") else pd.DataFrame()
    final_df = df_all.merge(clients_info, on="Nom", how="left")

    # Nettoyage colonnes inutiles
    final_df.drop(columns=[col for col in final_df.columns if col.lower().startswith("unnamed") or col == "customer_id"], inplace=True, errors="ignore")

    # Fusion des champs _x/_y
    for col in ["email", "telephone", "adresse", "ville"]:
        col_x, col_y = f"{col}_x", f"{col}_y"
        if col_x in final_df.columns and col_y in final_df.columns:
            final_df[col] = final_df[col_x].combine_first(final_df[col_y])
            final_df.drop(columns=[col_x, col_y], inplace=True)

    # Vérification minimale
    if "Plat" in final_df.columns and "quantity" in final_df.columns and not final_df.empty:
        # Réduire l’index aux colonnes non nulles et existantes
        index_cols = ["order_number", "Nom", "source_name", "note", "email", "telephone", "adresse", "ville"]
        index_cols = [col for col in index_cols if col in final_df.columns]

        pivot_df = final_df.pivot_table(
            index=index_cols,
            columns="Plat",
            values="quantity",
            aggfunc="sum",
            fill_value=0
        ).reset_index()

        # Ajouter Total
        plat_cols = pivot_df.columns.difference(index_cols)
        pivot_df["Total commandes"] = pivot_df[plat_cols].sum(axis=1)

        st.dataframe(pivot_df, use_container_width=True)
    else:
        st.warning("Aucune commande trouvée pour générer le tableau croisé.")
