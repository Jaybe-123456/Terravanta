import type { Metadata } from "next";
import { LegalPage } from "../_components/legal-page";

export const metadata: Metadata = {
  title: "Request Data Deletion | Terravanta",
  description: "How to request deletion or restriction of your Terravanta account and personal data.",
  alternates: { canonical: "/data-deletion" },
  robots: { index: true, follow: true },
};

export default function DataDeletionPage() {
  return <LegalPage
    eyebrow="PRIVACY · YOUR DATA"
    title="Request account or data deletion"
    introduction="You can ask Terravanta to delete your account or specific personal information. Requests are handled manually by the pilot operator; there is no self-service deletion control in the current application."
    sections={[
      { title: "Send a request", body: <><p>Email <a href="mailto:grafanaios@gmail.com?subject=Terravanta%20data%20deletion%20request">grafanaios@gmail.com</a> with the subject <strong>Terravanta data deletion request</strong>.</p><p>Include the name and email address used for your Terravanta account, the organization or farm workspace if relevant, and whether you want the account closed, particular personal details removed, or both. If you are acting for another person, include proof that you are authorized to make the request.</p><p>Do not include your password, one-time sign-in code, access token, or copies of sensitive farm or veterinary documents in the email.</p></> },
      { title: "How we handle it", body: <p>We will verify the request without asking for your password, identify the relevant account and records, and review whether any information must be preserved for another user’s record, an audit trail, an active dispute or a legal obligation. We will delete or de-identify information where appropriate and restrict information that must be retained where feasible. We will respond in line with applicable legal requirements and explain any material limits on the request.</p> },
      { title: "Connected records and channels", body: <p>Farm, veterinary, settlement and receivables records can include information about other people or organizations. Deleting one account may not remove source records that another authorized party is required to retain. You can also request revocation of active farm-sharing consent or removal of a linked WhatsApp number in the request. WhatsApp messages already received by the service may require separate review under the same process.</p> },
      { title: "Contact", body: <p>If you need help narrowing the request, contact <a href="mailto:grafanaios@gmail.com">grafanaios@gmail.com</a>. See the <a href="/privacy">Privacy Policy</a> for more detail about the information Terravanta handles.</p> },
    ]}
  />;
}
