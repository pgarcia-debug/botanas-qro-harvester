-- v_price_movements_7d (0003) confía en su propio ORDER BY interno para
-- que "los movimientos más grandes primero" salga bien. Eso NO está
-- garantizado cuando algo externo (como PostgREST/REST vía el dashboard
-- público) hace su propio `order=` sobre la vista — reordena por el
-- valor CON signo de delta_absoluto, no por magnitud. Se agrega una
-- columna explícita sin signo para poder ordenar bien desde afuera.

drop view if exists v_price_movements_7d;

create view v_price_movements_7d as
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
    abs(e.price_sale - e.prev_price_sale) as delta_abs_magnitud,
    round(100.0 * (e.price_sale - e.prev_price_sale) / nullif(e.prev_price_sale, 0), 2) as delta_pct,
    e.prev_captured_at,
    e.captured_at
from events_7d e
join products p on p.id = e.product_id
join retailers r on r.id = p.retailer_id
where e.prev_price_sale is not null
  and e.price_sale is not null
  and e.price_sale <> e.prev_price_sale
order by delta_abs_magnitud desc;

comment on view v_price_movements_7d is 'Cambios de precio (price_sale) de los últimos 7 días. Ordenar explícitamente por delta_abs_magnitud (no por delta_absoluto, que trae signo) para "top movimientos" real vía REST — "Top 30" = ORDER BY delta_abs_magnitud DESC LIMIT 30.';

grant select on v_price_movements_7d to anon;
