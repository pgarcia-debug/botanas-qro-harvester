"use client";

import { useMemo, useState } from "react";

function money(v) {
  if (v === null || v === undefined) return "—";
  return `$${Number(v).toFixed(2)}`;
}

function firstRetailerEntry(porRetailer) {
  if (!porRetailer) return null;
  const keys = Object.keys(porRetailer);
  if (keys.length === 0) return null;
  return { name: keys[0], ...porRetailer[keys[0]] };
}

export default function PriceTable({ rows }) {
  const [q, setQ] = useState("");

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter(
      (r) =>
        (r.brand || "").toLowerCase().includes(needle) ||
        (r.nombre_muestra || "").toLowerCase().includes(needle)
    );
  }, [rows, q]);

  return (
    <>
      <input
        className="search"
        type="text"
        placeholder="Buscar por marca o producto…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <div className="table-scroll">
        {filtered.length === 0 ? (
          <div className="empty">Sin resultados para “{q}”.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Producto</th>
                <th>Marca</th>
                <th className="num">Gramaje</th>
                <th className="num">Precio</th>
                <th className="num">$/100g</th>
                <th>Stock</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => {
                const entry = firstRetailerEntry(r.por_retailer);
                return (
                  <tr key={r.gtin}>
                    <td>{r.nombre_muestra}</td>
                    <td className="brand">{r.brand || "—"}</td>
                    <td className="num">
                      {r.net_weight_g ? `${Number(r.net_weight_g)}g` : "—"}
                    </td>
                    <td className="num">{money(entry?.price_sale)}</td>
                    <td className="num price-per-100g">
                      {money(r.mejor_price_per_100g)}
                    </td>
                    <td>
                      {entry?.in_stock ? (
                        <span className="badge good">en stock</span>
                      ) : (
                        <span className="badge bad">agotado</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
