# Auditoría de entrega y reproducción

Esta auditoría inicial revisó instrucciones, dependencias de construcción, empaquetado y configuración de CI antes de publicar el ZIP final. Las pruebas del empaquetador usan archivos aislados y respuestas Git controladas; la ejecución de la aplicación usa una copia real del proyecto en una ruta con espacios y acentos. La verificación del ZIP de la versión se registra por separado.

## Problemas reproducidos y cambios

| Prioridad | Reproducción anterior | Corrección |
|---|---|---|
| P1 · Sobrescritura de fuentes | Indicar `--output source/README.md` terminaba con éxito y reemplazaba el README por un ZIP. | Se rechaza toda salida dentro de la carpeta fuente y se exige extensión `.zip`, antes de escribir. |
| P2 · Nombres acentuados | `--output "Entrega Vértice.zip"` creaba el ZIP y después fallaba con `UnicodeEncodeError` al escribir el checksum como ASCII. | Checksum y recibo se escriben en UTF-8. Dos salidas con nombres distintos conservan idénticos bytes del ZIP. |
| P2 · Verificador dependía de temporales | En la copia sin `media/render`, el verificador fallaba por ausencia de `film-plan.json`, aunque el MP4 y su evidencia estaban incluidos. | Se usa el plan completo de `evidence/video.json` cuando no existe un plan local. Una ruta `--plan` explícita inexistente sigue produciendo un error. |
| P2 · Construcción sin instrucciones completas | El README no documentaba FFmpeg/FFprobe, Poppler, uso de dependencias opcionales ni el proceso de empaquetado. | Se añadieron comandos, requisitos, distinción entre aplicación y herramientas de autoría, y referencias al PDF, video y guía de defensa. |

Los resultados anteriores se conservan en `evidence/delivery/package_before.json` y `clean_snapshot_video_before.json`; las fuentes exactas anteriores están en `evidence/delivery/before/`.

El empaquetador valida además licencias requeridas, hashes de dependencias, igualdad del núcleo web y las dos copias del PDF. Rechaza rutas fuera del árbol, nombres ambiguos en Windows, colisiones por mayúsculas, el nombre reservado del manifiesto y temporales o archivos privados conocidos. No se afirma que esos filtros detecten cualquier secreto posible.

La creación y comprobación se realizan en archivos temporales del directorio de destino. Una falla de comprobación conserva el ZIP anterior; solo después se reemplaza el archivo. Cada reemplazo es atómico, pero el ZIP y sus dos archivos auxiliares no constituyen una transacción indivisible del sistema de archivos: sus hashes permiten detectar una interrupción entre reemplazos.

## Evidencia obtenida

- **9 pruebas del empaquetador aprobadas** en CPython 3.10.11, 3.11.9 y 3.14.7. Cubren integridad, reproducibilidad, salida acentuada, conservación del origen, interrupción, licencias, dependencias, copia web, estado Git y nombres peligrosos. Son nueve métodos, no 27 escenarios diferentes. Datos: `package_after.json` y `package_version_matrix.json`.
- **11 comandos comprobados** sobre 88 archivos reales copiados a una carpeta con espacios y acentos, sin `.git`, entornos de desarrollo ni `media/render`. Funcionaron el arranque sin paquetes Python externos, validación y resolución desde CLI, comprobación/sincronización de la copia web desde otra carpeta, ayuda del benchmark, cola JavaScript, lanzador Windows y los errores previstos. Datos: `clean_snapshot.json`.
- En esa copia, el verificador corregido aprobó los **20 controles del MP4 usando la evidencia incluida** como plan. Es una nueva comprobación de portabilidad del mismo archivo, no un nuevo video. Datos: `clean_snapshot_video.json`.
- Se creó un entorno Python 3.11 aislado y se instalaron las cinco versiones directas de `requirements-build.txt` y sus dependencias resueltas: 18 paquetes. `pip check` no encontró conflictos. Se regeneraron el PDF de diez páginas y las nueve previsualizaciones del video usando las voces incluidas; no se volvió a sintetizar voz ni a renderizar otro MP4. Datos: `build_reproduction.json`.

