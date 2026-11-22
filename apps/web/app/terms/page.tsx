import type { Metadata } from "next";
import { LegalPage } from "../_components/legal-page";

export const metadata: Metadata = {
  title: "Terms of Service | Terravanta",
  description: "Terms for using the Terravanta farm intelligence and cooperative operations pilot.",
  alternates: { canonical: "/terms" },
  robots: { index: true, follow: true },
};

export default function TermsPage() {
  return <LegalPage
    eyebrow="SERVICE TERMS · PILOT"
    title="Terms of Service"
    introduction="These terms cover access to the Terravanta pilot. By creating an account or using the service, you agree to use it only for authorized farm and cooperative work."
    sections={[
      { title: "The service", body: <p>Terravanta provides digital records and workflow tools for farms, veterinarians, cooperatives and processors. Features may change during the pilot and may be unavailable at times. Unless a separate written agreement says otherwise, the pilot has no guaranteed uptime, support response time or service level.</p> },
      { title: "Accounts and access", body: <p>Provide accurate account information, protect your sign-in credentials and use only the role and records you are authorized to access. Do not share accounts or attempt to bypass farm, organization, consent or role restrictions. Tell the Terravanta operator promptly if you believe your account has been accessed without permission.</p> },
      { title: "Records and permissions", body: <p>You remain responsible for the records you enter or upload, their accuracy and your authority to use or share them. Preserve the source and context of records. Do not upload another person’s personal information, veterinary information, cooperative records or processor evidence unless you have a lawful basis and the required authorization. A permission to view a record does not authorize unrelated use or onward sharing.</p> },
      { title: "Evidence, settlement and professional decisions", body: <p>Terravanta organizes records, calculations and evidence for human review. It does not independently establish that a processor owes a debt, determine a legal due date, collect or transfer money, guarantee settlement, approve credit or provide legal or financial advice. A cooperative or processor reviewer remains responsible for its own decisions and communications.</p> },
      { title: "Veterinary and AI limits", body: <p>Veterinary features support documentation and communication; they do not diagnose, prescribe, calculate treatment doses or replace a licensed veterinarian. AI output is a review draft based on the supplied context and may be incomplete or wrong. A qualified person must review it before any action. Do not use Terravanta or WhatsApp messaging as an emergency service.</p> },
      { title: "Optional integrations", body: <p>AI processing and WhatsApp communication are optional and may require separate consent. WhatsApp linking does not authenticate a user or grant access to farm records. You can withdraw channel consent where the feature is available. Third-party services are also governed by their own terms.</p> },
      { title: "Suspension and termination", body: <p>We may limit or suspend access to protect users, records, the service or legal rights, including when an account appears compromised or is used outside its authorization. You may stop using the service and request account or data deletion using the <a href="/data-deletion">data deletion instructions</a>. Some records may be retained or restricted where applicable law, dispute evidence or record integrity requires it.</p> },
      { title: "Fees and changes", body: <p>No fee is due under these pilot terms unless you separately accept a written pricing offer or agreement. We may revise these terms as the service develops; the current version and date appear on this page. Continued use after an updated version is posted means you accept the updated terms to the extent permitted by law.</p> },
      { title: "Contact", body: <p>For support or questions about these terms, email <a href="mailto:grafanaios@gmail.com">grafanaios@gmail.com</a>.</p> },
    ]}
  />;
}
