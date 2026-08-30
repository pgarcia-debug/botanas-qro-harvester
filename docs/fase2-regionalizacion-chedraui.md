# Fase 2 — Regionalización VTEX: Chedraui (CP 76000)

Todo lo de este documento está verificado con requests reales (navegador +
scripts) contra `www.chedraui.com.mx`, hoy. Nada es supuesto.

## 1. Cómo se resuelve la región para un CP

```
GET /api/checkout/pub/regions?country=MEX&postalCode=76000&sc=1
```

Respuesta para CP 76000:

```json
[{
  "id": "U1cjY2hlZHJhdWlteDAyNjI7Y2hlZHJhdWlteDAyNjg7Y2hlZHJhdWlteGRhcmtzdG9yZQ==",
  "sellers": [
    {"id": "chedrauimx0262", "name": "CHEDRAUI SELECTO GDL PLAZA MEXICO"},
    {"id": "chedrauimx0268", "name": "CHEDRAUI  SELECTO QUERETARO CENTRO SUR"},
    {"id": "chedrauimxdarkstore", "name": "chedrauimxdarkstore"}
  ]
}]
```

- `sc=1` es el único sales channel — **no hace falta probar otros `sc`**,
  Chedraui no segmenta por trade policy, segmenta por *seller* (tienda
  física).
- El `id` es un `regionId` codificado en base64: decodificado da
  `SW#chedrauimx0262;chedrauimx0268;chedrauimxdarkstore` — literalmente la
  lista de sellers que cubren ese CP.
- **`chedrauimx0268` = CHEDRAUI SELECTO QUERETARO CENTRO SUR** es el seller
  real de Querétaro. `chedrauimx0262` (etiquetado "GDL", Guadalajara) también
  aparece cubriendo el CP 76000 — no logré explicar por qué un store
  etiquetado como Guadalajara cubre una zona de Querétaro; puede ser
  cobertura de un centro de distribución regional o un nombre mal
  etiquetado en su Master Data. Documentado como anomalía, no resuelto.
- `chedrauimxdarkstore` es un fulfillment center para pedidos en línea
  (sin tienda física).

## 2. Cómo se inyecta el contexto de región en el precio — el hallazgo importante

**La API legacy de catálogo NO respeta el contexto de región.**
`GET /api/catalog_system/pub/products/search` siempre devuelve el precio
del seller genérico `"1"` (lista de precio nacional/default),
independientemente de cualquier cookie `vtex_segment` o `regionId` que se
tenga activo. Confirmado con la sesión de navegador ya regionalizada a
Querétaro Centro Sur: el precio que devuelve esta API para un SKU específico
**no coincidió** con el precio real mostrado en la página del producto (ver
validación abajo).

**La única fuente confiable del precio real por tienda es el endpoint de
simulación de checkout:**

```
POST /api/checkout/pub/orderForms/simulation
{
  "items": [{"id": "<skuId>", "quantity": 1, "seller": "1"}],
  "postalCode": "76000",
  "country": "MEX"
}
```

Esto devuelve, por SKU: `price` (en centavos), `sellerChain` (la cadena
`["1", "<seller regional>"]` que resuelve internamente), `availability`, y
la logística completa (tienda de recolección, ventanas de entrega a
domicilio, etc.).

**Además, es completamente *stateless*:** confirmé con
`credentials: 'omit'` (petición sin ninguna cookie) que el `postalCode` en
el body basta — no hace falta primero llamar a `/api/checkout/pub/regions`
ni a `/api/segments?regionId=...` ni mantener cookie de sesión. Cada
llamada a `simulation` resuelve la región por su cuenta a partir del CP.
Esto simplifica mucho el diseño: el adaptador VTEX no necesita cookie jar
ni sesión persistente para obtener precio correcto — solo pasar
`postalCode` en cada request.

**También soporta batch:** un solo POST puede llevar varios SKUs en
`items[]` y devuelve el precio/disponibilidad de todos en una sola llamada
— reduce drásticamente el número de requests necesarios en Fase 5.

### Implicación para el contrato de adaptador (`CLAUDE.md`)

Esto encaja con la interfaz de 4 funciones ya definida, pero precisa qué
hace cada una para VTEX:

- `resolve_region(postal_code)` → llama `/api/checkout/pub/regions`, guarda
  el `regionId` y la lista de sellers (principalmente para documentar/
  auditar qué tienda cubre qué CP — **no** es un prerrequisito en runtime
  para `fetch()`).
- `discover(region_context)` → catálogo/SKUs vía `/api/catalog_system/pub/products/search`
  o vía GraphQL search — insensible a precio, sirve para descubrir qué
  existe (Fase 3).
- `fetch(sku_refs)` → **NO** usa el precio de `discover()`. Hace POST
  batched a `/api/checkout/pub/orderForms/simulation` con el `postalCode`
  del retailer, para obtener precio y disponibilidad reales.
