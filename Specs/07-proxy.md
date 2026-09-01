# 07 — Proxy (Caddy del proveedor)

El proxy inverso está gestionado por el proveedor del hosting y termina
TLS antes de pasar el tráfico a `sapi-api.service` (`0.0.0.0:8000`).
Este doc recoge los snippets de configuración que aplican al servidor.

## Subida de PDFs de hasta 300 MB

Para aceptar `POST /api/boletines/upload` con archivos de hasta
`MAX_UPLOAD_MB=300` hay que subir el tamaño del cuerpo y los timeouts
en el proxy. Sin esto el navegador recibe 413/504 antes de que
`file.read()` llegue a la API.

### Snippet para Caddy (`Caddyfile` o equivalente del proveedor)

```caddy
marcas.solutechve.net {
    reverse_proxy 127.0.0.1:8000 {
        # 300 MB en MB / GB (Caddy acepta unidades).
        max_size 300MB

        # Subir timeouts: extracción pdfplumber sobre un PDF de 1000+
        # páginas puede tardar minutos. Caddy por defecto es 30s.
        transport http {
            dial_timeout 30s
            response_header_timeout 600s
            read_timeout 600s
            write_timeout 600s
        }

        # WebSocket del progreso de upload.
        @ws path /api/boletines/ws/*
        reverse_proxy @ws 127.0.0.1:8000
    }
}
```

### Equivalentes si el proveedor usa otro proxy

| Proxy | `client_max_body_size` / equivalente | Timeout relevante |
|---|---|---|
| nginx | `client_max_body_size 300m;` | `proxy_read_timeout 600s;` |
| Apache | `LimitRequestBody 314572800` | `ProxyTimeout 600` |
| HAProxy | `tune.http.max-request 300m` | `timeout server 600s` |

## Despliegue del snippet

Este repo no incluye `Caddyfile` (la config vive en el panel del
proveedor). Para aplicar los cambios:

1. Abrir el panel del proveedor → reverse proxy de
   `marcas.solutechve.net`.
2. Pegar/ajustar el snippet de arriba con `max_size 300MB` y
   `read_timeout 600s`.
3. Guardar y verificar:

   ```bash
   curl -sf -o /dev/null -w "%{http_code}\n" \
       https://marcas.solutechve.net/api/health
   ```

4. Probar subida con un PDF de ~250 MB; el dashboard debe mostrar
   `Subiendo…` durante el progreso del WebSocket.

## Rollback

Si algo falla tras aplicar los valores, basta con volver al panel del
proveedor y reducir `max_size` a `50MB` y los timeouts a los originales
(30 s por defecto).
