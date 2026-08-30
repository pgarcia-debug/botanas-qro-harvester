# Infraestructura

## Supabase

- Proyecto: `botanas-qro-harvester`
- Project ref: `mpaplyddfabyvzjleobf`
- URL: https://mpaplyddfabyvzjleobf.supabase.co
- Región: us-east-1
- Organización: `pgarcia@eter3d.com.mx's Org` (plan free)
- Migraciones aplicadas: `migrations/0001_init.sql` (Fase 4 — retailers,
  products, price_events, product_matches, run_log)

**Resuelto (Fase 4):** RLS activado en las 5 tablas, sin políticas
(`migrations/0002_enable_rls.sql`) — decisión explícita del usuario.
Bloquea todo acceso vía las claves `anon`/`authenticated` de PostgREST; el
harvester sigue funcionando porque escribe con la `service_role` key, que
bypassa RLS. Si en el futuro se construye un consumidor público (dashboard
de precios), agregar ahí las políticas de lectura específicas que
necesite — nunca una política `USING (true)` genérica sin pensar qué se
expone.

Secretos (connection string, service role key) — **no están en este
repo**, van solo en variables de entorno / GitHub Actions secrets, como
manda `CLAUDE.md`.
