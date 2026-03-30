# API Integrations Catalog — Patterns one-off

> Patterns d'intégration API extraits des repos de test KB mais **non indexés** en KB.
> Ces patterns sont des exemples concrets d'appel à des services tiers.
> À exploiter après la phase de test KB (18 repos).
>
> Dernière mise à jour : 30 mars 2026

---

## Pourquoi ce fichier ?

Les patterns d'intégration API (Stripe, Twilio, Google Drive, etc.) sont des exemples one-off :
ils montrent comment appeler UN service spécifique, pas un pattern architectural réutilisable.

Ils ne vont pas en KB Qdrant (trop spécifiques pour le retriever sémantique), mais ils ont
de la valeur pour :
- Générer des intégrations API dans les PRDs qui en demandent
- Servir de template quand le LLM doit intégrer un service tiers
- Alimenter un futur "API cookbook" ou un retriever dédié

---

## Format par entrée

```
### [Service] — [Fonction]
- **Source repo** : owner/repo
- **Fichier** : chemin relatif
- **Fonction(s)** : nom des exports
- **Méthode HTTP** : GET / POST
- **SDK/Client** : lib utilisée (axios, stripe, twilio, etc.)
- **Auth** : type d'auth (API key, OAuth token, bearer, etc.)
- **Description** : ce que fait le pattern en 1-2 lignes
```

---

## Repos indexés

### sahat/hackathon-starter (JS C — Hard)

#### Payment / E-commerce

**Stripe — Charge payment**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getStripe, postStripe
- **Méthode HTTP** : GET (form) + POST (charge)
- **SDK/Client** : `stripe` npm
- **Auth** : API key (STRIPE_SKEY / STRIPE_PKEY)
- **Description** : Affiche formulaire de paiement puis crée un charge via Stripe API. Pattern : publishable key côté client, secret key côté serveur.

**PayPal — Checkout order + capture**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getPayPal, getPayPalSuccess, getPayPalCancel
- **Méthode HTTP** : GET (3 routes : create/success/cancel)
- **SDK/Client** : `@paypal/checkout-server-sdk` ou REST API direct
- **Auth** : OAuth client credentials (PAYPAL_ID / PAYPAL_SECRET)
- **Description** : Flow complet PayPal Checkout : create order → redirect → capture on success → cancel handler. 3 fonctions = 3 étapes du flow.

#### Communication

**Twilio — Send SMS**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getTwilio, postTwilio
- **Méthode HTTP** : GET (form) + POST (send)
- **SDK/Client** : `twilio` npm
- **Auth** : Account SID + Auth Token
- **Description** : Envoie un SMS via Twilio. Gère mode sandbox vs live, error handling pour numéros non vérifiés.

**Lob — Physical letter**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getLob
- **Méthode HTTP** : GET
- **SDK/Client** : `lob` npm
- **Auth** : API key
- **Description** : Crée et affiche une lettre physique avec validation d'adresse USPS.

#### Data / Media APIs

**Foursquare — Trending venues**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getFoursquare
- **Méthode HTTP** : GET
- **SDK/Client** : axios / fetch
- **Auth** : API key
- **Description** : Récupère les lieux tendance et détails d'un lieu spécifique via Foursquare Places API.

**Last.fm — Artist info**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getLastfm
- **Méthode HTTP** : GET
- **SDK/Client** : axios / fetch
- **Auth** : API key
- **Description** : Récupère info artiste, top tracks, albums via Last.fm API.

**New York Times — Bestsellers**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getNewYorkTimes
- **Méthode HTTP** : GET
- **SDK/Client** : axios / fetch
- **Auth** : API key
- **Description** : Récupère la liste bestsellers Young Adult Hardcover.

**Alpha Vantage — Stock chart**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getChart
- **Méthode HTTP** : GET
- **SDK/Client** : axios / fetch
- **Auth** : API key
- **Description** : Récupère données boursières MSFT et affiche un chart interactif.

**PubChem — Chemical data**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getPubChem
- **Méthode HTTP** : GET
- **SDK/Client** : axios / fetch
- **Auth** : aucune (API publique)
- **Description** : Récupère données chimiques d'un composé (Aspirin).

**Wikipedia — Article search**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getWikipedia
- **Méthode HTTP** : GET
- **SDK/Client** : axios / fetch
- **Auth** : aucune (API publique)
- **Description** : Recherche Wikipedia, affiche sections, texte et images.

**GIPHY — GIF search**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getGiphy
- **Méthode HTTP** : GET
- **SDK/Client** : axios / fetch
- **Auth** : API key
- **Description** : Recherche de GIFs animés par query utilisateur.

#### Social / OAuth-based APIs

**GitHub — User repos + events**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getGithub
- **Méthode HTTP** : GET
- **SDK/Client** : `@octokit/rest`
- **Auth** : OAuth token (stored in user.tokens)
- **Description** : Récupère repos, events, et stargazers via Octokit. Pattern : check token → API call → render.

