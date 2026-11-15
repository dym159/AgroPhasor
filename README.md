# 🚀 AgroPhasor (Nasa_AgroFarm)

> **NASA Space Apps Challenge 2026**  
> **Reto:** *Field Shift: Adapting Farms with NASA Data*  
> **Solución:** Gemelo Digital Mecanicista y Optimizador Espaciotemporal de Rotación de Cultivos bajo Estrés Climático.

---

## 📋 Resumen del Proyecto

AgroPhasor es una plataforma web orientada al agricultor que modela la parcela agrícola como un sistema dinámico termodinámico acoplado (Humedad del suelo, Temperatura de la planta y Nutrientes NPK). Utiliza 20 a 30 años de historia agroclimatológica de **NASA POWER**, series de Fourier y perturbaciones de Montecarlo para alimentar un recomendador de rotación de cultivos optimizado mediante el algoritmo $A^*$.

---

## 🛡️ Seguridad y Git Hooks (Tarea Linear CC-01)

Para prevenir la filtración de claves privadas, archivos de credenciales de Google Cloud, archivos `.env` y secretos en el historial del repositorio, el proyecto cuenta con un sistema de **Git Hooks** y validaciones locales de CI inspirado en estándares de alta seguridad.

### 1. Requisitos previos

El escaneo de seguridad utiliza **Gitleaks**:

```bash
# Windows (PowerShell con winget)
winget install Gitleaks.Gitleaks

# macOS / Linux (Homebrew)
brew install gitleaks
```

*(Si no tienes Gitleaks instalado localmente, los scripts intentarán utilizar Docker automáticamente como respaldo).*

---

### 2. Activar los Git Hooks en tu clon local

Git no activa hooks versionados automáticamente al clonar. Cada miembro del equipo debe activar la ruta de hooks ejecutando una sola vez en la raíz del repositorio:

```bash
git config core.hooksPath .githooks
```

---

### 3. ¿Cómo funcionan los hooks configurados?

* **`pre-commit` (.githooks/pre-commit):**
  * Se ejecuta automáticamente antes de registrar cualquier commit.
  * Bloquea inmediatamente archivos sensibles preparados para commit (`.env`, `*.pem`, `*.key`, `id_rsa`, credenciales GCP `*gcp*.json`, `.netrc`).
  * Ejecuta `gitleaks protect --staged -v --redact` para auditar el contenido de los archivos preparados con salida redactada.
  * Detecta marcadores de conflicto de merge (`<<<<<<< / ======= / >>>>>>>`).
  * Muestra una advertencia preventiva si se está realizando un commit directamente sobre la rama principal `main`.

* **`pre-push` (.githooks/pre-push):**
  * Se ejecuta automáticamente antes de enviar cambios al repositorio remoto con `git push`.
  * Invoca el validador `./check-ci.sh`. Si se detecta un secreto o falla una validación, el push se cancela.

---

### 4. Validador de CI Local (`check-ci.sh`)

Puedes ejecutar la suite completa de verificaciones en cualquier momento antes de abrir un Pull Request:

```bash
./check-ci.sh
```

Este script ejecuta:
1. **Gitleaks detect:** Escanea el rango de commits entre tu rama y `origin/main`.
2. **Auditoría de archivos:** Verifica que no existan archivos privados rastreados por Git y que `.env.example` esté presente.
3. **Validación de código:** Ejecuta pruebas de backend (Python/pytest) y frontend si están configurados.

---

### 5. Configuración del Entorno Local

1. Copia la plantilla de variables de entorno:
   ```bash
   cp .env.example .env
   ```
2. Configura los parámetros necesarios en `.env`.
3. Recuerda: **el archivo `.env` nunca debe subirse al repositorio Git**.

---

## Mapa de parcelas (NAS-8)

Desde la raíz del repositorio, sirve el frontend y el backend con Python 3:

```bash
python -m pip install numpy "shapely>=2.1,<3" "pyproj>=3,<4"
python server.py
```

Al seleccionar un terreno, el mapa muestra la temperatura media del dosel por celda de 30 × 30 m. La malla se recorta al contorno. Cada celda usa la elevación, pendiente y orientación de SRTM v3 consultadas mediante Open Topo Data, y un forzamiento horario de NASA POWER consultado en un punto representativo de la parcela. Al tocar una celda se muestran la temperatura mínima, máxima y media del dosel.

La simulación busca el día histórico más reciente con 24 horas válidas de temperatura, radiación y humedad relativa dentro de los últimos 365 días. Usa 50 mm de agua radicular asumida. Si el cultivo elegido carece de calibración, se muestra la simulación de papa como referencia. El servicio limita cada parcela a 500 celdas y requiere conexión a ambas fuentes.

Abre [http://127.0.0.1:5173](http://127.0.0.1:5173). El mismo servidor entrega el frontend y la API bajo `/api/v1/`. La página usa Leaflet en el navegador y necesita conexión a internet para cargar la biblioteca, las imágenes de Esri World Imagery y la capa opcional NASA GIBS (HLS Sentinel-2).

Para servir un frontend ya compilado, define `AGROPHASOR_FRONTEND_DIR` con la ruta de la carpeta que contiene su `index.html` antes de ejecutar `python server.py`. El frontend debe llamar a EDO 1 con la ruta relativa `/api/v1/parcelas/edo1`.

El buscador consulta Nominatim solo al enviar el formulario y admite localidades de cualquier país. El servidor local comparte una caché en memoria y limita las consultas salientes. Para un despliegue compartido, usa un único punto de salida que aplique el límite global o configura otro servidor compatible mediante `AGROPHASOR_GEOCODER`. Revisa la [política de Nominatim](https://operations.osmfoundation.org/policies/nominatim/).

Para comprobar el mapa, navega y cambia el zoom con la atribución visible. Pulsa «Usar mi ubicación» y prueba conceder el permiso. Restablece el permiso del sitio, vuelve a pulsar el botón y deniega la solicitud para verificar que puedas seguir navegando. Repite ambos casos en la URL HTTPS de la demo.

## 📚 Documentación Técnica y Referencias

Los documentos y especificaciones aprobados por los frentes de Física, Matemática y Ciencias de la Computación se encuentran disponibles en:
* [Plan Maestro de AgroPhasor](docs/PLAN_MAESTRO_AGROPHASOR.md)
* [Tareas de CC en Linear](docs/referencias/AgroPhasor_Tareas_CC_Linear.md)
* [Guía Maestra de APIs y Datos de la NASA](docs/referencias/GUIA_APIS_Y_DATOS_NASA.md)
