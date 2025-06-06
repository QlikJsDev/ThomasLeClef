import requests
from datetime import datetime

# === PARAMÈTRES SHOPIFY (à adapter ou à lire depuis un fichier si besoin) ===
SHOPIFY_DOMAIN = "ton-shop.myshopify.com"
ACCESS_TOKEN = "ton_token"
API_VERSION = "2025-01"

# === DATE CIBLE POUR FILTRAGE ===
target_date = datetime.strptime("2025-04-10", "%Y-%m-%d").date()

# === RÉCUPÉRATION DES CLIENTS PAR DATE DE COMMANDE ===
def get_customers_by_order_date(target_date):
    url = f"https://{SHOPIFY_DOMAIN}/admin/api/{API_VERSION}/orders.json?status=any&limit=250"
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": ACCESS_TOKEN
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        orders = response.json().get("orders", [])
        customer_ids = []

        for order in orders:
            created_at = order.get("created_at", "")
            try:
                order_date = datetime.strptime(created_at[:10], "%Y-%m-%d").date()
                if order_date == target_date:
                    customer = order.get("customer", {})
                    if customer and "id" in customer:
                        customer_ids.append(customer["id"])
            except Exception as e:
                continue

        return list(set(customer_ids))  # éviter les doublons
    else:
        print(f"Erreur Shopify {response.status_code} : {response.text}")
        return []

# === EXÉCUTION ===
if __name__ == "__main__":
    clients = get_customers_by_order_date(target_date)
    print(f"Clients ayant commandé le {target_date} :")
    print(clients)
