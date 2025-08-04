# Streamlit multi-page app for Shopify enriched orders
import streamlit as st
import pandas as pd
import requests
import os
import re
from datetime import datetime, timedelta
import csv
from google.oauth2 import service_account
from googleapiclient.discovery import build

st.set_page_config(page_title="Commandes Shopify enrichies", layout="wide")
# st.title("🍭️ Gestion des commandes Shopify")



mode = "Prod"  # Remplacez cela par 'Prod' pour le mode production

if mode == "Prod":
    params = {}
    with open("param.txt", "r") as f:
        exec(f.read(), params)
    ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
    CUSTOMER_PATH = params["CUSTOMER_PATH"]
    API_VERSION = "2025-01"
    SHOPIFY_DOMAIN = params["SHOPIFY_DOMAIN"]
else:
    params = {}
    # Chemin vers le fichier param.txt un niveau au-dessus du répertoire actuel
    file_path = os.path.join(os.path.dirname(__file__), '..', 'param.txt')

    with open(file_path, "r") as f:
        exec(f.read(), params)
    ACCESS_TOKEN = params["ACCESS_TOKEN"]
    CUSTOMER_PATH = params["CUSTOMER_PATH"]
    API_VERSION = "2025-01"
    SHOPIFY_DOMAIN = params["SHOPIFY_DOMAIN"]



# === Précharger données globales ===
clients_info = pd.read_csv("Clients.csv") if os.path.exists("Clients.csv") else pd.DataFrame()
Noms_clients = sorted(clients_info["Nom"].dropna().unique()) if "Nom" in clients_info.columns else []
sources = ["web", "non web"]

# print(ACCESS_TOKEN)

plats_disponibles = []
if os.path.exists("commandes.csv"):
    plats_disponibles = sorted(pd.read_csv("commandes.csv")["Plat"].dropna().unique())

# === Fonctions ===
def read_csv_flexible_encoding(file_path):
    encodings = ["utf-8", "utf-8-sig", "latin1"]
    for enc in encodings:
        try:
            with open(file_path, "r", encoding=enc) as f:
                return f.readline().strip().split(";")
        except Exception:
            continue
    return None


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
            volume = variants[0].get("title", None)
        else:
            price = None
            volume = None

        if volume!='Default Title':
            title=title+' - '+volume

        products_info.append({
            "id": product_id,
            "title": title,
            "price": price
        })

    # 4. Sauvegarder dans produits_prices.csv (en écrasant)
    products_df = pd.DataFrame(products_info)
    products_df.to_csv("produits_prices.csv", index=False, quoting=csv.QUOTE_NONNUMERIC)

