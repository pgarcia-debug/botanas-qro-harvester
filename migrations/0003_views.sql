-- Entregables finales: vista de precio vigente por marca/presentación
-- (con desglose por retailer) y consulta de movimientos de precio.
--
-- Nota sobre "columna por retailer" (pedido del brief): un pivot con una
-- columna SQL literal por retailer no es dinámico en Postgres sin
-- hardcodear los nombres (crosstab de tablefunc exige columnas fijas).
-- Con un solo retailer hoy (Chedraui) eso sería prematuro y se rompería
-- cada vez que se agregue uno nuevo. En su lugar, `por_retailer` es una
-- columna jsonb con una key por retailer — se comporta como "una columna
-- por retailer" para cualquier consumidor (Python, un dashboard, `->>`
-- en SQL) sin tener que editar la vista cada vez que se agrega una
-- cadena. Ver README para un ejemplo de cómo leerla.

begin;

-- =====================================================================
-- v_latest_price_event: el price_event más reciente por (product_id,
-- seller). Vista base — la reusan las de abajo y sirve directo para
-- "precio vigente por SKU".
-- =====================================================================
create or replace view v_latest_price_event as
select distinct on (product_id, seller)
    id, product_id, seller, captured_at, price_list, price_sale,
    price_per_100g, currency, in_stock, promo_label, source_postal_code
from price_events
order by product_id, seller, captured_at desc;

comment on view v_latest_price_event is 'Precio vigente por (product_id, seller) — el price_event más reciente de cada uno.';

-- =====================================================================
-- v_current_price_by_gtin: comparación entre retailers por marca y
-- presentación (gramaje/tipo de empaque), ordenada por el mejor $/100g.
-- Solo incluye productos con gtin resuelto — sin gtin no hay manera
-- confiable de saber que es "el mismo producto" en otra cadena.
-- =====================================================================
create or replace view v_current_price_by_gtin as
with current_by_product as (
    -- si un product_id tiene más de un seller vigente (p.ej. varias
    -- tiendas de la misma cadena), se prioriza el que tiene stock y,
    -- entre esos, el más barato — es el precio que un comprador real
    -- vería como disponible.
    select distinct on (product_id)
        product_id, seller, price_sale, price_per_100g, in_stock, captured_at
    from v_latest_price_event
    order by product_id, in_stock desc, price_per_100g asc nulls last, captured_at desc
)
select
    p.gtin,
    min(p.brand) as brand,
    min(p.name) as nombre_muestra,
    min(p.net_weight_g) as net_weight_g,
    min(p.package_type) as package_type,
    jsonb_object_agg(
        r.name,
        jsonb_build_object(
            'price_sale', c.price_sale,
            'price_per_100g', c.price_per_100g,
            'in_stock', c.in_stock,
            'captured_at', c.captured_at
        )
        order by r.name
    ) filter (where r.name is not null) as por_retailer,
    min(c.price_per_100g) as mejor_price_per_100g
from products p
join retailers r on r.id = p.retailer_id
join current_by_product c on c.product_id = p.id
where p.gtin is not null
group by p.gtin
order by mejor_price_per_100g asc nulls last;

comment on view v_current_price_by_gtin is 'Precio vigente por marca y presentación (agrupado por gtin), con desglose por retailer en `por_retailer` (jsonb, una key por cadena) y ordenado por el mejor $/100g disponible.';

-- =====================================================================
-- v_price_movements_7d: cambios de precio en los últimos 7 días,
-- ordenados por magnitud del cambio (mayor primero). "Top 30" = esta
-- vista con LIMIT 30 (no se hardcodea el límite en la vista — ver
-- README para el ejemplo de consulta).
-- =====================================================================
create or replace view v_price_movements_7d as
with events_7d as (
    select
        pe.id, pe.product_id, pe.seller, pe.price_sale, pe.in_stock, pe.captured_at,
        lag(pe.price_sale) over w as prev_price_sale,
        lag(pe.captured_at) over w as prev_captured_at
    from price_events pe
    where pe.captured_at >= now() - interval '7 days'
    window w as (partition by pe.product_id, pe.seller order by pe.captured_at)
)
select
    p.id as product_id,
    p.sku,
    p.name,
    p.brand,
    r.name as retailer,
    e.seller,
    e.prev_price_sale,
    e.price_sale as price_sale_actual,
    (e.price_sale - e.prev_price_sale) as delta_absoluto,
    round(100.0 * (e.price_sale - e.prev_price_sale) / nullif(e.prev_price_sale, 0), 2) as delta_pct,
    e.prev_captured_at,
    e.captured_at
from events_7d e
join products p on p.id = e.product_id
join retailers r on r.id = p.retailer_id
where e.prev_price_sale is not null
  and e.price_sale is not null
  and e.price_sale <> e.prev_price_sale
order by abs(e.price_sale - e.prev_price_sale) desc;

comment on view v_price_movements_7d is 'Cambios de precio (price_sale) de los últimos 7 días, ordenados por magnitud absoluta del cambio. "Top 30 movimientos" = SELECT * FROM v_price_movements_7d LIMIT 30.';

commit;
