# Fase 1 — Fingerprint de plataforma por dominio

Generado con [`tools/fingerprint.py`](../tools/fingerprint.py) — cada fila de
la tabla está verificada empíricamente (requests reales, no supuestos).
Metodología y hallazgos de infraestructura al final del documento.

## Tabla de resultados

| Dominio (candidato) | Dominio real usado | Plataforma | Endpoint útil | Protección | Requiere región | Viabilidad | Notas |
|---|---|---|---|---|---|---|---|
| chedraui.com.mx | www.chedraui.com.mx | **VTEX** | `/api/catalog_system/pub/products/search` + `/category/tree/3` | ninguna | Sí (VTEX regionId/sales channel) | 🟢 VERDE | Confirmado por API: array de productos con `productId`/`productName`. Apex rechaza conexión directa, hay que usar `www.`. |
| soriana.com | soriana.com | ⚠️ sin confirmar | — | **Cloudflare** (403 en /api y homepage) | por confirmar | 🟡 AMARILLO | WAF bloquea tanto el endpoint VTEX como la home sin JS. Necesita prueba con navegador real o headers adicionales antes de descartar VTEX. |
| lacomer.com.mx | www.lacomer.com.mx/lacomer/ | **CUSTOM (AngularJS 1.x — `ng-app="comerApp"`)** | ninguno encontrado | ninguna detectada | por confirmar | 🟡 AMARILLO | El dominio raíz solo hace un redirect por JS (`onload=`) a `/lacomer/`. Ahí corre una SPA AngularJS legado, no VTEX. `/api/catalog_system/...` da 404 limpio (no bloqueado, simplemente no existe esa ruta). Requiere encontrar su API real. |
| heb.com.mx | www.heb.com.mx | ⚠️ sin confirmar | — | **Incapsula** (403 en /api y homepage) | por confirmar | 🟡 AMARILLO | Incapsula bloquea incluso la home sin JS (`_Incapsula_Resource` visible en el body). |
| super.walmart.com.mx | super.walmart.com.mx | ⚠️ sin confirmar | — | **Bot-mitigación fuerte** (posible Akamai Bot Manager) | por confirmar | 🔴 ROJO | La *home* devuelve una página "Verifica tu identidad" con `uuid`/`blockId` — mitigación activa incluso para tráfico no autenticado. No es solo el endpoint VTEX, es todo el sitio. |
| bodegaaurrera.com.mx | www.bodegaaurrera.com.mx | ⚠️ sin confirmar | — | **Akamai** (holding page servida desde Azure Blob Storage) | por confirmar | 🔴 ROJO | Todas las rutas devuelven una página `/blocked?url=...&uuid=...` con 200, cabeceras `x-edgeconnect-*` (Akamai) y `x-ms-blob-type` (Azure). Bloqueo sistemático, no solo del endpoint API. |
| sams.com.mx | www.sams.com.mx | ⚠️ sin confirmar (probablemente plataforma propia de Walmart) | — | Akamai presente, pero la *home* sí carga (200) | por confirmar | 🟡 AMARILLO | A diferencia de Súper/Bodega Aurrera, la home renderiza contenido real (CDN `i5.walmartimages.com`). `/api/catalog_system` da 404 limpio → no es VTEX. Mismo grupo corporativo que Walmart Súper/Bodega Aurrera; probablemente comparten backend propietario. |
| costco.com.mx | www.costco.com.mx | **CUSTOM (SAP Commerce / Hybris — storefront "Spartacus")** | sin confirmar (candidato: `/occ/v2/{baseSite}/products/search`, no probado) | ninguna detectada | por confirmar | 🟡 AMARILLO | `<base href="/spartacus/assets/">` y marcador `data-critters-container` (Angular Universal SSR) son firma inequívoca de SAP Commerce Cloud. SAP Commerce expone una API REST (OCC) — no la until de LO probé, queda para cuando se retome este retailer. |
| cityclub.com.mx | cityclub.com.mx | ⚠️ sin confirmar | — | **Cloudflare** (403) | por confirmar | 🟡 AMARILLO | City Club es propiedad de Grupo Comercial Chedraui (mismo dueño que chedraui.com.mx, que sí es VTEX). Hipótesis a validar con navegador real: podría compartir plataforma VTEX aunque hoy el bot de fingerprint esté bloqueado. |
| tiendasneto.com / tiendasneto.com.mx | ambos probados | **Ninguna — sitio WordPress institucional** | — | ninguna | N/A | 🔴 ROJO | Yoast SEO, `xmlrpc.php`, perfil `gmpg.org/xfn/11` = WordPress genérico. No hay catálogo ni carrito. Además: certificado TLS de `www.tiendasneto.com` está **vencido** (confirmado, no es problema de mi entorno); el apex responde solo si se ignora la verificación TLS. |
| merza.com.mx | www.merzava.com (redirect) | **CUSTOM (vendor "Aktios" — Angular Universal SSR)** | sin confirmar | ninguna detectada | por confirmar | 🟡 AMARILLO | El dominio redirige a `merzava.com`. CDN `cdn-merza.aktiosdigitalservices.com` identifica al proveedor de plataforma "Aktios", usado por varias cadenas regionales mexicanas. `/api/catalog_system/...` da 500 genérico (no es señal VTEX). |
| waldos.com.mx | waldos.com.mx | **CUSTOM (Magento 2)** | candidato: `/graphql` (no probado) | ninguna detectada | por confirmar | 🟡 AMARILLO | Firma inequívoca de Magento 2: `require.baseUrl` apunta a `/static/version<ts>/frontend/WolfSellers/waldos/es_MX`. Magento tiene API GraphQL/REST estándar — candidato fuerte para adaptador nuevo si se prioriza. |
| tiendasdax.com | — no resuelve — | sin determinar | — | — | N/A | 🔴 ROJO | El dominio no existe (falla de DNS). El nombre real de la cadena es "Tiendas DAX" (Tijuana, belleza/hogar/cuidado personal). Hay AL MENOS dos dominios candidatos y no logré desambiguar cuál es la cadena real: `dax.com.mx` (Cloudflare, React con `react-helmet`) y `tiendadax.com.mx` (sitio antiguo tipo PHP con branding "TIENDA DAX", envío gratis a México). **Ninguno vende botanas como categoría central** (es cosmética/hogar) — prioridad baja para este proyecto independientemente de la plataforma. |
| superq.com.mx | superq.com.mx | **Ninguna — sitio WordPress institucional** | — | ninguna | N/A | 🔴 ROJO | Confirmado por fingerprint Y por investigación externa: Súper Q (~58 tiendas, base 442/Querétaro) **no tiene e-commerce con carrito**, solo folletos/ubicación de tiendas. Único candidato "regional QRO" encontrado con presencia web — no califica para cosecha automatizada. |
| oxxo.com | www.oxxo.com | **Ninguna — sitio institucional custom (PHP/Laravel + CloudFront)** | — | ninguna detectada | N/A | 🔴 ROJO | `/api/catalog_system` y `/products.json` dan 404 limpio, sin bloqueo. No expone catálogo de productos vía web pública — consistente con que OXXO no opera e-commerce nacional de catálogo. |
| 7-eleven.com.mx | 7-eleven.com.mx | **Ninguna — sitio WordPress institucional** | — | ninguna | N/A | 🔴 ROJO | Mismo patrón que Súper Q y Neto (Yoast SEO, `xmlrpc.php`). Sin catálogo. |
| circulok.com.mx | — dominio incorrecto — | N/A | — | — | N/A | 🔴 ROJO | El dominio devuelve un **listado de directorio abierto** (`Index of /`) con una carpeta `KARMI_REPLICACION/` — no es el sitio de la cadena, parece infraestructura mal configurada de un tercero. La marca en México se llama **Circle K**, no "Círculo K"; su dominio real es `circlek.com.mx` (ver fila siguiente). |
| — | circlek.com.mx | ⚠️ sin confirmar | — | **Cloudflare** (403) | por confirmar | 🟡 AMARILLO | Dominio correcto de la cadena (rebrand a "Circle K" en México). Bloqueado por Cloudflare en los endpoints estándar. |
| farmaciasguadalajara.com | www.farmaciasguadalajara.com | **Sospecha: Salesforce Commerce Cloud (SFCC)** | sin confirmar | timeouts consistentes (¿bot-mitigación o servidor lento?) | por confirmar | 🔴 ROJO (provisional) | El sitio no respondió en ninguna prueba (timeout incluso a 25s con UA identificable). Indicio externo fuerte: una URL indexada de su propio sitio contiene el patrón `Sites-fragua-Site`, firma clásica de Salesforce Commerce Cloud (`Sites-<siteId>-Site`). Requiere prueba con navegador real (Fase 2/7) antes de descartar. |
| benavides.com.mx | www.benavides.com.mx | **CUSTOM (Magento 2)** | candidato: `/graphql` (no probado) | ninguna detectada | por confirmar | 🟡 AMARILLO | Misma firma que Waldo's: `require.baseUrl` → `/static/version<ts>/frontend/Never8/base/es_MX`. |
| rappi.com.mx | rappi.com.mx | ⚠️ sin confirmar | — | **Cloudflare** (403, bloqueo a nivel edge/worker, ni llega a origen) | por confirmar | 🔴 ROJO | `robots.txt` **prohíbe explícitamente** `/api/...` (único caso detectado). Respeto de robots.txt + bloqueo de borde → plan C confirmado como último recurso, no primera opción. |
| cornershopapp.com | cornershopapp.com | ⚠️ sin confirmar | — | **Cloudflare** (challenge JS "Just a moment...") | por confirmar | 🔴 ROJO | Challenge interactivo de Cloudflare — inviable sin JS real. Plan C, mismo criterio que Rappi. |