def load_all_clients(sheet_url, csv_path="Clients.csv"):
    # Configurer l'API Google Sheets
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    # Récupérer le bloc
    sa_info = st.secrets["google_service_account"]
    # Charger les credentials directement à partir du dictionnaire
    creds = service_account.Credentials.from_service_account_info(sa_info, scopes=scopes)
    # creds = service_account.Credentials.from_service_account_file("file", scopes=scopes)
    service = build('sheets', 'v4', credentials=creds)

    

    # Extraire l'ID de la feuille
    sheet_id = sheet_url.split("/d/")[1].split("/")[0]

    # Appeler l'API Google Sheets
    sheet = service.spreadsheets().values().get(spreadsheetId=sheet_id, range="Clients").execute()
    data = sheet.get("values", [])

    # Convertir en DataFrame
    column_names = data[0]
    rows = data[1:]
    clients_df = pd.DataFrame(rows, columns=column_names)

    # Fusionner les colonnes Prenom et Nom et stocker dans colonne "Nom" (= "Prenom Nom")
    clients_df["Nom"] = clients_df["Prenom"].str.strip() + " " + clients_df["Nom"].str.strip()
    clients_df = clients_df.drop(columns=["Prenom"])

    clients_df["customer_id"] = clients_df["customer_id"].apply(lambda x: str(x).split(".")[0] if str(x).endswith(".0") else str(x))
    

    # Colonnes à vérifier
    columns_to_check = ["Nom", "Email", "Telephone", "Adresse", "Ville", "customer_id"]

    # Charger le CSV existant
    if os.path.exists(csv_path):
        csv_df = pd.read_csv(csv_path)
    else:
        csv_df = pd.DataFrame(columns=columns_to_check + ["Itineraire"])

    csv_df["customer_id"] = csv_df["customer_id"].apply(lambda x: str(x).split(".")[0] if str(x).endswith(".0") else str(x))
    
    # Gérer la colonne Itineraire absente dans la Google Sheet
    if "Itineraire" not in clients_df.columns:
        clients_df["Itineraire"] = ""

    # S'assurer du bon ordre des colonnes pour concaténation/comparaison
    clients_df = clients_df[columns_to_check + ["Itineraire"]]

    columns_to_check = ["Nom", "Email", "Telephone", "Adresse", "Ville", "customer_id"]


    # Forcer tous les columns_to_check (dans les deux DataFrames) au type string (object)
    for col in columns_to_check:
        clients_df[col] = clients_df[col].astype(str)
        csv_df[col] = csv_df[col].astype(str)


    # Trouver les nouvelles lignes (hors Itineraire)
    merged = clients_df.merge(csv_df, on=columns_to_check, how='left', indicator=True)

    # Trouver les index des nouvelles lignes
    new_rows_idx = merged[merged['_merge'] == 'left_only'].index

    # Extraire les vraies nouvelles lignes avec Itineraire propre
    new_rows = clients_df.loc[new_rows_idx, columns_to_check + ["Itineraire"]]

    if not new_rows.empty:
        result = pd.concat([csv_df, new_rows], ignore_index=True)
        result.to_csv(csv_path, index=False)
        print(f"{len(new_rows)} nouvelles lignes ajoutées.")
    else:
        print("Aucune nouvelle ligne à ajouter.")

    return clients_df



sheet_url = "https://docs.google.com/spreadsheets/d/1YLWvm-ay-vgPP2rIDQNplrRKUciyGzudWPgO2fVAC_I/edit?usp=sharing"
clients_df = load_all_clients(sheet_url)

colonnes_clients = ["Nom", "Email", "Telephone", "Adresse", "Ville", "Itineraire", "customer_id"]
clients_df = pd.read_csv("Clients.csv") if os.path.exists("Clients.csv") else pd.DataFrame(columns=colonnes_clients)




def clean_telephone(tel):
    # Remplace la virgule par un point (pour cast float)
    if isinstance(tel, str):
        tel = tel.replace(',', '.')
    try:
        # Si c'est un float ou une string représentant un float
        tel_str = '{0:.0f}'.format(float(tel))
    except Exception:
        tel_str = str(tel)
    # Retire tout sauf les chiffres
    tel_str = ''.join(filter(str.isdigit, tel_str))
    # Supprime les numéros inappropriés comme 32510 (qui ne fait pas sens)
    if len(tel_str) < 8:
        tel_str = ''
    return tel_str

# Exemple sur la colonne du DataFrame :
clients_df["Telephone"] = clients_df["Telephone"].apply(clean_telephone)



# for i in clients_df:
#     st.write(i)

# # D'abord, normalise les colonnes
# clients_df.columns = (
#     clients_df.columns
#     .str.strip()
#     .str.lower()
#     .str.normalize('NFKD')
#     .str.encode('ascii', errors='ignore')
#     .str.decode('utf-8')
# )

# # Ensuite tu peux manipuler "Prenom" et "Nom" sans risque
# clients_df["Nom complet"] = (clients_df["Prenom"].fillna("") + " " + clients_df["Nom"].fillna("")).str.strip()

