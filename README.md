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

## 📚 Documentación Técnica y Referencias

Los documentos y especificaciones aprobados por los frentes de Física, Matemática y Ciencias de la Computación se encuentran disponibles en:
* [Plan Maestro de AgroPhasor](docs/PLAN_MAESTRO_AGROPHASOR.md)
* [Tareas de CC en Linear](docs/referencias/AgroPhasor_Tareas_CC_Linear.md)
* [Guía Maestra de APIs y Datos de la NASA](docs/referencias/GUIA_APIS_Y_DATOS_NASA.md)
