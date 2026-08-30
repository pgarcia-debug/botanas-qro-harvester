import "./globals.css";

export const metadata = {
  title: "Botanas QRO — Monitor de precios",
  description:
    "Precios de botanas saladas y frituras en supermercados de Querétaro, actualizados diariamente.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
