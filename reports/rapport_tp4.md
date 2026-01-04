# Exercice 1 : Mise en route + rappel de contexte (sanity checks + où on en est dans la pipeline)

## Commandes utilisées

Ajout du service MLflow dans `docker-compose.yml`, puis redémarrage complet :

```bash
docker compose down
docker compose up -d --build
docker compose ps

```

![alt text](image-11.png)

## Preuves d’accessibilité des services

**MLflow UI**

![alt text](image-12.png)

**API FastAPI /health**

![alt text](image-13.png)

**Smoke check Feast Online via l’API**

![alt text](image-14.png)

La stack exécute :
- PostgreSQL :stockage des tables live, snapshots et online store Feast
- Feast : Feature Store pour définitions des features et accès offline/online
- Prefect : orchestration des flows d’ingestion et scripts de préparation de dataset
- MLflow :tracking des expériences, stockage des artefacts et Model Registry
- API FastAPI : exposition d’endpoints

# Exercie 2 :Créer un script d’entraînement + tracking MLflow (baseline RandomForest)
```
docker compose exec -e TRAIN_AS_OF=2024-01-31 prefect \
  python /opt/prefect/flows/train_baseline.py
```
![alt text](image-15.png)


**AS_OF** : 2024-01-31
**Nombre de lignes** : 7043
**cat_cols** : net_service
**Métriques et temps d’entraînement** :
- AUC : 0.6207

- F1 : 0.0384

- Accuracy : 0.7439

- Temps d’entraînement : 1.34 s 


Fixer `AS_OF` garantit que le dataset est construit à une date de référence précise, ce qui évite de mélanger des informations futures et réduit le risque de data leakage. Cela permet aussi de reconstruire exactement le même jeu d’entraînement plus tard, même si les tables live évoluent. Fixer `random_state` rend déterministes les étapes stochastiques (split train/val, initialisation du modèle, échantillonnage interne), donc on obtient des résultats comparables entre deux exécutions. Ensemble, `AS_OF` et `random_state` assurent la reproductibilité d’un entraînement et facilitent le debug, la comparaison d’expériences et l’audit MLOps via MLflow.



# Exercice 3 : Explorer l’interface MLflow et promouvoir un modèle

**Run sélectionné : `rf_baseline_2024-01-31`**

![alt text](image-16.png)

**Metrics**

![alt text](image-17.png)

**Artifacts**

![alt text](image-18.png)

**Model Registry avec la version en Production : Version 1**

![alt text](image-19.png)

Le Model Registry MLflow indique que le modèle streamflow_churn version 1 est actuellement le seul modèle en Production.

La promotion via le Model Registry est préférable à un déploiement manuel car elle centralise le cycle de vie du modèle tels que les versions, métadonnées et les artefacts et évite de dépendre de chemins locaux ou de fichiers copiés à la main.
Les stages (None/Staging/Production) imposent un processus explicite et traçable : on sait exactement quelle version est servie en production et pourquoi. 
Cela facilite aussi les rollbacks : si une version est mauvaise, on repasse immédiatement à la version précédente sans la redéployer. 
En plus, l’UI permet d’associer des validations avant promotion.

# Exercice 4 : Étendre l’API pour exposer /predict (serving minimal end-to-end)

![alt text](image-21.png)

![alt text](image-20.png)


Pointer l’API vers `models:/streamflow_churn/Production` garantit qu’elle charge exactement la version validée et promue via le Model Registry, plutôt qu’un fichier local non traçable. Le stage Production matérialise une décision explicite (gouvernance), avec historique de versions, métadonnées, métriques et artefacts associés. Cela facilite les rollbacks : on peut repasser à une version précédente en changeant le stage, sans redéploiement manuel. Tandis que un `.pkl` local est fragile et difficile à auditer et peut introduire du drift entre environnements. Le Registry réduit les erreurs humaines et standardise le cycle de vie du modèle en MLOps.


# Exercice 5 : Robustesse du serving : cas d’échec réalistes (sans monitoring)

**Requête qui réussit**

![alt text](image-21.png)

![alt text](image-20.png)

**Requête qui échoue**

![alt text](image-22.png)

**Ce qui peut mal tourner en serving et comment on le détecte tôt**

En production, beaucoup de pannes viennent des features plutôt que du modèle.
- Entité absente : si le user_id demandé n’est pas présent dans l’online store, Feast renvoie des valeurs manquantes (null).L’API pourrait produire une prédiction incohérente ou planter.Dans cet exemple , on détecte le problème tôt grâce au check X.isnull() et on renvoie une erreur explicite avec la liste des missing_features.
- Online store incomplet / obsolète : même si un utilisateur existe, la matérialisation peut être absente ou pas à jour, ce qui entraîne des colonnes nulles côté API. Le même garde-fou permet d’identifier immédiatement la panne avant d’appeler le modèle, ce qui évite des résultats incorrects et accélère le diagnostic.

# Exercice 6 : Réflexion de synthèse (ingénierie MLOps)

### 6.a

MLflow garantit d’abord la **traçabilité complète des entraînements** dont chaque run conserve les paramètres (AS_OF, hyperparamètres), les métriques (AUC, F1, ACC), les artefacts (schéma des features, modèle entraîné) et le code exécuté, ce qui permet de comprendre, comparer et reproduire un entraînement passé.  
Ensuite, MLflow assure une **identification claire des modèles servis** grâce au Model Registry dont chaque modèle est versionné, nommé et associé à un run précis, ce qui évite toute ambiguité sur l’origine d’un modèle déployé en production.

### 6.b

Le stage **Production** signifie que l’API charge automatiquement, au démarrage, **la version du modèle explicitement promue comme stable** via l’URI `models:/streamflow_churn/Production`.  
Cela permet de **décorréler le code de l’API du choix du modèle** qu'on peut changer de modèle en production sans redéployer l’API, simplement en modifiant le stage dans MLflow.  
En contrepartie, cela empêche les déploiements sauvages basés sur des fichiers locaux ou des chemins temporaires, renforçant ainsi le contrôle et la gouvernance du cycle de vie du modèle.

### 6.c

Malgré MLflow, la reproductibilité peut encore être rompue à plusieurs endroits :
1. **Les données** : si les snapshots changent, sont supprimés ou mal versionnés, le dataset d’entraînement ne sera plus identique.
2. **Le code** : une modification du code d’entraînement ou de feature engineering sans tag Git peut produire un modèle différent à paramètres égaux.
3. **L’environnement** : une évolution des versions de librairies (scikit-learn, Feast, pandas etc) ou de l’image Docker peut modifier les résultats.
4. **La configuration** : des variables d’environnement (AS_OF, chemins Feast etc ) mal fixées ou modifiées peuvent changer le comportement du pipeline.

