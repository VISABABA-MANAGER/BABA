
# Visa Manager Pro V3

Nouveautés principales :
- Checklist automatique selon le type de visa
- Statuts de checklist : Manquant / Ajouté / À vérifier / Validé / Expiré
- Gestion avancée des documents : ajout, téléchargement, suppression
- Historique des actions (audit log)
- Paramètres de l'agence
- PDF récapitulatif personnalisé avec données de l'agence et checklist
- Authentification administrateur / employé

## Compte initial
Email : admin@visamanager.local
Mot de passe : Admin123!

## Installation
1. Installer Python 3.10+
2. Ouvrir un terminal dans ce dossier
3. Créer l'environnement :
   python -m venv .venv
4. Activer l'environnement
5. Installer :
   pip install -r requirements.txt
6. Lancer :
   python app.py
7. Ouvrir :
   http://127.0.0.1:5000

## Important avant mise en ligne
- Remplacer SQLite par PostgreSQL
- Utiliser un stockage cloud sécurisé
- Ajouter HTTPS
- Remplacer la clé secrète
- Changer le mot de passe administrateur initial
- Chiffrer les données sensibles
- Ajouter sauvegardes, antivirus et politique de rétention
