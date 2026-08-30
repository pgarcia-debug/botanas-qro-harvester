-- Fase 4 — Modelo de datos inicial.
-- Harvester de precios de botanas — retail MX, zona Querétaro.
--
-- Convenciones:
--   - Claves primarias: bigint identity (bigserial-equivalente).
--   - Todo timestamp es timestamptz (nunca timestamp sin zona).
--   - Todo precio es numeric (NUNCA float — ver CLAUDE.md "Precios como
--     Decimal, nunca float").
--   - price_events es append-only: el pipeline (Fase 5) es responsable de
--     insertar una fila SOLO si cambió price_list, price_sale o in_stock
--     respecto al último evento del mismo (product_id, seller). Esta
--     migración no impone esa regla vía constraint — vive en la lógica de
--     ingesta, documentada aquí para que quede explícito el contrato.

begin;

-- =====================================================================
-- retailers
-- =====================================================================
create table retailers (
    id              bigint generated always as identity primary key,
    name            text not null,
    domain          text not null unique,
    platform        text not null,              -- 'VTEX' | 'SHOPIFY' | 'CUSTOM' | ...
    -- Contexto de región resuelto en Fase 2 (p.ej. para VTEX: regionId,
    -- sellers cubriendo el CP, sales channel). HOY guarda un solo CP por
    -- retailer (el proyecto corre con un solo CP); el diseño multi-CP a
    -- futuro no requiere cambiar esta tabla — se resuelve en price_events
    -- vía las columnas `seller` / `source_postal_code`, que ya identifican
    -- de qué tienda/CP viene cada precio. Si más adelante se necesitan
    -- MÚLTIPLES CPs activos por retailer al mismo tiempo, el cambio real
    -- sería permitir varias filas de `retailers` por dominio (una por
    -- región) o mover region_context a una tabla `retailer_regions`
    -- aparte — no tocar price_events/products.
    region_context  jsonb not null default '{}'::jsonb,
    active          boolean not null default true,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

comment on table retailers is 'Un row por cadena/dominio. active=false para desactivar sin borrar histórico.';
comment on column retailers.region_context is 'JSON con el contexto de región resuelto en Fase 2 (regionId, sellers, CP de referencia, etc.) — específico de la plataforma.';

-- =====================================================================
-- products
-- =====================================================================
create table products (
    id              bigint generated always as identity primary key,
    retailer_id     bigint not null references retailers(id) on delete restrict,
    sku             text not null,               -- id de SKU/item en la plataforma del retailer (NO el productId si difieren — ver Fase 2/3, el sku es la unidad vendible real)
    gtin            text,                        -- EAN/UPC — llave de cruce entre cadenas. Nullable: no todos los SKUs traen GTIN limpio.
    name            text not null,
    brand           text,
    manufacturer    text,                        -- fabricante/corporativo (p.ej. PepsiCo, Grupo Bimbo) — distinto de brand (p.ej. Sabritas, Barcel)
    category_path   text,                        -- breadcrumb crudo del retailer (p.ej. '/Supermercado/Despensa/Botanas y frutos secos/'), para trazabilidad — NO es la taxonomía propia del proyecto
    net_weight_g    numeric(10,2),                -- gramaje total resuelto (multipacks ya resueltos a total). NULL si no se pudo determinar.
    package_type    text,                        -- 'bolsa' | 'caja' | 'bote' | 'granel' | ... (libre por ahora, sin catálogo cerrado)
    units_per_pack  integer not null default 1,   -- para multipacks: número de unidades individuales
    needs_review    boolean not null default false, -- true si NO se pudo resolver el gramaje — CLAUDE.md: "nunca inventar un peso"
    url             text,
    image_url       text,
    first_seen_at   timestamptz not null default now(),
    last_seen_at    timestamptz not null default now(),

    constraint uq_products_retailer_sku unique (retailer_id, sku),
    constraint ck_products_net_weight_positive check (net_weight_g is null or net_weight_g > 0),
    constraint ck_products_units_per_pack_positive check (units_per_pack >= 1)
);

comment on table products is 'Catálogo por retailer. UNIQUE(retailer_id, sku) — un SKU pertenece a un solo retailer.';
comment on column products.gtin is 'EAN/UPC. Llave de cruce entre cadenas vía product_matches. Sin GTIN, ese producto no participa en comparaciones entre retailers.';
comment on column products.needs_review is 'true si el gramaje no se pudo extraer del nombre/specs con confianza — NUNCA se infiere/inventa un peso. Ver guarda de calidad Fase 6 (>20% needs_review falla el run).';

-- =====================================================================
-- price_events (append-only)
-- =====================================================================
create table price_events (
    id                  bigint generated always as identity primary key,
    product_id          bigint not null references products(id) on delete restrict,
    captured_at         timestamptz not null default now(),
    price_list          numeric(10,2),           -- precio de lista (antes de descuento)
    price_sale          numeric(10,2),           -- precio de venta real (con descuento aplicado, si hay)
    price_per_100g      numeric(10,4),           -- calculado a partir de price_sale (o price_list si no hay sale) y net_weight_g del producto. NULL si el producto tiene needs_review=true.
    currency            char(3) not null default 'MXN',
    in_stock            boolean not null,
    promo_label         text,                    -- texto de la promoción tal cual la reporta el retailer (Teasers/productClusters en VTEX)
    seller              text,                    -- id del seller/tienda que resolvió el precio (p.ej. VTEX sellerChain: "chedrauimx0268") — CRÍTICO: distingue precio regional del genérico, ver Fase 2
    source_postal_code  text,                    -- CP usado para resolver este precio — explícito además de `seller` para no depender de convenciones de nombres por plataforma; habilita histórico multi-CP sin rediseño

    constraint ck_price_events_prices_nonneg check (
        (price_list is null or price_list >= 0) and
        (price_sale is null or price_sale >= 0) and
        (price_per_100g is null or price_per_100g >= 0)
    )
);

comment on table price_events is 'Append-only. Insertar SOLO si cambió price_list, price_sale o in_stock respecto al último evento de (product_id, seller) — regla de negocio en la lógica de ingesta de Fase 5, no en constraint de DB.';
comment on column price_events.seller is 'Identifica la tienda/región real que sirvió el precio (no el seller genérico marketplace) — ver hallazgo de Fase 2: la API de catálogo VTEX devuelve precio nacional genérico, el precio real de tienda viene de simulation y trae su propio seller.';
comment on column price_events.source_postal_code is 'CP que se usó para resolver este precio. Hoy siempre el CP de referencia del retailer (76000); columna lista para cuando el proyecto corra con más de un CP.';

-- =====================================================================
-- product_matches — cruce entre cadenas por GTIN
-- =====================================================================
create table product_matches (
    gtin            text primary key,
    canonical_name  text not null,
    product_ids     bigint[] not null default '{}'::bigint[]
);

comment on table product_matches is 'Un row por GTIN con los product_ids (de products.id, potencialmente de distintos retailers) que representan el mismo producto físico. Poblada/actualizada por un job de matching aparte — no por la ingesta directa.';

-- =====================================================================
-- run_log
-- =====================================================================
create table run_log (
    id              bigint generated always as identity primary key,
    retailer_id     bigint not null references retailers(id) on delete restrict,
    started_at      timestamptz not null default now(),
    finished_at     timestamptz,                 -- NULL mientras el run está en curso
    items_ok        integer not null default 0,
    items_err       integer not null default 0,
    status          text not null default 'running', -- 'running' | 'success' | 'failed' | 'warning'
    notes           text,                        -- resumen legible — mismo texto que va al step summary de GitHub Actions (Fase 6)

    constraint ck_run_log_status check (status in ('running', 'success', 'failed', 'warning')),
    constraint ck_run_log_items_nonneg check (items_ok >= 0 and items_err >= 0)
);

comment on table run_log is 'Una fila por corrida por retailer. Alimenta las guardas de calidad de Fase 6 (comparación contra el promedio de los últimos 3 runs exitosos, etc.).';

-- =====================================================================
-- Índices
-- =====================================================================

-- Precio vigente por SKU + histórico por SKU: misma consulta de acceso
-- (product_id [+ seller], ordenado por captured_at). Este índice sirve
-- ambos casos de uso, y además es el que usa la lógica de ingesta de
-- Fase 5 para leer "el último price_event de este (product_id, seller)"
-- antes de decidir si inserta un evento nuevo.
create index idx_price_events_product_seller_captured
    on price_events (product_id, seller, captured_at desc);

-- Comparación entre retailers por gtin: agrupar products de distintos
-- retailers que comparten gtin.
create index idx_products_gtin
    on products (gtin)
    where gtin is not null;

-- Ranking por price_per_100g dentro de una marca: resolver "productos de
-- esta marca" rápido; el ranking en sí ordena sobre el precio vigente ya
-- resuelto vía idx_price_events_product_seller_captured.
create index idx_products_brand
    on products (brand)
    where brand is not null;

-- Búsquedas por retailer (catálogo completo de una cadena, guardas de Fase 6).
create index idx_products_retailer
    on products (retailer_id);

-- run_log: consultas de guardas de calidad (últimos N runs por retailer).
create index idx_run_log_retailer_started
    on run_log (retailer_id, started_at desc);

commit;