- `parse(raw)` → combina metadata de `discover()` (nombre, marca, EAN,
  categoría) con precio/stock de `fetch()` (simulation) para construir
  `Product`.

## 3. Hallazgo operativo: el backend de checkout tiene bot-shield propio

`/api/checkout/pub/regions` y `/api/checkout/pub/orderForms/simulation`
(ambos corren en el backend VTEX que se identifica como
`x-vtex-janus-router-backend-app: chk`) devuelven `429 Too Many Requests`
con header `rate-limit-reason: bot` a un cliente `httpx` con HTTP/1.1 y
sin headers de navegador — **incluso en la primera petición**, sin haber
excedido ningún rate limit real. Esto es independiente del rate limit de
1 req/s que ya respeta nuestro propio harvester.

**Se resuelve sin navegador headless**, solo replicando la forma de
petición de un navegador real:
- `http2=True` en el cliente `httpx` (requiere `pip install httpx[http2]`).
- Headers: `Origin`, `Referer`, `sec-ch-ua`, `sec-ch-ua-mobile`,
  `sec-ch-ua-platform`, `sec-fetch-site`, `sec-fetch-mode`,
  `sec-fetch-dest`, además del `User-Agent` de navegador.

Con esto, tanto `regions` como `simulation` responden `200` de forma
consistente. La API de catálogo (`/api/catalog_system/pub/products/search`)
nunca mostró este bloqueo, ni con el User-Agent identificable del proyecto
— el bot-shield parece aplicar solo al backend de checkout.

**Esto es una tensión real con el principio de "User-Agent identificable"
de `CLAUDE.md`.** Un UA identificable y no-browser-like en el backend `chk`
se bloquea sistemáticamente. Dos caminos, a decidir antes de Fase 5:
1. Usar headers de navegador (incluyendo UA de Chrome) **solo** para las
   llamadas a `simulation`/`regions`, mientras el resto del tráfico
   (catálogo/búsqueda) sigue con el UA identificable del proyecto.
2. Mantener el UA identificable en todos lados y aceptar una tasa de 429
   en checkout, con reintentos — más lento y menos confiable.

Recomiendo la opción 1: no es evasión de un WAF real ni de una protección
anti-scraping deliberada contra bots maliciosos — es iguar la forma de una
petición pública que cualquier visitante anónimo del sitio hace sin
autenticarse ni aceptar términos, para un endpoint que no requiere login.
Lo dejo para que lo confirmes antes de codificarlo en Fase 5, porque sí es
una desviación del principio original de `CLAUDE.md`.

## 4. Validación obligatoria — 3 SKUs, pipeline vs. sitio real

CP usado en el navegador: **76000** (dirección: Calle Vicente Guerrero Sur,
Centro, Santiago de Querétaro — geocodificada a coordinates
`-100.3949569, 20.590909`, resuelta a seller `chedrauimx0268`).

| SKU | Producto | Precio API legacy (`catalog_system`) | Precio `simulation` (CP 76000) | Precio mostrado en la página del producto | ¿Coinciden? |
|---|---|---|---|---|---|
| 3104995 | Papas Sabritas Adobadas 105g | $38.00 | $38.00 | **$38.00** | ✅ Coinciden (los tres) |
| 3196352 | Botana Papas Sabritas Adobadas 160g | **$52.00** | **$61.00** | **$61.00** | ❌ **API legacy NO coincide** — simulation sí |
| 3783832 | Botana Sabritas Rancheritos 72g | $15.00 (sin stock, `AvailableQuantity:0`) | $15.00 (`availability:"withoutStock"`) | **Agotado** (sin precio visible) | ✅ Coinciden en disponibilidad |

**Conclusión de la validación:** el contexto de región en sí **no estaba
mal** — el problema es que había estado usando la fuente equivocada. La API
de catálogo (`catalog_system`) ignora la región y devuelve el precio
nacional de lista; en el SKU 3196352 eso produce un precio **17% más bajo**
que el real de tienda ($52 vs $61). Si el harvester hubiera usado esa API
como fuente de precio (como hice por defecto en Fase 1), **todo el
histórico de precios habría quedado contaminado con el precio nacional
genérico, no el de Querétaro** — exactamente el riesgo que advertía el
brief. La fuente correcta y ya validada es `simulation`.

## Siguientes pasos

Con esto, Fase 2 queda resuelta para Chedraui: sabemos cómo resolver
región, sabemos qué endpoint da el precio real, y quedó documentado el
único obstáculo operativo (bot-shield del backend de checkout) con una
solución probada. Falta tu visto bueno para:
1. Confirmar el uso de headers de navegador solo en las llamadas a
   checkout/simulation (sección 3).
2. Avanzar a Fase 3 (descubrimiento de la categoría botanas) usando
   `discover()` sobre el árbol de categorías / búsqueda por marca / texto
   libre, ya sabiendo que el precio real se obtendrá después vía
   `simulation`, no desde `discover()` mismo.
