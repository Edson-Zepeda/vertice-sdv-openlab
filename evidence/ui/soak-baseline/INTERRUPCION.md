# Ensayo de referencia interrumpido

El coordinador detuvo esta ejecución a los 25,83 minutos para corregir hallazgos nuevos de contrato y experiencia de usuario antes de ensayar la versión final. Hubo 898 acciones y 111 cálculos reales. **No se completaron los 75 minutos previstos.**

Se cerró únicamente el Chrome aislado perteneciente a `scripts/soak_ui.cjs`, identificado por PID 35832, padre Node 3700 y perfil temporal de Playwright. El script registró el cierre como `Target page, context or browser has been closed`; ese registro se conserva íntegro en `report.json` y no representa un fallo espontáneo de la aplicación.

Se conservan los hashes iniciales/finales, los seis controles de memoria y el registro de actividad originales. Los cambios posteriores incluyen etiquetas vacías y Unicode, preservación de espacios, el límite de importación de 2 MiB, el foco del editor y espacio reservado para metadatos. La ejecución final se registrará por separado en `evidence/ui/soak`.
