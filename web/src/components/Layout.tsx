import type { ReactNode } from "react";

interface LayoutProps {
  statusBar: ReactNode;
  gopro: ReactNode;
  map: ReactNode;
  gauges: ReactNode;
}

export function Layout({ statusBar, gopro, map, gauges }: LayoutProps) {
  return (
    <div className="layout">
      <header className="layout-header">{statusBar}</header>

      <main className="layout-main">
        <div className="layout-left">
          <section className="layout-gopro">{gopro}</section>
          <section className="layout-map">{map}</section>
        </div>
        <aside className="layout-gauges">{gauges}</aside>
      </main>
    </div>
  );
}
