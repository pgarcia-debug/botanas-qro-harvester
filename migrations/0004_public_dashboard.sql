-- UI pública de solo lectura (dashboard temporal en Vercel).
--
-- Decisión de seguridad, explícita: se expone lectura pública (rol
-- `anon`, vía PostgREST) SOLO de estas 3 vistas — nunca de las tablas
-- base. Las tablas (`products`, `price_events`, `retailers`, `run_log`,
-- `product_matches`) siguen con RLS activo y CERO políticas (ver
-- migrations/0002_enable_rls.sql) — anon no puede leer ni escribir nada
-- ahí directamente. Las vistas no son security_invoker, así que corren
-- con los permisos del rol que las creó (no las de quien consulta) —
-- eso es lo que permite exponerlas sin abrir RLS en las tablas de abajo.
-- El dato expuesto es precio público de retail (sin PII, sin secretos) y
-- no hay ningún GRANT de INSERT/UPDATE/DELETE para anon en ningún lado.

begin;

-- =====================================================================
-- v_last_run_summary: contexto para el dashboard ("actualizado hace X").
-- Solo expone status/fecha/conteos — nada de `notes` (podría tener
-- detalle operativo interno) ni nada de connection/error internals.
-- =====================================================================
create or replace view v_last_run_summary as
select distinct on (r.id)
    r.id as retailer_id,
    r.name as retailer_name,
    r.domain as retailer_domain,
    rl.started_at,
    rl.finished_at,
    rl.status,
    rl.items_ok,
    rl.items_err
from retailers r
join run_log rl on rl.retailer_id = r.id
where rl.status in ('success', 'warning')
order by r.id, rl.started_at desc;

comment on view v_last_run_summary is 'Última corrida exitosa/con warning por retailer — solo lo necesario para mostrar "actualizado hace X" en un dashboard público. No expone notes ni detalle operativo.';

grant select on v_current_price_by_gtin to anon;
grant select on v_price_movements_7d to anon;
grant select on v_last_run_summary to anon;

commit;
