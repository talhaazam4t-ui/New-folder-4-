import { LegalPage } from "@/components/shared/LegalPage";

export const metadata = { title: "Terms of Service — Teloxtech" };

export default function TermsPage() {
  return (
    <LegalPage title="Terms of Service" updated="November 2026">
      <p>By creating an account or using Teloxtech you agree to these terms.</p>

      <h2>The service</h2>
      <p>
        Teloxtech provides managed AI business services. You choose the services you want; each is
        activated after your payment is verified by us.
      </p>

      <h2>Payments</h2>
      <p>
        Services are billed per the package you select. Services are activated only after we verify
        your payment (for example, a bank transfer). Unpaid services stay locked.
      </p>

      <h2>Your responsibilities</h2>
      <ul>
        <li>Provide accurate information and keep your login secure.</li>
        <li>Use the service lawfully, including messaging and email laws and platform policies.</li>
        <li>Only connect accounts (WhatsApp, Google) that you are authorized to use.</li>
      </ul>

      <h2>AI output</h2>
      <p>
        AI-generated content may contain errors. Review important messages, financial figures and
        decisions before relying on them. High-impact actions may require your approval.
      </p>

      <h2>Third-party services</h2>
      <p>
        Features that use Google, Meta/WhatsApp or other providers are subject to those
        providers&apos; terms and availability.
      </p>

      <h2>Suspension and termination</h2>
      <p>
        We may suspend accounts that violate these terms or misuse the service. You may stop using
        the service and request account deletion at any time.
      </p>

      <h2>Liability</h2>
      <p>
        The service is provided &quot;as is&quot;. To the extent permitted by law, Teloxtech is not
        liable for indirect or consequential losses.
      </p>
    </LegalPage>
  );
}
