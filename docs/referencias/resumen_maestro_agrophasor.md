# 🚀 Resumen Maestro: Arquitectura de AgroPhasor
**Objetivo:** Ganar el NASA Space Apps Challenge 2026 (Reto: *"Field Shift: Adapting Farms with NASA Data"*) proponiendo la solución definitiva a nivel global para la planificación de rotación de cultivos bajo estrés climático.

---

## 1. Núcleo Físico y Matemático (El Backend "Deep Tech")
A diferencia de las soluciones tradicionales basadas en estadística, AgroPhasor es un **Gemelo Digital Mecanicista** que modela la parcela como una máquina térmica usando sistemas dinámicos en $\mathbb{R}^4$.

*   **Ecuaciones Diferenciales Ordinarias (EDO):** Se modela el acoplamiento entre la Humedad del suelo ($W$) y la Temperatura de la planta ($T$).
*   **La Aproximación Adiabática:** Es el mayor "hack" computacional del proyecto. Dado que el agua ($W$) cambia lentamente y la temperatura ($T$) cambia rápido, se asume que $W$ está "congelada" durante el día. Esto linealiza el sistema caótico ($\gamma \cdot W \cdot T$) convirtiéndolo en osciladores armónicos acoplados. 
*   **Curvas de Lissajous:** La solución analítica de estos osciladores genera elipses. El **área de la elipse** representa la inercia térmica del ecosistema (la capacidad del suelo para enfriar a la planta mediante evapotranspiración antes del cierre estomático).
*   *Nota de Diseño:* Las curvas de Lissajous se mantienen **exclusivamente en el backend**. Son el motor matemático, pero se ocultan al usuario para evitar la fricción cognitiva.

## 2. El Motor Algorítmico (Optimización de Rotaciones)
El problema biológico de elegir qué sembrar mes a mes se transforma en un problema computacional de optimización de rutas espaciotemporales.

*   **Algoritmo de Búsqueda $A^*$:** Explora miles de permutaciones de rotación de cultivos. 
*   **Costo Heurístico:** Utiliza el área de la curva de Lissajous. Si un cultivo agota el agua, el área colapsa a una línea recta (estrés térmico/cierre estomático), y el $A^*$ descarta esa ruta (costo infinito).
*   **Malla Espacial (Autómatas Celulares):** Para no lidiar con Ecuaciones en Derivadas Parciales (EDP) lentas, el espacio se discretiza. **1 Píxel de NASA = 1 Celda (Nodo)**. Se corren miles de EDOs vectorizadas en paralelo usando NumPy. Esto permite micro-rotaciones adaptadas a la topografía (ladera vs. valle).

## 3. Forzamiento Climático y Datos de la NASA
El modelo rechaza el uso de promedios estadísticos simples y pronósticos meteorológicos limitados a 14 días.

*   **API NASA POWER:** Se extraen 20 años de historia agroclimatológica de la granja (radiación solar, temperatura).
*   **Generador Estocástico (Síntesis de Fourier):** Los datos no se usan para adivinar el futuro, sino para construir una función continua $f_{rad}(t)$. Se aplica una Transformada de Fourier para extraer el ciclo anual (ondas senoidales) y se le suma una Tendencia (cambio climático).
*   **Simulación de Montecarlo (Cisnes Negros):** Se añade "ruido blanco" matemático para simular años extremos (ej. El Niño o sequías). El algoritmo $A^*$ evalúa las rotaciones bajo múltiples futuros paralelos, garantizando supervivencia incluso ante climas inéditos.

## 4. Interfaz de Usuario y UX (Frontend)
El software traduce la complejidad de las derivadas parciales en una experiencia sensorial y visual instintiva para el agrónomo empírico.

*   **El Escudo Térmico:** El factor de amortiguamiento matemático ($\zeta$) se renderiza como un escudo de ciencia ficción sobre la planta. Un escudo grueso y azul indica alta inercia térmica; un escudo delgado, parpadeante y atravesado por rayos térmicos (rojos) indica colapso estomático inminente.
*   **El "Hover" Predictivo (Arrastrar y Soltar):** El usuario arrastra un cultivo sobre el mapa interactivo 4D. El sistema recalcula la física en milisegundos y muestra cómo reaccionarían los "Escudos Térmicos" del terreno antes de soltar la semilla.
*   **Traducción Sensorial (Háptica y Sonificación):** Para el trabajo de campo. El agrónomo siente en la línea de tiempo la resistencia del ecosistema a través de vibraciones en el móvil (suave = homeostasis; rasposo = estrés) y acordes armónicos vs. disonantes.

## 5. Hardware y Escalabilidad (El "Wow Factor" para la NASA)
Elementos creativos que separan a AgroPhasor de una simple aplicación web:

*   **El "Artemis Toggle":** Un interruptor que cambia los parámetros (gravedad, radiación LED, presión) para simular el Gemelo Digital en invernaderos lunares, demostrando universalidad matemática.
*   **Histéresis Termodinámica:** Modelado del "efecto memoria" del suelo. Si se seca demasiado, el daño es irreversible (deformación asimétrica), penalizando rotaciones comerciales destructivas.
*   **El Oráculo de Escritorio (Hardware Tangible):** Un cubo impreso en 3D con un ESP32 que palpita en el escritorio del agrónomo (luz verde/roja y golpeteos) avisando silenciosamente del estado termodinámico del campo.

## 6. La Tesis Competitiva (Por qué supera a las Corporaciones y ML)
*   **Física (Causalidad) vs. Machine Learning (Correlación):** Las empresas AgTech (FBN, Corteva, Agmatix) usan ML probabilístico basado en el principio de "estacionariedad" (el clima futuro será como el pasado). AgroPhasor usa Física Computacional (Ley de Enfriamiento de Newton, Conservación de Energía). Si ocurre un calor extremo inédito (50°C), el ML alucina por falta de datos; AgroPhasor calcula analíticamente el cierre estomático exacto.
*   **Predictivo vs. Reactivo:** Los ganadores anteriores de Space Apps usaban NDVI satelital, que muestra la planta en rojo cuando ya está biológicamente muerta. AgroPhasor predice la asfixia termodinámica *días antes* del daño celular visible.