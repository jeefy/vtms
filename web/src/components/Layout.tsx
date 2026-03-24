import type { ReactNode } from "react";

interface LayoutProps {
  statusBar: ReactNode;
  gopro: ReactNode;
  map: ReactNode;
  gauges: ReactNode;
  sdr: ReactNode;
}

export function Layout({ statusBar, gopro, map, gauges, sdr }: LayoutProps) {
  return (
    <div className="layout">
      <header className="layout-header">{statusBar}</header>

      <main className="layout-main">
        <div className="layout-left">
          <section className="layout-map">{map}</section>
          <section className="layout-gopro">{gopro}</section>
        </div>
        <aside className="layout-gauges">{gauges}</aside>
        <aside className="layout-sdr">{sdr}</aside>
      </main>
    </div>
  );
}
