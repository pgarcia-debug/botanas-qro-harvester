// Clave pública ("publishable"/anon) de Supabase — está diseñada para
// vivir en el cliente, la protección real es RLS del lado del servidor
// (ver migrations/0004_public_dashboard.sql: solo 3 vistas de solo
// lectura, sin ningún GRANT de escritura).
const SUPABASE_URL = "https://mpaplyddfabyvzjleobf.supabase.co";
const ANON_KEY = "sb_publishable__H0DiykXNF0ho1swvVDeLA_ntWg0xqG";

async function fetchView(view, query) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${view}?${query}`, {
    headers: {
      apikey: ANON_KEY,
      Authorization: `Bearer ${ANON_KEY}`,
    },
    cache: "no-store",
  });
  if (!res.ok) {
    return [];
  }
  return res.json();
}

export async function getCurrentPrices() {
  return fetchView(
    "v_current_price_by_gtin",
    "select=*&order=mejor_price_per_100g.asc&limit=2000"
  );
}

export async function getPriceMovements() {
  return fetchView(
    "v_price_movements_7d",
    "select=*&order=delta_abs_magnitud.desc&limit=30"
  );
}

export async function getLastRunSummary() {
  return fetchView("v_last_run_summary", "select=*&order=started_at.desc");
}
