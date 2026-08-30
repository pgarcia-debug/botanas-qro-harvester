import { getCurrentPrices, getLastRunSummary, getPriceMovements } from "./data";
import PriceTable from "./PriceTable";

export const dynamic = "force-dynamic";

function timeAgo(iso) {
  if (!iso) return null;
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "hace instantes";
  if (mins < 60) return `hace ${mins} min`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `hace ${hours} h`;
  const days = Math.floor(hours / 24);
  return `hace ${days} d`;
}

function money(v) {
  if (v === null || v === undefined) return "—";
  return `$${Number(v).toFixed(2)}`;
}

export default async function Page() {
  const [prices, movements, runs] = await Promise.all([
    getCurrentPrices(),
    getPriceMovements(),
    getLastRunSummary(),
  ]);

  const run = Array.isArray(runs) && runs.length > 0 ? runs[0] : null;
  const inStockCount = prices.filter((p) => {
    const first = p.por_retailer && Object.values(p.por_retailer)[0];
    return first && first.in_stock;
  }).length;

  return (
    <div className="wrap">
      <header className="top">
        <h1>🌶️ Botanas QRO</h1>
        <p>
          Precios de botanas saladas y frituras en Querétaro capital (CP
          76000) — actualizado diariamente vía scraping automatizado.
        </p>
      </header>

      <div className="stats">
        <div className="stat">
          <div className="n">{prices.length}</div>
          <div className="l">productos rastreados</div>
        </div>
        <div className="stat">
          <div className="n">{inStockCount}</div>
          <div className="l">en stock ahora</div>
        </div>
        <div className="stat">
          <div className="n">{run ? timeAgo(run.started_at) : "—"}</div>
          <div className="l">
            {run ? `última corrida (${run.retailer_name})` : "sin corridas todavía"}
          </div>
        </div>
      </div>

      <section>
        <h2>Precio vigente, ordenado por $/100g</h2>
        <p className="hint">
          El precio más conveniente primero — comparable entre marcas y
          presentaciones distintas.
        </p>
        <PriceTable rows={prices} />
      </section>

      <section>
        <h2>Movimientos de precio (últimos 7 días)</h2>
        <p className="hint">
          Cambios reales detectados por el harvester — cada fila es un
          precio que subió o bajó de un día a otro.
        </p>
        {movements.length === 0 ? (
          <div className="table-scroll">
            <div className="empty">
              Todavía no hay suficiente histórico para mostrar movimientos
              de precio — vuelve en unos días.
            </div>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Producto</th>
                  <th className="num">Antes</th>
                  <th className="num">Ahora</th>
                  <th className="num">Cambio</th>
                </tr>
              </thead>
              <tbody>
                {movements.map((m) => (
                  <tr key={`${m.product_id}-${m.captured_at}`}>
                    <td>{m.name}</td>
                    <td className="num">{money(m.prev_price_sale)}</td>
                    <td className="num">{money(m.price_sale_actual)}</td>
                    <td className="num">
                      <span
                        className={`badge ${
                          m.delta_absoluto < 0 ? "good" : "bad"
                        }`}
                      >
                        {m.delta_absoluto > 0 ? "+" : ""}
                        {money(m.delta_absoluto)} ({m.delta_pct}%)
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <footer className="foot">
        Datos públicos de retail, recolectados con fines de comparación de
        precios. Fuente: catálogo público de Chedraui, zona Querétaro
        (CP 76000).
      </footer>
    </div>
  );
}
