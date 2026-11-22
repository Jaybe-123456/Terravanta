import type { ReactNode } from "react";

type LegalSection = { title: string; body: ReactNode };

export function LegalPage({
  eyebrow,
  title,
  introduction,
  updated = "November 22, 2026",
  sections,
}: {
  eyebrow: string;
  title: string;
  introduction: string;
  updated?: string;
  sections: LegalSection[];
}) {
  return (
    <main className="legal-page">
      <header className="legal-header">
        <a className="product-brand" href="/product" aria-label="Terravanta product overview">
          <span className="product-brand-mark">T</span>
          <span>terravanta<small>FARM INTELLIGENCE</small></span>
        </a>
        <a className="legal-back-link" href="/product">Product overview <span aria-hidden="true">→</span></a>
      </header>
      <article className="legal-document">
        <p className="product-kicker"><span />{eyebrow}</p>
        <h1>{title}</h1>
        <p className="legal-intro">{introduction}</p>
        <p className="legal-updated">Last updated {updated}</p>
        <nav className="legal-contents" aria-label="On this page">
          {sections.map((section, index) => <a key={section.title} href={`#section-${index + 1}`}>{section.title}</a>)}
        </nav>
        {sections.map((section, index) => (
          <section className="legal-section" id={`section-${index + 1}`} key={section.title}>
            <h2>{section.title}</h2>
            <div>{section.body}</div>
          </section>
        ))}
        <aside className="legal-contact">
          Questions or requests? Email <a href="mailto:grafanaios@gmail.com">grafanaios@gmail.com</a>.
        </aside>
      </article>
      <footer className="legal-footer">
        <span>Terravanta · Kenya pilot</span>
        <nav aria-label="Legal pages">
          <a href="/privacy">Privacy</a>
          <a href="/terms">Terms</a>
          <a href="/data-deletion">Data deletion</a>
        </nav>
      </footer>
    </main>
  );
}
