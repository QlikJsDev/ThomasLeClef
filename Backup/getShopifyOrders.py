import requests
import pandas as pd

# === Configuration ===
SHOPIFY_DOMAIN = "2c3fd5-e6.myshopify.com"
API_VERSION = "2025-01"
ACCESS_TOKEN = "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"  # à remplacer par ton token personnel
ENDPOINT = f"https://{SHOPIFY_DOMAIN}/admin/api/{API_VERSION}/orders.json"

# === En-têtes d'authentification ===
headers = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": ACCESS_TOKEN
}

# === Requête vers l'API ===
response = requests.get(ENDPOINT, headers=headers)

if response.status_code == 200:
    orders = response.json().get("orders", [])

    # Rassembler tous les line_items de toutes les commandes
    all_line_items = []
    for order in orders:
        for item in order.get("line_items", []):
            all_line_items.append({
                "product_id": item.get("product_id"),
                "title": item.get("title")
            })

    # Transformer en DataFrame
    df_items = pd.DataFrame(all_line_items)

    # Supprimer les doublons
    df_unique = df_items.drop_duplicates().reset_index(drop=True)

    # Afficher les valeurs distinctes
    print(df_unique)

else:
    print(f"Erreur {response.status_code} : {response.text}")