# # Facultatif : Si tu veux une colonne "Nom" déjà concaténée
# clients_df["Nom_concatene"] = clients_df["Nom complet"]


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
        orders_df.rename(columns={"name": "Plat"}, inplace=True)
        orders_df["created_at"] = pd.to_datetime(orders_df["created_at"].astype(str).str[:10], format="%Y-%m-%d")
        debut_annee = pd.to_datetime(f"{datetime.today().year}-01-01", format="%Y-%m-%d")
        start_week = datetime.today() - timedelta(days=datetime.today().weekday())
        orders_df["date_livraison"] = orders_df["Plat"].apply(extract_date_from_name)

        orders_df = orders_df[
            (orders_df["created_at"] >= debut_annee) &
            (orders_df["date_livraison"].notnull()) &
            (orders_df["date_livraison"] >= start_week)
        ]

        # ✅ Sauvegarder toutes les commandes récupérées dans commandes.csv
        save_df = orders_df[["order_number", "Plat", "customer_id", "quantity", "source_name", "note"]]
        save_df.to_csv("commandes.csv", index=False, quoting=csv.QUOTE_NONNUMERIC)

        # 🔥 Utilise le clients_df chargé plus haut
        # Harmonisation des types (très important pour le merge !)
        clients_df["customer_id"] = clients_df["customer_id"].astype(str)
        clients_df["customer_id"] = clients_df["customer_id"].apply(lambda x: str(x).split(".")[0] if str(x).endswith(".0") else str(x))
    
        orders_df["customer_id"] = orders_df["customer_id"].astype(str)

        # Jointure avec la Google Sheet des clients
        full_df = orders_df.merge(clients_df, on="customer_id", how="left")
        
        
        # Affichage (vérifie que les colonnes existent dans tes DataFrames !)
        shopify_display = full_df[["order_number", "Plat", "Nom", "quantity", "source_name", "note"]].copy()

        # Si tu veux un select dynamique sur les Noms possibles :
        Noms_clients = sorted(clients_df["Nom"].dropna().unique())

        edited_shopify = st.data_editor(
            shopify_display,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Plat": st.column_config.SelectboxColumn("Plat", options=plats_disponibles, required=True),
                "Nom": st.column_config.SelectboxColumn("Nom", options=Noms_clients, required=True),
                "source_name": st.column_config.SelectboxColumn("Source", options=sources)
            }
        )

        if st.button("📅 Sauvegarder commandes Shopify"):
            edited_shopify.to_csv("commandes.csv", index=False, quoting=csv.QUOTE_NONNUMERIC)
            st.success("Commandes Shopify sauvegardées.")

edited_shopify.to_csv("commandes.csv", index=False, quoting=csv.QUOTE_NONNUMERIC)

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
            "Nom": st.column_config.SelectboxColumn("Nom", options=Noms_clients, required=True),
            "source_name": st.column_config.SelectboxColumn("Source", options=sources)
        }
    )


    if st.button("📅 Sauvegarder commandes additionnelles"):
        edited_new = edited_new.copy()
        # Gérer consistance des types
        edited_new["order_number"] = pd.to_numeric(edited_new.get("order_number"), errors="coerce").fillna(0).astype(int)

        # Si tu veux toujours que les nouveaux aient un numéro unique :
        # 1. Regarder ceux dont order_number ==0 => leur donner un nouveau
        if edited_new["order_number"].eq(0).any():
            max_number = edited_new["order_number"].max()
            mask_new = edited_new["order_number"] == 0
            count_new = mask_new.sum()
            edited_new.loc[mask_new, "order_number"] = range(max_number + 1, max_number + 1 + count_new)

        # Écraser le fichier (supprimera les lignes manquantes)
        edited_new.to_csv("commandes_additionnelles.csv", index=False)
        st.success("Commandes additionnelles sauvegardées avec suppression.")






