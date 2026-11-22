import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terravanta | Cooperative receivables and farm records",
  description: "Explore Terravanta’s evidence-backed processor receivables workflow, cooperative settlement tools and connected farm records.",
  alternates: { canonical: "/product" },
  robots: { index: true, follow: true },
  openGraph: {
    title: "Terravanta | Cooperative receivables and farm records",
    description: "A source-linked processor receivables workflow and connected farm records for cooperatives and Kenyan mixed farms.",
    url: "/product",
    siteName: "Terravanta",
    type: "website",
  },
};

const workflow = [
  { number: "01", title: "Bring the source records", body: "Start from cooperative delivery, processor settlement and payout files, plus the contract terms and supporting evidence your team already holds." },
  { number: "02", title: "Build a reviewable claim", body: "Keep each amount tied to its source, show the due-date basis, and leave unknown or disputed terms explicitly unresolved." },
  { number: "03", title: "Record the other side", body: "An authorized processor reviewer can confirm, partially confirm or dispute the claim. Preserve each response in the case history." },
  { number: "04", title: "Export the evidence trail", body: "Give cooperative reviewers a dated register and evidence pack they can use in their own follow-up and financing conversations." },
];

export default function ProductPage() {
  return <main className="product-page">
    <header className="product-topbar">
      <a className="product-brand" href="/" aria-label="Terravanta home"><span className="product-brand-mark">T</span><span>terravanta<small>FARM INTELLIGENCE</small></span></a>
      <nav aria-label="Main navigation"><a href="#receivables">Receivables</a><a href="#workflows">Workflows</a><a href="#boundaries">What it does</a></nav>
      <a className="button button-primary" href="/">Sign in <span aria-hidden="true">→</span></a>
    </header>

    <section className="product-hero">
      <div className="product-hero-copy">
        <p className="product-kicker"><span />COOPERATIVE OPERATIONS · PROCESSOR RECEIVABLES</p>
        <h1>Make a late processor payment easier to prove, follow up and finance.</h1>
        <p className="product-lede">Terravanta turns a cooperative’s scattered settlement records into a source-linked receivables case: what is claimed, who owes it, what supports it, what is disputed and how old it is.</p>
        <div className="product-hero-actions"><a className="button button-primary" href="/">Open Terravanta <span aria-hidden="true">→</span></a><a className="product-secondary-link" href="#workflows">See how the workflow works</a></div>
        <p className="product-honesty"><strong>Product overview, not a customer-results claim.</strong> There is no validated processor integration or published cooperative case study yet.</p>
      </div>
      <div className="product-hero-panel" aria-label="Illustration of a claim record">
        <div className="product-panel-top"><span>CLAIM RECORD · REVIEW WORKSPACE</span><span className="product-panel-status">Evidence linked</span></div>
        <div className="product-panel-amount"><small>Claimed balance</small><strong>Built from reviewed source lines</strong><span>Currency and value come from the cooperative’s records</span></div>
        <div className="product-panel-rows"><div><span>Claim basis</span><b>Source-linked</b></div><div><span>Due date</span><b>Contract reviewed</b></div><div><span>Processor response</span><b>Recorded by named reviewer</b></div><div><span>Age</span><b>Unknown terms stay unknown</b></div></div>
        <div className="product-panel-foot"><span className="product-ledger-dot" />Every assertion remains attributed to its source and reviewer.</div>
      </div>
    </section>

    <section className="product-video card" aria-labelledby="product-video-title">
      <div><p className="eyebrow">THE TERRAVANTA WORKFLOW</p><h2 id="product-video-title">A short product explainer</h2><p>This film explains the intended evidence and settlement workflow. It is not evidence that a cooperative has recovered money or reduced payment delays.</p></div>
      <video controls preload="metadata" poster="/videos/terravanta-receivables-assurance-poster.png" aria-label="Terravanta processor receivables product explainer">
        <source src="/videos/terravanta-receivables-assurance.mp4" type="video/mp4" />
        Your browser does not support embedded video. <a href="/videos/terravanta-receivables-assurance.mp4">Open the explainer video</a>.
      </video>
    </section>

    <section className="product-section" id="receivables">
      <div className="product-section-heading"><p className="eyebrow">THE COMMERCIAL WEDGE</p><h2>One workspace for the work between “payment is late” and “here is the supported claim.”</h2><p>The cooperative remains the claimant and decision-maker. Terravanta organizes the evidence, aging and follow-up work around the claim.</p></div>
      <div className="product-capability-grid">
        <article className="card"><span className="product-capability-icon">01</span><h3>Claim register</h3><p>Record processor, period, amount, currency, source and status in one case history.</p></article>
        <article className="card"><span className="product-capability-icon">02</span><h3>Explainable aging</h3><p>Age amounts only from reviewed due-date terms. Unclear contract language stays unaged until a person resolves it.</p></article>
        <article className="card"><span className="product-capability-icon">03</span><h3>Counterparty response</h3><p>Capture a processor reviewer’s confirmation, partial confirmation or dispute with an attributable record.</p></article>
        <article className="card"><span className="product-capability-icon">04</span><h3>Evidence export</h3><p>Prepare a source-indexed case pack for cooperative review and follow-up, with a traceable activity history.</p></article>
      </div>
    </section>

    <section className="product-section product-workflow-section" id="workflows">
      <div className="product-section-heading"><p className="eyebrow">HOW A CASE MOVES</p><h2>From files to a reviewable next step.</h2></div>
      <ol className="product-workflow-list">{workflow.map((item) => <li key={item.number}><span>{item.number}</span><div><h3>{item.title}</h3><p>{item.body}</p></div></li>)}</ol>
    </section>

    <section className="product-section product-connected-section">
      <div className="product-section-heading"><p className="eyebrow">CONNECTED FARM RECORDS</p><h2>Keep cooperative settlement work connected to the farm records behind it.</h2><p>Terravanta also includes farm identity, livestock and veterinary history, crop plots, feed and manure records, production, deliveries and consent-controlled sharing.</p></div>
      <div className="product-connected-tags"><span>Farm identity & passport</span><span>Livestock & veterinary events</span><span>Crops, feed & compost</span><span>Milk production & deliveries</span><span>Consent-controlled sharing</span></div>
    </section>

    <section className="product-boundary" id="boundaries">
      <div><p className="eyebrow">DESIGNED FOR TRUST</p><h2>Evidence support, with clear limits.</h2></div>
      <div className="product-boundary-copy"><p>Terravanta records a cooperative’s claim and the evidence behind it. It does not independently certify a legal debt, move money, guarantee settlement, originate credit or replace legal advice.</p><p>The current workflow starts with files and information authorized by the cooperative. No live processor MIS, bank, mobile-money or cooperative ERP connector is claimed. Any sharing with a lender requires a separate, explicit mandate.</p></div>
    </section>

    <footer className="product-footer"><a className="product-brand" href="/"><span className="product-brand-mark">T</span><span>terravanta<small>FARM INTELLIGENCE</small></span></a><span>Private records require an authenticated, authorized account.</span><nav className="product-legal-links" aria-label="Legal pages"><a href="/privacy">Privacy</a><a href="/terms">Terms</a><a href="/data-deletion">Data deletion</a></nav><a href="/">Open the sign-in page <span aria-hidden="true">→</span></a></footer>
  </main>;
}
