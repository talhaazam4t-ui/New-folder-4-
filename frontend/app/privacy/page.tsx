import { LegalPage } from "@/components/shared/LegalPage";

export const metadata = { title: "Privacy Policy — Teloxtech" };

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy Policy" updated="November 2026">
      <p>
        Teloxtech provides managed AI business services (financial tracking, marketing, WhatsApp
        concierge, lead CRM, analytics). This policy explains what data we handle and why.
      </p>

      <h2>Information we collect</h2>
      <ul>
        <li>Account data: name, email, company name, industry and the services you select.</li>
        <li>Business data you add: transactions, leads, appointments, messages and reports.</li>
        <li>Billing data: invoices, payment references and bank-transfer confirmations.</li>
        <li>Integration data: tokens issued when you connect third-party accounts.</li>
      </ul>

      <h2>Google user data</h2>
      <p>
        If you choose to connect Gmail or Google Calendar, we request only the permissions needed
        for the feature you enable: sending and reading email on your behalf (Gmail) and creating
        or checking calendar events (Google Calendar), plus your basic profile and email address
        for identification. We use this data solely to provide those features to you. We do not
        sell Google user data, use it for advertising, or transfer it to others except as needed
        to operate the service or comply with law.
      </p>
      <p>
        Teloxtech&apos;s use and transfer of information received from Google APIs adheres to the{" "}
        <a
          className="text-emerald-700 underline"
          href="https://developers.google.com/terms/api-services-user-data-policy"
        >
          Google API Services User Data Policy
        </a>
        , including the Limited Use requirements.
      </p>

      <h2>How we protect data</h2>
      <ul>
        <li>Each client&apos;s data is isolated by tenant and protected by access controls.</li>
        <li>Integration tokens are stored encrypted and are never shown in full.</li>
        <li>Connections use HTTPS.</li>
      </ul>

      <h2>Sharing</h2>
      <p>
        We use infrastructure and AI providers (hosting, database, AI models, messaging providers)
        to deliver the service. They process data only on our instructions. We do not sell personal
        data.
      </p>

      <h2>Retention and deletion</h2>
      <p>
        We keep data while your account is active. You can disconnect any integration at any time
        from Settings, and you can ask us to delete your account and data using the contact below.
        You can also revoke Teloxtech&apos;s access at{" "}
        <a className="text-emerald-700 underline" href="https://myaccount.google.com/permissions">
          myaccount.google.com/permissions
        </a>
        .
      </p>

      <h2>Changes</h2>
      <p>We may update this policy; the date above shows the latest version.</p>
    </LegalPage>
  );
}
