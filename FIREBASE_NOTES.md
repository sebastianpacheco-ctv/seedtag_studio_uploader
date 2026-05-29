# Nota Técnica — Configuración Firebase Pendiente

## Proyecto Firebase Correcto
- **Firebase Project ID:** `decoded-theme-461808-d3`
- **Nombre del Proyecto:** FreelancerPortal
- **GCP Project Number:** `987340441900`
- **Web App ID:** `Zjg3MTRjMzgtODc5Yi00MDIwLWI4OTUtNTViY2Q5NTkyOTdm`
- **Consola Firebase:** https://console.firebase.google.com/project/decoded-theme-461808-d3/settings/general/web:Zjg3MTRjMzgtODc5Yi00MDIwLWI4OTUtNTViY2Q5NTkyOTdm
- **Cuenta con acceso:** `sebastianpacheco@seedtag.com`

## Pendiente: Obtener la Firebase Config completa
Cuando se quiera integrar el Firebase JS SDK (para Auth, Firestore, etc.), ir a la 
consola arriba → copiar el objeto `firebaseConfig` y pegarlo en el frontend:

```js
// Estructura esperada (completar con los valores reales de la consola):
const firebaseConfig = {
  apiKey: "...",
  authDomain: "decoded-theme-461808-d3.firebaseapp.com",
  projectId: "decoded-theme-461808-d3",
  storageBucket: "decoded-theme-461808-d3.appspot.com",
  messagingSenderId: "987340441900",
  appId: "Zjg3MTRjMzgtODc5Yi00MDIwLWI4OTUtNTViY2Q5NTkyOTdm"
};
```

## Configuración Cloud Run (objetivo final)
- **Servicio Cloud Run:** `seedtag-studio-uploader`
- **Región:** `us-central1`
- **URL final esperada:** `https://seedtagstudiouploader.web.app` (Firebase Hosting)
  → redirige a → Cloud Run en el proyecto `decoded-theme-461808-d3`

## Estado actual
- [x] Código subido a GitHub: https://github.com/sebastianpacheco-ctv/seedtag_studio_uploader
- [x] Dockerfile y firebase.json creados
- [ ] Cloud Run desplegado (pendiente — usar proyecto decoded-theme-461808-d3)
- [ ] Firebase Hosting conectado a Cloud Run
- [ ] Firebase SDK integrado (opcional, solo si se quiere Firebase Auth / Firestore)