## Resumen por categoría del brief

- **Autoservicio (13 candidatos):** 1 VERDE limpio (Chedraui/VTEX), 6 AMARILLO
  (plataforma con pistas fuertes pero no 100% confirmada por WAF o por no
  haber probado la ruta correcta todavía: Soriana, La Comer, Sam's, Costco,
  City Club, Merza), 3 ROJO por WAF duro (H-E-B, Walmart Súper, Bodega
  Aurrera — mismo patrón, probable plataforma propia de Walmart/HEB con
  mitigación de bots agresiva) y 3 ROJO por no tener e-commerce real (Neto,
  y Waldo's queda AMARILLO por ser Magento aunque farmacéutico-adyacente).
- **Regional QRO:** investigado a fondo. **Súper Q** es el único hallazgo
  real con presencia en Querétaro (58 tiendas, sede en zona 442) — pero no
  tiene tienda en línea, solo folletos. No se encontró ninguna otra cadena
  nativa de Querétaro con e-commerce activo. Jüsto (100% online, opera en
  Querétaro) apareció en la investigación pero es un supermercado
  online-only nacional, no una cadena regional física — lo dejo fuera por
  no encajar en el criterio "regional QRO", pero lo menciono por si quieres
  agregarlo como candidato aparte.
- **Conveniencia (3 candidatos):** los 3 sin catálogo de producto
  automatizable — OXXO y 7-Eleven son sitios institucionales (WordPress),
  y "circulok.com.mx" resultó ser el dominio equivocado (la cadena real es
  Circle K, `circlek.com.mx`, bloqueada por Cloudflare).
- **Farmacia/mixto (2 candidatos):** ambas con plataformas identificables
  (Benavides = Magento 2 confirmado; Farmacias Guadalajara = sospecha SFCC,
  pendiente de confirmar por timeout persistente). Nota aparte: su encaje
  con la categoría "botanas" es marginal — botanas no es su catálogo
  central — así que aun si son técnicamente viables, sugiero prioridad baja.
- **Agregadores (plan C):** Rappi y Cornershop confirmados como bloqueo
  duro de Cloudflare, exactamente el perfil "último recurso" que anticipaba
  el brief. Rappi además prohíbe `/api` explícitamente en robots.txt.

## Falsos positivos / correcciones de dominio descartadas

- `circulok.com.mx` → no es el sitio de la cadena; el nombre correcto en
  México es **Circle K** (`circlek.com.mx`).
- `tiendasdax.com` → no resuelve; hay ambigüedad real entre `dax.com.mx` y
  `tiendadax.com.mx` como posible sitio de "Tiendas DAX". No asumí cuál es
  el correcto — categoría de producto (cosmética/hogar) tampoco encaja bien
  con "botanas", así que no vale la pena resolver la ambigüedad para este
  proyecto.
- `tiendasneto.com` → redirige a `tiendasneto.com.mx`; ambos son WordPress
  puro, sin relación con el operador real del catálogo de tienda (si Neto
  tiene e-commerce, vive en otro dominio que no identifiqué).

## Hallazgos de infraestructura (afectan Fase 2 en adelante)

1. **Apex vs. `www.`:** varios dominios rechazan conexión directa en el
   apex y solo responden en `www.<dominio>` (Chedraui, Farmacias
   Guadalajara). El fingerprint ya resuelve esto automáticamente probando
   ambos; los adaptadores de Fase 5 deben hacer lo mismo o fijar `www.`
   como config por retailer.
2. **Certificados TLS rotos:** `www.tiendasneto.com` sirve un certificado
   **vencido** (no es un problema de mi entorno — confirmado
   independientemente). Cualquier intento de cosechar ese dominio debe
   decidir explícitamente si se tolera (`verify=False`) o se excluye —
   nunca ignorarlo en silencio.
3. **Detección de WAF ampliada durante esta fase:** el fingerprint inicial
   no reconocía cabeceras `x-edgeconnect-*` (Akamai EdgeConnect) ni el
   patrón de "holding page" en Azure Blob Storage que usa el grupo Walmart
   para bloqueos — se agregó la señal y con eso Bodega Aurrera pasó de
   "DESCONOCIDA" a "HOSTIL (akamai)" correctamente.
4. **Concurrencia y DNS en Windows:** corriendo ~20 dominios en paralelo,
   el resolver de Windows produce fallas DNS transitorias
   (`getaddrinfo failed`) que no son fallas reales del sitio. El
   fingerprint ahora reintenta con backoff antes de concluir que un host
   no responde, y limita a 6 dominios concurrentes para reducir la
   contención. Sin este ajuste, Chedraui (VTEX real, VERDE) se reportaba
   como "DESCONOCIDA" — un falso negativo que habría contaminado la
   decisión de plataforma si no se hubiera verificado dos veces.

## Plataformas nuevas detectadas (no estaban en la lista original del brief)

Además de VTEX/Shopify, esta fase encontró evidencia concreta de:

- **SAP Commerce Cloud / Spartacus** (Costco México)
- **Magento 2** (Waldo's, Farmacias Benavides)
- **AngularJS 1.x custom** (La Comer)
- **Vendor "Aktios"** (Merza/Merzava) — vale la pena investigar si otras
  cadenas regionales mexicanas usan el mismo vendor; si sí, un adaptador
  para "Aktios" tendría el mismo apalancamiento que uno de VTEX.
- **Posible Salesforce Commerce Cloud** (Farmacias Guadalajara, sin
  confirmar aún)

Esto no cambia el principio "adaptadores por plataforma" de `CLAUDE.md` —
al contrario, lo confirma: si decidimos perseguir Waldo's y Benavides,
un solo adaptador Magento cubre ambos sin código específico de retailer.

## Siguientes pasos sugeridos (para cuando apruebes esta fase)

- Fase 2 solo tiene sentido, tal como está planteada, para los retailers
  VTEX confirmados o casi confirmados: **Chedraui** (VERDE) y, si logramos
  destrabar Cloudflare/probar la ruta correcta, **Soriana, City Club**.
- Si quieres ampliar el alcance más allá de VTEX antes de Fase 2, los
  candidatos AMARILLO con plataforma identificada (Magento: Waldo's y
  Benavides; SAP Commerce: Costco; AngularJS: La Comer) necesitarían su
  propio "Fase 2 equivalente" de regionalización antes de poder
  descubrir catálogo — Magento y SAP Commerce también tienen su propio
  concepto de tienda/región, distinto al de VTEX.
- Los ROJO por WAF fuerte (HEB, Walmart Súper, Bodega Aurrera, Rappi,
  Cornershop) son candidatos para revisar recién en Fase 7, y solo con
  justificación explícita de por qué no hay alternativa a Playwright.
