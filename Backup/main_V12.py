# Streamlit multi-page app for Shopify enriched orders
import streamlit as st
import pandas as pd
import requests
import os
import re
from datetime import datetime, timedelta
import csv

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

# === Précharger données globales ===
clients_info = pd.read_csv("Clients.csv") if os.path.exists("Clients.csv") else pd.DataFrame()
noms_clients = sorted(clients_info["Nom"].dropna().unique()) if "Nom" in clients_info.columns else []
sources = ["web", "non web"]

plats_disponibles = []
if os.path.exists("commandes.csv"):
    plats_disponibles = sorted(pd.read_csv("commandes.csv")["Plat"].dropna().unique())

# === Fonctions ===
def get_products_and_prices():
    # Paramètres Shopify
    url_collects = f"https://{SHOPIFY_DOMAIN}/admin/api/{API_VERSION}/collects.json?limit=250"
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": ACCESS_TOKEN
    }

    # 1. Récupérer les collects (collection_id, product_id)
    response = requests.get(url_collects, headers=headers)
    if response.status_code != 200:
        st.error(f"Erreur récupération collects: {response.status_code}")
        return

    collects = response.json().get("collects", [])
    product_ids = list({str(collect["product_id"]) for collect in collects})  # unique ids

    # 2. Pour tous les products ids, récupérer les produits
    products_info = []

    # Shopify limite souvent à 50-100 ids par requête, mais ici on suppose <250
    ids_param = ",".join(product_ids)
    url_products = f"https://{SHOPIFY_DOMAIN}/admin/api/{API_VERSION}/products.json?ids={ids_param}"

    response = requests.get(url_products, headers=headers)
    if response.status_code != 200:
        st.error(f"Erreur récupération produits: {response.status_code}")
        return

    products = response.json().get("products", [])

    # 3. Extraire titre principal et prix du premier variant
    for product in products:
        product_id = product.get("id")
        title = product.get("title")
        variants = product.get("variants", [])
        if variants:
            price = variants[0].get("price", None)
        else:
            price = None

        products_info.append({
            "id": product_id,
            "title": title,
            "price": price
        })

    # 4. Sauvegarder dans produits_prices.csv (en écrasant)
    products_df = pd.DataFrame(products_info)
    products_df.to_csv("produits_prices.csv", index=False, quoting=csv.QUOTE_NONNUMERIC)



def load_all_clients(path):
    today = datetime.today().date()
    clients = []
    for file in os.listdir(path):
        full_path = os.path.join(path, file)
        if file.endswith(".csv") and datetime.fromtimestamp(os.path.getmtime(full_path)).date() == today:
            try:
                with open(full_path, "r", encoding="utf-8") as f:
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


@st.cache_data(show_spinner="Chargement des commandes depuis Shopify...")
def get_shopify_orders():
    url = f"https://{SHOPIFY_DOMAIN}/admin/api/{API_VERSION}/orders.json?status=any&limit=250"
    headers = {"Content-Type": "application/json", "X-Shopify-Access-Token": ACCESS_TOKEN}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        orders = response.json().get("orders", [])
        rows = []
        for order in orders:
            created_at = order.get("created_at")
            order_number = order.get("order_number")
            source_name = order.get("source_name", "non web")
            note = order.get("note")
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
                    "note": note
                })
        return pd.DataFrame(rows)
    else:
        st.error(f"Erreur Shopify : {response.status_code}")
        return pd.DataFrame()

def extract_date_from_name(name):
    match = re.search(r"(\d{2}/\d{2})", str(name))
    if match:
        try:
            return datetime.strptime(match.group(1) + f"/{datetime.today().year}", "%d/%m/%Y")
        except:
            return None
    return None

# === Interface principale ===
if not os.path.exists("produits_prices.csv"):
    get_products_and_prices()

if st.button("🔄 Refresh Produits/Prix depuis Shopify"):
    with st.spinner("🔄 Rafraîchissement des produits et prix en cours..."):
        get_products_and_prices()
    st.success("Mise à jour terminée ✅")


tabs = st.tabs(["Commandes Shopify", "Ajouter des commandes", "Clients", "Synthèse", "Pivot", "Pivot éditable"])

# === Onglet Commandes Shopify ===
with tabs[0]:
    st.header("🔵 Commandes Shopify")
    
    if "reload_shopify" not in st.session_state:
        st.session_state["reload_shopify"] = True

    if st.button("🔄 Rafraîchir commandes Shopify"):
        st.session_state["reload_shopify"] = True

    if st.session_state["reload_shopify"]:
        orders_df = get_shopify_orders()
        st.session_state["orders_df"] = orders_df.copy()
        st.session_state["reload_shopify"] = False
    else:
        orders_df = st.session_state.get("orders_df", pd.DataFrame())

    if not orders_df.empty:
        orders_df["created_at"] = pd.to_datetime(orders_df["created_at"].astype(str).str[:10], format="%Y-%m-%d")
        debut_annee = pd.to_datetime(f"{datetime.today().year}-01-01", format="%Y-%m-%d")
        start_week = datetime.today() - timedelta(days=datetime.today().weekday())
        orders_df = orders_df[
            (orders_df["created_at"] >= debut_annee) &
            (orders_df["name"].apply(extract_date_from_name).notnull()) &
            (orders_df["name"].apply(extract_date_from_name) >= start_week)
        ]

        client_df = pd.DataFrame()
        if not orders_df["customer_id"].dropna().empty:
            client_df = get_client_details(orders_df["customer_id"].dropna().unique())
        full_df = orders_df.merge(client_df, on="customer_id", how="left")
        full_df.rename(columns={"name": "Plat"}, inplace=True)

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
            edited_shopify.to_csv("commandes.csv", index=False, quoting=csv.QUOTE_NONNUMERIC)
            st.success("Commandes Shopify sauvegardées.")