**Versión observada:** el snapshot y la construcción anteriores se realizaron antes del cambio posterior en el preanálisis JSON y en el servidor HTTP. Sus hashes se conservan como evidencia de esa versión; no acreditan automáticamente el núcleo o servidor posteriores. Las pruebas del empaquetador acreditan sus propios archivos registrados. El paquete final, una vez construido, necesita su comprobación de extracción e integridad.

## Comprobación del commit publicado

La [auditoría del snapshot actual](../evidence/delivery/current_snapshot.json) comprobó el commit público `407cc98f4fded8b00daa7e16c50ebc52dc9b7a5e`, que ya incluye las correcciones del importador y del servidor. Sus **37 controles aprobaron**: 392 archivos íntegros, dos ZIP idénticos de 42,382,838 bytes, extracción en una ruta con espacios y acentos, arranque sin paquetes Python externos, consulta de costo 11, PDF exacto y respuesta HTTP 206 correcta para el MP4. El servidor de la prueba usó un puerto propio y se cerró al terminar.

SHA-256 de ambos ZIP de revisión: `1c58e24b071b519e15a1724ee0175ad77e2237b51798d6fe799da08c7e67f32a`. Esos archivos identifican ese commit, no anticipan el ZIP final de la versión.

La primera ejecución del comprobador esperaba un campo `ok` inexistente en la respuesta de salud. Se corrigió la aserción para comprobar `project`, `engine` y los cuatro hashes definidos por la API. El [resultado inicial](../evidence/delivery/current_snapshot_before_health_assertion.json) se conserva; la aplicación no necesitó cambios.

## Verificar el ZIP de la versión

El [verificador de extracción](../scripts/verify_extracted_release.py) lee el ZIP real y obtiene los hashes del manifiesto incluido. Comprueba todos los archivos, ejecuta la terminal sin paquetes externos y arranca el servidor extraído en un puerto propio. Contrasta una consulta conocida, el PDF y un rango del video; finalmente cierra su proceso y elimina únicamente su carpeta temporal. Su [revisión independiente](../evidence/delivery/release_independent_review.json) conserva una ejecución sobre el paquete anterior y ocho comprobaciones negativas. Esa ejecución anterior no acredita por anticipado el ZIP final.

```sh
python -S -B scripts/verify_extracted_release.py ../VerticeSDV_Proyecto.zip --output ../VerticeSDV_EntregaExtraida.json
python scripts/verify_release.py ../VerticeSDV_Proyecto.zip --output ../VerticeSDV_Verificacion.json
```

El segundo comprobador verifica, sin autenticación, que la etiqueta corresponde al commit del ZIP y que la descarga es idéntica. Los registros finales se guardan fuera del repositorio para conservar limpia la revisión contenida en la entrega. Los archivos auxiliares publicados también deben compararse con el checksum y el recibo locales.

## Versiones y CI

Las cinco versiones fijadas existen en PyPI y admiten Python 3.10 según sus metadatos. Se conservaron sus URLs, requisitos y hashes en `build_dependencies.json`; la instalación real queda identificada por archivos descargados y versiones en `build_reproduction.json`. Los pins directos no congelan las dependencias transitivas: se documenta esa limitación en el README.

Se verificó la existencia del código de las tres acciones fijadas por commit en el flujo: [checkout](https://raw.githubusercontent.com/actions/checkout/3d3c42e5aac5ba805825da76410c181273ba90b1/action.yml), [setup-python](https://raw.githubusercontent.com/actions/setup-python/5fda3b95a4ea91299a34e894583c3862153e4b97/action.yml) y [setup-node](https://raw.githubusercontent.com/actions/setup-node/820762786026740c76f36085b0efc47a31fe5020/action.yml). La matriz declarada cubre Python 3.10 y 3.14 en Ubuntu, y 3.12 en Windows; el trabajo JavaScript usa Node.js 24. El comando de descubrimiento incluye automáticamente las nuevas pruebas del empaquetador. No se ejecutó GitHub Actions durante esta auditoría.

El ZIP fija orden, fecha del commit, permisos y sistema creador. Su manifiesto registra zlib porque cambiar el compresor puede cambiar los bytes comprimidos. No se atribuye reproducibilidad binaria universal al PDF, a la voz sintetizada ni a entornos que no fueron comprobados.
