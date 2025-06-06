import os
import pandas as pd

# 📁 Chemin du dossier
folder_path = r"C:\Users\MGE\OneDrive\Documents\Qlik Clef"

# 📋 Noms de colonnes à forcer
columns = ["email", "updated_at", "created_at", "prenom", "nom", "phone", "adresse", "localite"]

# 🗃️ Liste des DataFrames valides
dfs = []

# 🔁 Parcours des fichiers .csv
for filename in os.listdir(folder_path):
    if filename.endswith(".csv") and filename[:-4].isdigit():
        filepath = os.path.join(folder_path, filename)
        try:
            df = pd.read_csv(filepath, header=None, names=columns)
            df["customer_id"] = filename.replace(".csv", "")
            dfs.append(df)
        except Exception as e:
            print(f"Erreur lecture {filename} : {e}")

# 📦 Fusion des DataFrames
if dfs:
    consolidated_df = pd.concat(dfs, ignore_index=True)
    output_file = os.path.join(folder_path, "clients_consolidated.csv")
    consolidated_df.to_csv(output_file, index=False)
    print(f"✅ Fichier consolidé généré : {output_file}")
else:
    print("❌ Aucun fichier .csv valide trouvé.")
