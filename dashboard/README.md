# Dashboard (temporal)

UI de solo lectura para ver los precios que recolecta el harvester —
**no es parte del pipeline de producción**, es una demo desplegada en
Vercel para validar visualmente los datos.

Lee directamente de 3 vistas públicas de Supabase vía PostgREST
(`v_current_price_by_gtin`, `v_price_movements_7d`, `v_last_run_summary`
— ver `../migrations/0004_public_dashboard.sql` y `0005_fix_movements_view_sort.sql`).
Usa la clave `anon`/publishable de Supabase, que está diseñada para vivir
en el cliente — la protección real es que solo esas 3 vistas de solo
lectura tienen `GRANT SELECT` para ese rol; las tablas base siguen con
RLS activo sin ninguna política (nadie puede leer ni escribir ahí desde
afuera).

## Local

```bash
cd dashboard
npm install
npm run dev
```