**Facebook — User profile**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getFacebook
- **Méthode HTTP** : GET
- **SDK/Client** : axios / Graph API
- **Auth** : OAuth token
- **Description** : Récupère profil utilisateur (nom, email, locale) via Facebook Graph API.

**Tumblr — User info + posts**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getTumblr
- **Méthode HTTP** : GET
- **SDK/Client** : `tumblr.js` ou custom OAuth 1.0a
- **Auth** : OAuth 1.0a token
- **Description** : Récupère info utilisateur authentifié et posts de blog public.

**Twitch — User + followers + streams**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getTwitch
- **Méthode HTTP** : GET
- **SDK/Client** : axios / Helix API
- **Auth** : OAuth token
- **Description** : Récupère données utilisateur, followers, et streams pour un jeu via Twitch Helix API.

**Steam — Player achievements + games**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getSteam
- **Méthode HTTP** : GET
- **SDK/Client** : axios / Steam Web API
- **Auth** : API key + Steam ID
- **Description** : Récupère achievements, game summaries, et bibliothèque de jeux.

**Trakt.tv — Movies + watchlist**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getTrakt
- **Méthode HTTP** : GET
- **SDK/Client** : axios
- **Auth** : OAuth token + client ID
- **Description** : Affiche films tendance, profil utilisateur et historique de visionnage.

**QuickBooks — Customer data**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getQuickbooks
- **Méthode HTTP** : GET
- **SDK/Client** : `node-quickbooks`
- **Auth** : OAuth 2.0 token + realm ID
- **Description** : Query les données client dans QuickBooks comptabilité.

#### Google Services

**Google Drive — List files**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getGoogleDrive
- **Méthode HTTP** : GET
- **SDK/Client** : `googleapis`
- **Auth** : OAuth token
- **Description** : Liste les fichiers Google Drive de l'utilisateur authentifié.

**Google Sheets — Read spreadsheet**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getGoogleSheets
- **Méthode HTTP** : GET
- **SDK/Client** : `googleapis`
- **Auth** : API key (public sheet)
- **Description** : Récupère données d'un Google Sheet public.

**Google Maps — Display map**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getGoogleMaps
- **Méthode HTTP** : GET
- **SDK/Client** : frontend JS (Google Maps JS API)
- **Auth** : API key
- **Description** : Affiche interface Google Maps avec clé API.

**HERE Maps — Display map**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getHereMaps
- **Méthode HTTP** : GET
- **SDK/Client** : frontend JS (HERE Maps JS API)
- **Auth** : API key
- **Description** : Affiche interface HERE Maps avec clé API.

#### Web Scraping

**Hacker News — Scraping**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getScraping
- **Méthode HTTP** : GET
- **SDK/Client** : `cheerio` + axios
- **Auth** : aucune
- **Description** : Extrait les liens de Hacker News via parsing HTML avec Cheerio.

#### AI / ML

**OpenAI Moderation — Content check**
- **Fichier** : controllers/ai.js
- **Fonction(s)** : getOpenAIModeration, postOpenAIModeration
- **Méthode HTTP** : GET (form) + POST (check)
- **SDK/Client** : `openai` npm
- **Auth** : API key
- **Description** : Soumet du texte à l'endpoint modération d'OpenAI, affiche les catégories flaggées.

**Groq Vision — Image analysis**
- **Fichier** : controllers/ai.js
- **Fonction(s)** : getLLMCamera, postLLMCamera
- **Méthode HTTP** : GET (form) + POST (analyze)
- **SDK/Client** : `groq-sdk` ou axios
- **Auth** : API key
- **Description** : Upload image → analyse via Groq Vision API → description textuelle.

**Groq — Text classification**
- **Fichier** : controllers/ai.js
- **Fonction(s)** : getLLMClassifier, postLLMClassifier
- **Méthode HTTP** : GET (form) + POST (classify)
- **SDK/Client** : `groq-sdk` ou axios
- **Auth** : API key
- **Description** : Classifie un message client dans un département via LLM.

**RAG Pipeline — PDF ingest + query**
- **Fichier** : controllers/ai.js
- **Fonction(s)** : getRag, postRagIngest, postRagAsk
- **Méthode HTTP** : GET (dashboard) + POST (ingest) + POST (ask)
- **SDK/Client** : custom (PDF extract → embedding → MongoDB vector search)
- **Auth** : LLM API key
- **Description** : Pipeline RAG complet : ingestion PDF → chunking → embeddings → stockage MongoDB → query avec et sans contexte pour comparaison.

#### File Upload

**Multer — File upload**
- **Fichier** : controllers/api.js
- **Fonction(s)** : getFileUpload, postFileUpload, uploadMiddleware
- **Méthode HTTP** : GET (form) + POST (upload)
- **SDK/Client** : `multer` (diskStorage)
- **Auth** : aucune (route protégée par isAuthenticated)
- **Description** : Upload fichier avec multer, validation taille, stockage disk.

---

## Patterns à ajouter (repos futurs)

> Compléter ce fichier au fur et à mesure des tests TS, Go, Rust, C++.
> Format identique : service, fichier, fonctions, méthode, SDK, auth, description.
