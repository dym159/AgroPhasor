# Entorno local de Python

Ejecuta estos comandos en PowerShell desde la raíz del repositorio.
Usa un entorno virtual para que servidor y pruebas usen el mismo Python.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe server.py
```

Si el lanzador `py` no encuentra Python, usa la ruta del intérprete instalado
para crear el entorno. No es necesario activar el entorno: los comandos
anteriores seleccionan explícitamente su intérprete.

Abre `http://127.0.0.1:5173` y conserva la terminal del servidor abierta.
Los scripts de CI prefieren `.venv`. La suite usa pytest: unittest no ejecuta
todas las funciones de prueba. Los scripts exploratorios en scratch y las
dependencias descargadas en tmp no forman parte de la suite.

En esta sesión se preparó `.venv` con Python 3.13 y copias de las dependencias
ya disponibles localmente (numpy, shapely, pytest y dependencias transitivas),
sin descargar paquetes. Para instalar el conjunto completo, incluidos FastAPI,
Uvicorn y pyproj, utiliza requirements-dev.txt cuando dispongas de acceso a red.
