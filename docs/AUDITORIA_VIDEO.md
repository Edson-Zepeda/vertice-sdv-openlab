# Auditoría científica y audiovisual del video SDV

El MP4 final pasó los 20 controles técnicos de `evidence/video_audit/verification.json`. La revisión separa exactitud de datos, calidad del plan visual y funcionamiento del archivo exportado. El estado previo a exportación quedó guardado como `pending` en `pre_export_status.json`, sin aprobar controles antes de que existiera el video.

## Fuentes y procedimiento

Se revisaron el guion, las nueve previsualizaciones y la composición de `scripts/build_film.py`, contrastándolos con `web/data/examples.json`, `tests/independent_oracle.py`, `evidence/verification/benchmark.json` y el contrato del algoritmo. El oráculo usa Bellman–Ford con enteros en microunidades y no importa el solucionador entregado. El video vuelve a ejecutar ambos algoritmos sobre los mismos ejemplos y verifica igualdad del costo mínimo.

Se conservaron el constructor, el plan y las nueve imágenes anteriores a los cambios en `evidence/video_audit/before/`. El diagnóstico `plan_before.json` compara tres muestras del contenido por escena, excluyendo título, subtítulos, pie y barra de progreso; `plan_final.json` repite ese diagnóstico sobre el plan corregido. Las tres muestras permiten detectar paneles inmóviles en esos instantes, sin medir por sí solas fluidez ni calidad audiovisual.

## Hallazgos y correcciones

| Hallazgo | Por qué afectaba la evaluación | Cambio y comprobación |
|---|---|---|
| VID-01 · P2 · Consultas implícitas | El costo 0.25 del panel de ciclo cero podía interpretarse como A→E, aunque la consulta real era A→D. | Cada panel muestra origen y destino. A→D cuesta 0.25; A→E no se presenta como ese resultado. |
| VID-02 · P2 · Dirección no representada | La voz describía invertir un recorrido dirigido mientras los tres grafos visibles eran no dirigidos. | Durante esa frase aparece el ejemplo dirigido y la consulta D→A sin ruta. Se revisó el instante local 11.898 s; las flechas están presentes. `direction_final_plan.png` conserva la prueba visual. |
| VID-03 · P2 · Equivalencia excesiva del oráculo | Un signo igual entre algoritmos y referencias a eventos podían implicar que Bellman–Ford reproduce la traza de Dijkstra. | El signo se limita a COSTO; la voz distingue costo contra oráculo de conexiones y traza contra invariantes. Cambian cinco consultas reales, incluido un caso sin ruta. |
| VID-04 · P2 · Movimiento insuficiente del contenido | Cuatro escenas tenían el mismo contenido en las muestras al 25 %, 50 % y 75 %. Solo cambiaban elementos periféricos. | Clases con foco secuencial y flujo; decimales con foco y contribuciones proporcionales; oráculo con consultas sucesivas. El plan final mantiene estables el total decimal tras concluir la suma narrada y el rendimiento tras su entrada animada. La gráfica permite comparar siete filas sin movimiento continuo. |
| VID-05 · P2 · Subtítulos superpuestos | Se encontraron 29 solapamientos temporales. El texto quemado elegía una línea, pero un reproductor VTT podía mostrar dos. | Cada final se recorta antes de la siguiente entrada. El plan final tiene cero solapamientos; se restaura además la puntuación del guion. |
| VID-06 · P2 · Procedencia incompleta | Los hashes no incluían la captura del estudio, las fuentes ni los audios usados para componer el video. | El plan registra 21 archivos: captura, dos fuentes, nueve audios y nueve metadatos de voz. Todos existían y coincidían al revisar el plan final. |
| VID-07 · P2 · Marcador tapa información | En el instante 11.898 s, el marcador animado borraba las letras C y B; en la previsualización de la escena 6 invadía el peso 0.25. | Se corrigió el orden de dibujo: conexiones, marcador, cajas de peso y nodos. Se compararon `direction_after.png` y `direction_final_plan.png` en el mismo instante. Letras y costos permanecen legibles. |
| VID-08 · P2 · Foco desincronizado con la clase explicada | El foco cambiaba por cuartos de duración: cuando la voz decía Nodo a 5.930 s ya estaba resaltado Edge; al decir solucionador a 14.766 s seguía resaltado Graph hasta 17.575 s. | Corregido con las palabras reales: Node 5.930 s, Edge 8.810 s, Graph 11.506 s y la frase «El solucionador» 14.582 s. Se revisaron imágenes a 6.3 y 15.5 s. `focus_timing_before.json`, `focus_timing_after.json` y capturas conservan el contraste. |
| VID-09 · P2 · Foco decimal llega después de la voz | El primer valor seguía resaltado hasta 7.3 s, aunque la voz decía dos décimos a 1.507 s y tres décimos a 2.965 s. | Corregido con focos a 0.649, 1.507 y 2.965 s. Se verificaron las imágenes a 1.65 y 3.15 s; el total permanece resaltado después de la suma narrada. |

El ajuste geométrico del ejemplo de costo cero evita que sus etiquetas se crucen sin modificar extremos ni pesos. Las dos etiquetas de grafos de 500 nodos y 4000 conexiones se distinguen por su tipo y el número de conexiones visible; no se confunden nodos con conexiones.