# === Ajouter des commandes manuellement ===
with tabs[1]:
    st.header("🔹 Ajouter des commandes manuellement")
    colonnes = ["order_number", "Plat", "Nom", "quantity", "source_name", "note"]
    if os.path.exists("commandes_additionnelles.csv"):
        initial_df = pd.read_csv("commandes_additionnelles.csv")
    else:
        initial_df = pd.DataFrame(columns=["Plat", "Nom", "quantity", "source_name", "note"])
    # st.success("Initial DF")
    # st.success(initial_df)
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





with tabs[2]:
    st.header("👥 Informations clients")
    colonnes_clients = ["Nom", "email", "telephone", "adresse", "ville", "Itinéraire"]

    # 🔥 Initialisation : charger dans st.session_state
    if "clients_df" not in st.session_state:
        from_path = load_all_clients(CUSTOMER_PATH)
        from_csv = pd.read_csv("Clients.csv") if os.path.exists("Clients.csv") else pd.DataFrame(columns=colonnes_clients)
        initial_clients_df = pd.concat([from_csv, from_path], ignore_index=True)
        initial_clients_df = initial_clients_df.drop_duplicates(subset="Nom", keep="last")
        st.session_state["clients_df"] = initial_clients_df

    # 🔥 Edition en live
    edited_clients = st.data_editor(
        st.session_state["clients_df"],
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Nom": st.column_config.TextColumn("Nom", required=True),
            "Itinéraire": st.column_config.SelectboxColumn("Itinéraire", options=[str(i) for i in range(1, 6)])
        }
    )

    # 🔥 Stockage de l'édition en session_state pour garder en mémoire
    st.session_state["clients_df"] = edited_clients

    if st.button("💾 Sauvegarder clients"):
        st.session_state["clients_df"].to_csv("Clients.csv", index=False, quoting=csv.QUOTE_NONNUMERIC)
        st.success("✅ Clients sauvegardés dans Clients.csv")





# === Synthèse des commandes ===
with tabs[3]:
    st.header("🧾 Synthèse consolidée des commandes")
    df1 = pd.read_csv("commandes.csv") if os.path.exists("commandes.csv") else pd.DataFrame()
    df2 = pd.read_csv("commandes_additionnelles.csv", sep=",", quotechar='"') if os.path.exists("commandes_additionnelles.csv") else pd.DataFrame()
    df_all = pd.concat([df1, df2], ignore_index=True)

    clients_info = pd.read_csv("Clients.csv") if os.path.exists("Clients.csv") else pd.DataFrame()
    produits_prices = pd.read_csv("produits_prices.csv") if os.path.exists("produits_prices.csv") else pd.DataFrame()

    final_df = df_all.merge(clients_info, on="Nom", how="left")

    # Supprimer colonnes inutiles
    final_df.drop(columns=[col for col in final_df.columns if col.lower().startswith("unnamed") or col == "customer_id"], inplace=True, errors="ignore")

    # Fusion champs _x/_y
    for col in ["email", "telephone", "adresse", "ville", "Itinéraire"]:
        col_x, col_y = f"{col}_x", f"{col}_y"
        if col_x in final_df.columns and col_y in final_df.columns:
            final_df[col] = final_df[col_x].combine_first(final_df[col_y])
            final_df.drop(columns=[col_x, col_y], inplace=True)

    # ========== 🆕 ICI : Ajout du prix manquant depuis produits_prices.csv ==========
    if not produits_prices.empty:
        # Créer un dictionnaire rapide {title: price}
        prix_map = produits_prices.set_index("title")["price"].to_dict()
        
        # Ajouter colonne price si elle n'existe pas
        if "price" not in final_df.columns:
            final_df["price"] = final_df["Plat"].map(prix_map).astype(float)
        else:
            # Compléter uniquement les prix manquants
            final_df["price"] = final_df["price"].fillna(final_df["Plat"].map(prix_map).astype(float))
    else:
        st.warning("⚠️ Fichier produits_prices.csv non trouvé ou vide. Pas de correspondance des prix possible.")

    # Calcul du total
    final_df["total"] = final_df["price"] * final_df["quantity"].fillna(0)

    # Réorganiser les colonnes
    final_order = ["order_number", "Nom", "Plat", "quantity", "price", "total", "source_name", "note", "Itinéraire", "email", "telephone", "adresse", "ville"]
    final_df = final_df[[col for col in final_order if col in final_df.columns]]

    st.dataframe(final_df, use_container_width=True)
    st.markdown(f"### 💰 Total global : **{final_df['total'].sum():.2f} €**")


