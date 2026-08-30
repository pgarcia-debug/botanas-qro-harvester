-- Fase 4 — Activa Row Level Security en las 5 tablas, sin políticas.
--
-- Efecto: bloquea TODO acceso vía las claves anon/authenticated de
-- PostgREST (lectura y escritura). El harvester sigue funcionando normal
-- porque escribe con la service-role key, que bypassa RLS por diseño de
-- Supabase.
--
-- Decisión explícita del usuario (Fase 4): no se agregan políticas
-- todavía porque no hay consumidor público definido. Si más adelante se
-- construye un dashboard de precios u otro consumidor con la clave anon,
-- agregar ahí las políticas de lectura específicas que necesite — nunca
-- una política blanket "true" sin pensar qué se expone.

alter table public.retailers enable row level security;
alter table public.products enable row level security;
alter table public.price_events enable row level security;
alter table public.product_matches enable row level security;
alter table public.run_log enable row level security;
