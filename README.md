# Studio Batch Uploader — kit de arranque

Todo lo necesario para construir, en otro lado, una web app que sube varios
videos a Studio Seedtag asociados a un ticket y devuelve los links de preview.

## Qué hay acá

```
studio-batch-uploader-kit/
├── KICKOFF.md              ← spec / recomendación de arquitectura. EMPEZÁ ACÁ.
├── CLAUDE.md               ← reglas del proyecto (seguridad, auth, convenciones)
├── requirements.txt
├── .env.example            ← copiá a .env y completá (NUNCA subas .env)
├── .gitignore
├── reference/
│   ├── studio_api.py       ← cliente REAL de Studio (de producción). Autocontenido.
│   └── INTEGRATION.md       ← cómo usar studio_api.py (snippets reales)
└── app/
    ├── app.py              ← scaffold Flask (con TODOs marcados)
    └── templates/
        └── index.html       ← UI mínima drag&drop (estilo dark Seedtag)
```

## Primeros pasos

```bash
cd studio-batch-uploader-kit
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # completá STUDIO_JWT_COOKIE (para el spike) + Jira
python app/app.py           # http://127.0.0.1:8088
```

## Orden recomendado
1. Leé `KICKOFF.md` (scope + arquitectura + decisiones).
2. **Spike de auth de Studio** (lo de mayor riesgo): ¿token/OAuth por usuario o
   JWT pegado? Ver sección auth en `KICKOFF.md`.
3. Probá `reference/studio_api.py` con un JWT real (ver `reference/INTEGRATION.md`):
   subir 1 video → obtener `preview_url`.
4. El scaffold de `app/` ya hace el lote básico; completá los `TODO`
   (auth por usuario, country/category, adjuntar al ticket).

## Prompt para arrancar en un chat/agente nuevo

> "Abrí este repo (studio-batch-uploader-kit). Leé KICKOFF.md y CLAUDE.md.
> Reusá reference/studio_api.py para todo lo de Studio (no reimplementes la
> integración; mirá reference/INTEGRATION.md). Empezá por un spike de la auth
> de Studio por usuario, después completá los TODO del scaffold en app/app.py.
> Respetá las reglas: nunca borrar de Jira/Studio, validar proyecto SDS, solo
> crear/adjuntar."

## Nota
`reference/studio_api.py` es una copia del cliente que ya corre en producción en
`csv-automation`. Si Studio cambia su API, sincronizá ambos. No incluye secretos
(el JWT entra en runtime). El cliente de Jira NO se incluyó: si necesitás
adjuntar al ticket, copiá `jira_client.py` del repo `csv-automation`.