# === Pivot
with tabs[4]:
    st.header("📊 Tableau croisé des commandes par plat")
    
    df1 = pd.read_csv("commandes.csv") if os.path.exists("commandes.csv") else pd.DataFrame()
    if "note" in df1.columns:
        df1["note"] = df1["note"].fillna("")
    if "source_name" in df1.columns:
        df1["source_name"] = df1["source_name"].fillna("")

    df2 = pd.read_csv("commandes_additionnelles.csv", sep=",", quotechar='"') if os.path.exists("commandes_additionnelles.csv") else pd.DataFrame()
    df_all = pd.concat([df1, df2], ignore_index=True)


    df_all["Plat"] = df_all["Plat"].astype(str)
    df_all["quantity"] = pd.to_numeric(df_all["quantity"], errors="coerce").fillna(0)

    pivot_df = df_all.pivot_table(
        index=["order_number", "Nom", "source_name", "note"],
        columns="Plat",
        values="quantity",
        aggfunc="sum",
        fill_value=0
    ).reset_index()

    pivot_df["Total commandes"] = pivot_df.drop(columns=["order_number", "Nom", "source_name", "note"]).sum(axis=1)

    st.dataframe(pivot_df, use_container_width=True)


# === Pivot éditable
with tabs[5]:
    st.header("✏️ Pivot éditable")

    # Recharger df1 et df2
    df1 = pd.read_csv("commandes.csv") if os.path.exists("commandes.csv") else pd.DataFrame()
    if "note" in df1.columns:
        df1["note"] = df1["note"].fillna("")
    if "source_name" in df1.columns:
        df1["source_name"] = df1["source_name"].fillna("")

    df2 = pd.read_csv("commandes_additionnelles.csv") if os.path.exists("commandes_additionnelles.csv") else pd.DataFrame()

    df_all = pd.concat([df1, df2], ignore_index=True)

    if not df_all.empty and "Plat" in df_all.columns:
        df_all["Plat"] = df_all["Plat"].astype(str)
        df_all["quantity"] = pd.to_numeric(df_all["quantity"], errors="coerce").fillna(0)

        pivot_df = df_all.pivot_table(
            index=["order_number", "Nom", "source_name", "note"],
            columns="Plat",
            values="quantity",
            aggfunc="sum",
            fill_value=0
        ).reset_index()

        pivot_columns_editable = pivot_df.columns[4:]  # seulement les colonnes de plats

        edited_pivot = st.data_editor(
            pivot_df,
            use_container_width=True,
            num_rows="dynamic",
            column_config={col: st.column_config.NumberColumn(col, step=1) for col in pivot_columns_editable},
            disabled=["order_number", "Nom", "source_name", "note"]
        )

        if st.button("💾 Sauvegarder modifications Pivot"):
            # Convertir edited_pivot en format long
            updated = edited_pivot.melt(
                id_vars=["order_number", "Nom", "source_name", "note"],
                var_name="Plat",
                value_name="quantity"
            )

            updated = updated[updated["quantity"] > 0]  # Ne garder que les quantités > 0

            # Recharger anciennes commandes
            commandes_all = pd.concat([
                pd.read_csv("commandes.csv") if os.path.exists("commandes.csv") else pd.DataFrame(),
                pd.read_csv("commandes_additionnelles.csv") if os.path.exists("commandes_additionnelles.csv") else pd.DataFrame()
            ])

            commandes_all["order_number"] = pd.to_numeric(commandes_all.get("order_number"), errors="coerce").astype(int)
            updated["order_number"] = pd.to_numeric(updated["order_number"], errors="coerce").astype(int)

            # Supprimer toutes les anciennes lignes des orders modifiés
            commandes_all = commandes_all[~commandes_all["order_number"].isin(updated["order_number"])]

            # Ajouter les nouvelles lignes
            commandes_final = pd.concat([
                commandes_all,
                updated
            ], ignore_index=True)

            # Séparer de nouveau Shopify vs Manuelles
            commandes_final_shopify = commandes_final[commandes_final["order_number"] < 2000]
            commandes_final_additionnelles = commandes_final[commandes_final["order_number"] >= 2000]

            commandes_final_shopify.to_csv("commandes.csv", index=False, quoting=csv.QUOTE_NONNUMERIC)
            commandes_final_additionnelles.to_csv("commandes_additionnelles.csv", index=False, quoting=csv.QUOTE_NONNUMERIC)

            st.success("✅ Modifications enregistrées dans commandes.csv et commandes_additionnelles.csv")

            # 🔥 Forcer rechargement dans les autres tabs
            st.session_state["reload_shopify"] = True
            if "clients_df" in st.session_state:
                del st.session_state["clients_df"]