with tabs[2]:
    st.header("👥 Informations clients")
    colonnes_clients = ["Nom", "Email", "Telephone", "Adresse", "Ville", "Itineraire"]

    # 🔥 Initialisation : charger dans st.session_state
    if "clients_df" not in st.session_state:
        from_path = load_all_clients(sheet_url)
        from_csv = pd.read_csv("Clients.csv") if os.path.exists("Clients.csv") else pd.DataFrame(columns=colonnes_clients)
        initial_clients_df = pd.concat([from_csv, from_path], ignore_index=True)
        initial_clients_df = initial_clients_df.drop_duplicates(subset="Nom", keep="last")
        initial_clients_df = initial_clients_df[["Nom", "Email", "Telephone", "Adresse", "Ville", "Itineraire","customer_id"]]
        st.session_state["clients_df"] = initial_clients_df

    # 🔥 Edition en live
    edited_clients = st.data_editor(
        st.session_state["clients_df"],
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Nom": st.column_config.TextColumn("Nom", required=True),
            "Itineraire": st.column_config.SelectboxColumn("Itineraire", options=[str(i) for i in range(1, 6)])
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
    # -- Chargement
    df1 = pd.read_csv("commandes.csv") if os.path.exists("commandes.csv") else pd.DataFrame()
    df2 = pd.read_csv("commandes_additionnelles.csv", sep=",", quotechar='"') if os.path.exists("commandes_additionnelles.csv") else pd.DataFrame()
    df_all = pd.concat([df1, df2], ignore_index=True)

    clients_df = pd.read_csv("Clients.csv") if os.path.exists("Clients.csv") else pd.DataFrame()
    produits_prices = pd.read_csv("produits_prices.csv") if os.path.exists("produits_prices.csv") else pd.DataFrame()

    # -- Harmoniser le type de customer_id si présent
    if "customer_id" in df_all.columns and "customer_id" in clients_df.columns:
        df_all["customer_id"] = df_all["customer_id"].astype(str)
        clients_df["customer_id"] = clients_df["customer_id"].astype(str)

    # -- Toujours essayer de merger SUR customer_id d'abord (si dispo)
    if "customer_id" in df_all.columns and "customer_id" in clients_df.columns:
        final_df = df_all.merge(
            clients_df[["customer_id", "Nom", "Email", "Telephone", "Adresse", "Ville", "Itineraire"]], 
            how="left", 
            on="customer_id", 
            suffixes=("", "_client")
        )
    else:
        # Sinon, fusionne directement sur "Nom"
        final_df = df_all.merge(
            clients_df[["Nom", "Email", "Telephone", "Adresse", "Ville", "Itineraire"]], 
            how="left", 
            on="Nom", 
            suffixes=("", "_client")
        )

    # -- Supprimer colonnes parasites
    final_df.drop(columns=[col for col in final_df.columns if col.lower().startswith("unnamed") or col == "customer_id"], inplace=True, errors="ignore")

    # -- Fusion champs _x/_y pour les principaux champs clients
    for col in ["Email", "Telephone", "Adresse", "Ville", "Itineraire"]:
        col_x, col_y = f"{col}_x", f"{col}_y"
        if col_x in final_df.columns and col_y in final_df.columns:
            final_df[col] = final_df[col_x].combine_first(final_df[col_y])
            final_df.drop(columns=[col_x, col_y], inplace=True, errors="ignore")

    # ========== Ajout du prix depuis produits_prices.csv ==========
    if not produits_prices.empty:
        prix_map = produits_prices.set_index("title")["price"].to_dict()
        if "price" not in final_df.columns:
            final_df["price"] = final_df["Plat"].map(prix_map).astype(float)
        else:
            final_df["price"] = final_df["price"].fillna(final_df["Plat"].map(prix_map).astype(float))
    else:
        st.warning("⚠️ Fichier produits_prices.csv non trouvé ou vide. Pas de correspondance des prix possible.")

    # -- Calcul du total
    final_df["total"] = final_df["price"] * final_df["quantity"].fillna(0)

    # -- Réorganiser les colonnes (sans risque de "Nom complet")
    final_order = [
        "order_number", "Nom", "Plat", "quantity", "price", "total", "source_name", "note",
        "Itineraire", "Email", "Telephone", "Adresse", "Ville"
    ]
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

with tabs[5]:
    st.header("✏️ Pivot éditable des commandes")
    
    df1 = pd.read_csv("commandes.csv") if os.path.exists("commandes.csv") else pd.DataFrame()
    if "note" in df1.columns:
        df1["note"] = df1["note"].fillna("")
    if "source_name" in df1.columns:
        df1["source_name"] = df1["source_name"].fillna("")

    df2 = pd.read_csv("commandes_additionnelles.csv") if os.path.exists("commandes_additionnelles.csv") else pd.DataFrame()
    df_all = pd.concat([df1, df2], ignore_index=True)

    # Assurer cohérence
    df_all["Plat"] = df_all["Plat"].astype(str)
    df_all["quantity"] = pd.to_numeric(df_all["quantity"], errors="coerce").fillna(0)

    pivot_edit = df_all.pivot_table(
        index=["order_number", "Nom", "source_name", "note"],
        columns="Plat",
        values="quantity",
        aggfunc="sum",
        fill_value=0
    ).reset_index()

    plats = [col for col in pivot_edit.columns if col not in ["order_number", "Nom", "source_name", "note"]]

    edited_pivot = st.data_editor(
        pivot_edit,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Nom": st.column_config.SelectboxColumn("Nom", options=Noms_clients, required=True),
            "source_name": st.column_config.SelectboxColumn("Source", options=sources, required=True),
            **{plat: st.column_config.NumberColumn(plat, min_value=0, step=1) for plat in plats}
        }
    )

    if st.button("💾 Sauvegarder modifications Pivot"):
        # Remettre sous forme ligne par plat
        lines = []
        for idx, row in edited_pivot.iterrows():
            for plat in plats:
                qty = row[plat]
                if qty > 0:
                    lines.append({
                        "order_number": row.get("order_number", None),
                        "Nom": row["Nom"],
                        "Plat": plat,
                        "quantity": qty,
                        "source_name": row["source_name"],
                        "note": row["note"]
                    })
        
        new_df = pd.DataFrame(lines)

        # Charger existant
        commandes_file = "commandes.csv"
        commandes_add_file = "commandes_additionnelles.csv"
        
        df_existing1 = pd.read_csv(commandes_file) if os.path.exists(commandes_file) else pd.DataFrame()
        df_existing2 = pd.read_csv(commandes_add_file) if os.path.exists(commandes_add_file) else pd.DataFrame()

        df_existing = pd.concat([df_existing1, df_existing2], ignore_index=True)

        # Gérer les order_number
        if "order_number" not in df_existing.columns:
            df_existing["order_number"] = 0

        df_existing["order_number"] = pd.to_numeric(df_existing["order_number"], errors="coerce").fillna(0).astype(int)

        new_df["order_number"] = pd.to_numeric(new_df["order_number"], errors="coerce")

        to_update = new_df[new_df["order_number"].notna()].astype({"order_number": int})
        to_add = new_df[new_df["order_number"].isna()]

        # Ajouter les nouveaux order_numbers
        last_number = df_existing["order_number"].max() if not df_existing.empty else 1000
        to_add = to_add.copy()
        to_add["order_number"] = range(last_number + 1, last_number + 1 + len(to_add))

        if not to_update.empty:
            # ✅ Eliminer les doublons sur order_number
            to_update = to_update.groupby("order_number").first()
            
            df_existing.set_index("order_number", inplace=True)
            to_update = to_update.reindex_like(df_existing, method=None)  # Aligner index
            df_existing.update(to_update)
            df_existing.reset_index(inplace=True)


        # Ajouter les nouvelles lignes
        final_df = pd.concat([df_existing, to_add], ignore_index=True)

        # Sauver dans les deux fichiers
        final_df1 = final_df[final_df["source_name"] == "web"]
        final_df2 = final_df[final_df["source_name"] != "web"]

        final_df1.to_csv(commandes_file, index=False)
        final_df2.to_csv(commandes_add_file, index=False)

        st.success("✅ Pivot sauvegardé correctement.")
        st.rerun()
