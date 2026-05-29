# Guía de Traspaso (Handover Guide) — Studio Batch Uploader

¡Hola! Si eres otra IA o desarrollador tomando el control de este proyecto, este documento te dará todo el contexto necesario sobre el estado actual, arquitectura, decisiones tomadas y cómo continuar de forma inmediata.

---

## 📌 Contexto del Proyecto

El **Studio Batch Uploader** es una herramienta web interna diseñada para el equipo de Seedtag. Permite:
1. Subir videos en lote (lotes CTV) directamente a **Studio Seedtag** usando la API de GraphQL de producción (`https://studio.seedtag.com/g`).
2. Asociar el lote de subida a un ticket específico de Jira del proyecto **SDS** (ej. `SDS-1234`).
3. Auto-detectar campos clave (*Operator Entity* -> País, e *Industry* -> Categoría) desde el ticket de Jira.
4. Mostrar el progreso en tiempo real de cada video de forma dinámica en una UI premium.
5. Al finalizar el lote, añadir automáticamente un comentario de reporte en el ticket de Jira con la tabla de vistas previas generadas (`preview_url`).

---

## 🛠️ Arquitectura Implementada

El proyecto ha sido completamente desarrollado con un enfoque robusto y premium:

```
├── app/
│   ├── app.py              # Lógica del servidor Flask, endpoints de la API y worker en segundo plano
│   ├── database.py         # Capa de persistencia relacional local (SQLite3: jobs.db)
│   ├── jira_client.py      # Cliente REST API v2 tolerante a fallos para interactuar con Jira
│   ├── app_test.py         # Suite de pruebas unitarias para parseo, mapeo y lógica
│   └── templates/
│       └── index.html      # UI premium interactiva basada en el manual de identidad de Seedtag
├── reference/
│   ├── studio_api.py       # Cliente REAL de producción de Studio (GraphQL y subida HTTP)
│   └── INTEGRATION.md      # Documentación técnica de cómo interactuar con el cliente de Studio
├── .env.example            # Plantilla para variables de entorno locales
├── Dockerfile              # Configuración de contenedor optimizada para Google Cloud Run
├── firebase.json           # Configuración para Firebase Hosting que conecta con Cloud Run
└── FIREBASE_NOTES.md       # Anotación técnica del proyecto Firebase "FreelancerPortal"
```

### 1. Base de Datos Local (SQLite3)
Ubicada en `tmp/jobs.db` (autoinicializada al arrancar).
- **`jobs`**: Almacena cabeceras del lote (`job_id`, `ticket_key`, `user_email`, `created_at`, `status`, `done`).
- **`job_items`**: Almacena cada video del lote (`id`, `job_id`, `filename`, `path`, `status`, `url`, `msg`, `created_at`).
- Mantiene un historial de subidas persistente que se renderiza dinámicamente en el frontend.

### 2. Capa Jira (`jira_client.py`)
- Filtra tickets bajo una estricta directiva de seguridad: solo interactúa con tickets del proyecto `SDS` (ej. `SDS-XXXX`).
- Lee los campos personalizados `customfield_14324` (País) y `customfield_15831` (Categoría) para auto-completar los dropdowns en la UI.
- Postea comentarios en formato Atlassian Wiki con la tabla detallada de previews.
- **Tolerancia a fallos:** Si Jira no está configurado en el `.env` o falla, la aplicación entra en modo "Solo Studio" graciosamente, sin interrumpir las subidas.

### 3. Frontend Premium (`templates/index.html`)
Diseñado meticulosamente siguiendo las pautas de marca de Seedtag:
- **Estética**: Diseño oscuro (*pure black* `#000000`), tarjetas glassmorphism traslúcidas (`backdrop-filter`) usando `#2F2E2E` (Grey-5), y color de acento **Coral Seedtag** (`#FF6B7C`).
- **Lens Glow**: Efectos radiales difuminados de marca en segundo plano.
- **Tipografía**: `Instrument Sans` para textos generales e `Instrument Serif Italic` para enfatizar titulares claves.
- **Interactividad**: Drag & Drop animado, visor de cola activa con polling dinámico cada 2s, y buscador de historial de subidas anteriores.
- **Auto-detección**: Listener con *debounce* (800ms) que consulta la API de Jira y auto-selecciona los metadatos adecuados.

---

## ⚡ Estado de Despliegue & Firebase

### Repositorio Git
El código ha sido configurado y subido exitosamente a la rama principal de GitHub:
👉 **[https://github.com/sebastianpacheco-ctv/seedtag_studio_uploader](https://github.com/sebastianpacheco-ctv/seedtag_studio_uploader)**

### Cloud Run & Firebase Hosting
Actualmente, el despliegue a producción se encuentra en pausa debido a:
- La cuenta de Seedtag (`sebastianpacheco@seedtag.com`) tiene acceso al proyecto Firebase **`FreelancerPortal`** (ID: `decoded-theme-461808-d3`).
- Sin embargo, este proyecto **no cuenta con facturación (Billing) activa** en la consola de Google Cloud, un requisito obligatorio para habilitar los servicios Cloud Run, Cloud Build y Artifact Registry.
- Hemos documentado detalladamente toda la información, IDs y checklists de despliegue en **[FIREBASE_NOTES.md](file:///Users/sebastianpacheco/Downloads/ViBeCoding/01_Active%20%F0%9F%9F%A2/Studio-batch-uploader/FIREBASE_NOTES.md)** para cuando la facturación sea habilitada por IT.

---

## 🚀 Cómo Arrancar y Probar Localmente

1. **Entorno Virtual e Instalar Dependencias**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Variables de Entorno**:
   Copia `.env.example` a `.env` y completa tus datos de prueba para Jira y Studio JWT.

3. **Ejecutar Pruebas**:
   Asegúrate de que todo funcione perfectamente corriendo la suite de tests unitarios:
   ```bash
   python3 -m unittest discover -s app -p "*_test.py"
   ```

4. **Correr el Servidor**:
   ```bash
   python app/app.py
   ```
   Abre [http://127.0.0.1:8088](http://127.0.0.1:8088). ¡Listo!

---

## 🔮 Sugerencias para el Siguiente Modelo de IA

Si vas a continuar expandiendo esta aplicación, aquí tienes excelentes puntos de partida:
1. **SSO Real**: Integrar Firebase Auth de forma real con Google Workspace SSO una vez que la facturación de Firebase esté lista.
2. **Reintentos Dinámicos en Backend**: Aumentar la resiliencia en `_run_job` para pausar y reanudar subidas de videos pesados en caso de inestabilidad de red.
3. **Manejo de Roles**: Restringir ciertas operaciones de subida basándose en el email del SSO.

¡Buena suerte programando! 🚀
