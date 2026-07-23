# Visa Manager Pro — Version prête à mettre en ligne

Cette version est adaptée à un déploiement web avec :
- Gunicorn pour le serveur de production
- Docker
- variables d'environnement pour les secrets
- stockage persistant de la base SQLite et des documents
- configuration Render via `render.yaml`

## Déploiement recommandé
1. Décompressez ce projet.
2. Placez-le dans un dépôt GitHub privé.
3. Connectez le dépôt à Render.
4. Créez le service à partir de `render.yaml`.
5. Render montera un disque persistant `/data`.
6. La base sera stockée dans `/data/visa_manager.db`.
7. Les documents seront stockés dans `/data/uploads`.

## Compte initial
Email : admin@visamanager.local
Mot de passe : Admin123!

Changez immédiatement ce mot de passe après la première connexion.

## Sécurité avant utilisation réelle
- Utilisez HTTPS.
- Gardez le dépôt privé.
- Utilisez une clé `SECRET_KEY` forte.
- Sauvegardez régulièrement le disque persistant.
- Ajoutez ultérieurement PostgreSQL et un stockage objet privé pour une montée en charge.
- Ajoutez un scan antivirus des documents téléversés.
- Définissez une politique de conservation et suppression des copies de passeports et autres données personnelles.

## Lancement local
`pip install -r requirements.txt`
puis :
`python app.py`

## Lancement production
`gunicorn --bind 0.0.0.0:5000 --workers 2 --threads 4 --timeout 120 app:app`
