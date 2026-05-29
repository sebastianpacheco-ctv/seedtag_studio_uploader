# Integración con Studio — referencia real

`reference/studio_api.py` es una **copia funcional** del cliente de Studio que
ya corre en producción en `csv-automation`. Es autocontenido: solo depende de
`requests` (+ stdlib). Podés usarlo tal cual.

---

## 1. Instanciar el cliente

```python
from studio_api import (
    StudioAPIClient,
    StudioVideoNotReadyError,
    StudioJWTExpiredError,
)
from pathlib import Path

studio = StudioAPIClient(
    jwt_cookie=user_jwt,                 # JWT de Studio (cookie seedtag_jwt)
    sidecar_path=Path("./.studio_jwt"),  # opcional: persiste el JWT rolado (chmod 600)
)
```

- `jwt_cookie`: el JWT del usuario. Para "por usuario", este es el JWT de la
  sesión de esa persona (no uno compartido).
- `sidecar_path`: si lo pasás, el cliente persiste el cookie rolado tras cada
  call. Para multi-usuario probablemente NO uses un sidecar compartido —
  guardá el JWT en la sesión del usuario en su lugar.

---

## 2. Subir un video y obtener el link (flujo end-to-end)

```python
sres = studio.process_video_to_creative(
    file_path=Path("/ruta/al/video.mp4"),
    ticket_title="NOMBRE_DEL_CREATIVE",   # se usa como nombre del creative
    country=country,                      # mapeado (ej. "usa") — ver COUNTRY_MAP
    category=category,                    # mapeado — ver map_category
)
# sres == {
#   "video_id":    "...",
#   "creative_id": "...",
#   "vast_url":    "https://creatives.seedtag.com/vasts/<video_id>.xml",
#   "preview_url": "https://preview.seedtag.com/creative/<creative_id>",
# }
preview = sres["preview_url"]   # <-- esto es lo que devolvés al usuario
```

Internamente `process_video_to_creative` hace:
1. `upload_video()` — multipart GraphQL upload (sanitiza el filename:
   Studio exige MAYÚSCULAS con `-`/`_`).
2. `wait_video_ready()` — espera a que Studio procese (CTV ~30s).
3. `build_csv_ctv_ad_template()` + `create_cov_creative()`.
4. `set_creative_dimensions()` — country/category para que aparezca en la lista.
5. devuelve las URLs.

---

## 3. Manejo de errores (importante para el lote)

```python
try:
    sres = studio.process_video_to_creative(file_path=f, ticket_title=name,
                                             country=c, category=cat)
    resultado = {"file": f.name, "ok": True, "url": sres["preview_url"]}

except StudioVideoNotReadyError as nre:
    # El video se subió pero Studio sigue PROGRESSING tras el timeout.
    # NO se reintenta el upload — el video YA está en Studio.
    # Guardá nre.video_id y mostrá "procesando, revisá en Studio Manager".
    resultado = {"file": f.name, "ok": False,
                 "pending_video_id": nre.video_id,
                 "msg": f"sigue procesando tras {nre.elapsed_seconds}s"}

except StudioJWTExpiredError:
    # El JWT del usuario caducó → pedile que lo renueve (re-pegar / re-login).
    resultado = {"file": f.name, "ok": False, "msg": "JWT de Studio vencido"}

except Exception as e:
    resultado = {"file": f.name, "ok": False, "msg": str(e)}
```

> Regla de oro heredada: si un video queda PROGRESSING, **nunca** lo borres ni
> re-subas en loop. Queda en Studio; el usuario lo ve en Studio Manager.

---

## 4. Mapeos country / category

`studio_api.py` trae `COUNTRY_MAP` (ej. `"us" → "usa"`, `"es" → "spain"`) y
helpers de mapeo. `process_video_to_creative` espera los valores YA mapeados.
Si tu UI deja elegir país/categoría, mapealos antes de llamar (o exponé el mapa
como dropdown).

---

## 5. Adjuntar al ticket (opcional)

En `csv-automation`, `jira_client.py` lo hace con:
- `attach_file(ticket_key, file_path)` — sube el .mp4 al ticket (límite ~100 MB).
- `add_comment(ticket_key, text)` / `add_comment_adf(ticket_key, doc_body)` —
  comentario (texto plano o ADF).
- `append_to_description(ticket_key, new_nodes)` — agrega nodos ADF a la
  descripción (así se postean los links de Studio como lista).

Para esta tool, lo más simple es un **comentario** con la lista de links de
preview. Auth de Jira: API token básico (`JIRA_EMAIL` + `JIRA_API_TOKEN`),
mismo patrón que el repo viejo. **Validá el proyecto (SDS) antes de comentar.**

> Si querés el código exacto de Jira, copialo de `csv-automation/src/jira_client.py`
> (no lo incluí acá porque trae lógica de descarga/forms que esta tool no usa).