## Exactitud de los mensajes

- El ejemplo principal S→T devuelve 11 y el recorrido S→B→D→E→T: 2 + 4 + 2 + 3. La mejora didáctica de A pasa de 4 a 3 mediante S→B→A.
- El ciclo cero A→D devuelve 0.25, el empate A→D devuelve 2 y el destino aislado devuelve `no_path`. El grafo dirigido no tiene camino D→A.
- El ejemplo decimal procede de la prueba `decimal_exact`: 0.1 + 0.2 = 0.3. Las franjas de contribución representan aproximadamente un tercio y dos tercios; no son mediciones empíricas.
- Las distancias de la frontera se rotulan tentativas; asentar un nodo convierte su distancia en definitiva. Se explica que una entrada antigua de la cola puede descartarse y que visitar una conexión no implica mejorarla.
- El oráculo compara costos, incluida la ausencia de ruta. Las invariantes comprueban continuidad y suma de la ruta, asentamiento, relajaciones y frontera. Ningún número de pruebas se presenta como demostración universal.
- La gráfica usa las siete variantes **con traza**, mediana de nueve repeticiones, y separa solucionador de JSON→JSON. Para el grafo dirigido de 500 nodos y 4000 conexiones, los datos guardados son 17.6713 ms y 139.7735 ms; la etiqueta visible de JSON redondea a 139.8 ms. Son resultados de CPython 3.11 en una computadora, sin garantía de latencia en navegador o vehículo.

## Verificación reproducible del MP4

`python scripts/verify_film.py` requiere las herramientas opcionales del video: Pillow, FFmpeg y FFprobe. Usa los archivos locales ya generados y no sintetiza voz ni realiza peticiones de red. La salida es 0 cuando pasan las comprobaciones técnicas, 1 ante una falla y 2 si falta el MP4. Los resultados detallados se guardan aunque falle una comprobación.

El verificador comprueba resolución 1920×1080, H.264, 30 fps, formato de color compatible, decodificación y cantidad total de fotogramas, audio AAC, duración, nueve capítulos incrustados, `moov` antes de `mdat` para inicio progresivo y la correspondencia de los capítulos de la web. Compara cada subtítulo VTT con el plan usado para quemar el texto y comprueba sus límites temporales; contrasta el texto de voz y subtítulos con el guion.

Además calcula sonoridad del audio exportado, exige contenido audible y ausencia de pico superior a 0 dBTP, valida hashes de fuentes y activos antes y después de la revisión y verifica el hash del MP4 contra la evidencia de exportación. Extrae dieciséis fotogramas del archivo comprimido: nueve escenas, dirección inversa, oráculo sin ruta, fotograma final y los cuatro focos corregidos. Los compara con el renderer determinista en los mismos instantes, tolerando una diferencia media RGB de hasta 6/255 global y en la explicación, y 3/255 en título y subtítulos. Contrasta además los siete instantes de foco con los metadatos de palabras pronunciadas. El mosaico `contact-sheet.jpg` se compone exclusivamente con esos fotogramas decodificados.

El propio verificador recibió revisión independiente. El primer criterio de error global podía aceptar un título o subtítulo borrado, porque esas letras ocupan una proporción pequeña del fotograma. Al evaluar por separado título y subtítulos, los 18 borrados deliberados sobre las nueve escenas produjeron errores regionales de 11.057–25.249 y 7.666–10.612, respectivamente; todos superan el límite 3. Esa prueba se hizo en memoria, sin alterar el MP4, y se reproduce con `scripts/probe_film_pixels.py`; sus datos y hashes están en `verifier_image_mutations.json`. En los fotogramas comprimidos correctos, los errores regionales máximos fueron 1.659 para título y 1.892 para subtítulos; el criterio aceptó la compresión real.

## Resultado del archivo final

- MP4 de 11,549,436 bytes; video de 209.966667 s y contenedor/audio de 210 s. La diferencia corresponde a un fotograma de duración de audio.
- 6,299 fotogramas decodificados, 1920×1080 a 30 fps, H.264 y audio AAC; nueve capítulos y 45 entradas VTT coherentes, sin solapamientos.
- Sonoridad integrada medida de −16.40 LUFS y pico verdadero de −1.37 dBTP. Son mediciones del audio exportado; no una afirmación de escucha humana.
- Dieciséis búsquedas temporales y comparaciones de imagen correctas; fuentes, activos y archivo final conservaron sus hashes durante la revisión.
- Se inspeccionaron visualmente el mosaico de dieciséis fotogramas y, a tamaño completo, traza, rendimiento, dirección inversa y foco del solucionador. Los resultados, consultas, flechas y focos corregidos permanecen legibles en esas muestras.

SHA-256 del MP4 revisado: `530f352a435eda2e056ff72b982da5534d046c457d4157942b3dad20537a3eaf`.

Estos controles acreditan el archivo examinado y las muestras indicadas. La escucha completa, comprensión de la narración y reproducción en cada dispositivo requieren revisión humana o del navegador por separado; no se infieren de FFprobe ni de las previsualizaciones. Una nueva edición del guion, datos, fuentes, captura o constructor exige regenerar el video y renovar esta evidencia.
