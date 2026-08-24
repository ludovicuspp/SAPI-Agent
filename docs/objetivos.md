# Objetivos del programa

## Resultados esperados (el impacto)

- **Eficiencia operativa**: reducir el tiempo de procesamiento del
  boletín oficial de días de revisión manual a menos de 15 minutos.
- **Cero omisiones**: lograr una cobertura del 100 % de los datos
  procesados, minimizando el alto riesgo de omitir marcas similares
  dentro de los estrictos plazos legales de oposición.
- **Alertas tempranas**: generar notificaciones automáticas de
  posibles conflictos en las primeras 24 horas tras la publicación
  del documento.
- **Valor comercial**: transformar un archivo PDF estático e inerte
  en un verdadero activo de inteligencia de mercado.

## Requisitos funcionales (el mecanismo)

- **Ingesta multiformato**: extraer de forma automatizada el texto
  de los PDFs del SAPI, superando sus maquetaciones inconsistentes
  o páginas escaneadas.
- **Estructuración estricta**: convertir la información desordenada
  en esquemas limpios y normalizados (expediente, marca, clase de
  Niza, titular, país de origen y estatus).
- **Motor de similitud**: aplicar un algoritmo de comparación
  fonética y semántica entre las nuevas solicitudes del boletín y
  tu lista privada de marcas bajo vigilancia.
- **Sistema de notificaciones**: avisar de forma inmediata mediante
  alertas cuando se detecte un movimiento estratégico o una
  coincidencia de riesgo.
- **Dashboard interactivo**: proveer una interfaz visual adaptada
  para la gestión multicliente, vigilancia e inteligencia de mercado.

## Notas operativas

- Los PDFs de los boletines los comparten los usuarios del sistema;
  no se scrappean de `sapi.gob.ve`.
- WEBPI requiere login + reCAPTCHA v3; no se automatiza. El
  seguimiento de expedientes propios se nutre de los boletines
  subidos.
- WEBPI horario: 8:00 AM – 11:30 PM hora Venezuela.
