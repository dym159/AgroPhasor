# Rotaciones en la interfaz

Con un terreno seleccionado, el panel espera a que el usuario elija una
estrategia, ajuste una perilla o marque un cultivo. Luego consulta
`POST /api/v1/parcelas/rotaciones` con el perfil de referencia y muestra la
secuencia sugerida de tres periodos por defecto, ajustable hasta seis. Toma la
primera fecha del calendario y el backend identifica la región de la parcela. Con
un solo cultivo marcado, lo fija al inicio y busca un compañero. Con varios,
busca entre los marcados. Sin selección, usa el catálogo disponible.

Si el backend no identifica un departamento, el panel pide elegirlo antes de
mostrar una combinación. Las variedades con cobertura regional documentada
solo participan en sus regiones registradas.

Las estrategias actualizan las perillas del tablero. Con un resultado
disponible, cambiar los pesos selecciona otra secuencia localmente. Cambiar
el terreno, los cultivos o el horizonte vuelve a consultar al motor.

La sugerencia usa clima histórico de NASA POWER. El suelo, el manejo y los
datos económicos del catálogo son de referencia. El contrato detallado sigue
disponible para integraciones con datos propios.

Pruebas de interfaz: `npm test`.
