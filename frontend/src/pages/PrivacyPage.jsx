export default function PrivacyPage() {
  return (
    <div style={{ maxWidth: 760, margin: '0 auto', lineHeight: 1.7 }}>
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>Privacy Policy</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: 32, fontSize: 14 }}>
        Last updated: March 30, 2026
      </p>

      <Section title="1. Who We Are">
        MLBPredictIt.com ("the Site") is operated by Andrew Maxwell, an individual based in
        California. The Site provides baseball game predictions and statistical projections for
        entertainment and informational purposes only. We are not affiliated with Major League
        Baseball or any MLB team.
      </Section>

      <Section title="2. Information We Collect">
        <p style={{ marginBottom: 12 }}>
          <strong>Information collected automatically:</strong>
        </p>
        <ul style={{ paddingLeft: 24, marginBottom: 16 }}>
          <li>IP address (used solely for rate limiting to prevent abuse)</li>
          <li>Pages visited and timestamps (standard server logs retained for 30 days)</li>
          <li>Browser type and device information (standard HTTP headers)</li>
        </ul>
        <p style={{ marginBottom: 12 }}>
          <strong>Information we do NOT collect:</strong>
        </p>
        <ul style={{ paddingLeft: 24 }}>
          <li>Names, email addresses, or any personally identifiable information</li>
          <li>Payment or financial information</li>
          <li>Location data beyond what is inferred from IP address</li>
          <li>Cookies for tracking or advertising purposes</li>
        </ul>
        <p style={{ marginTop: 12 }}>
          We do not require account creation. There are no login forms, registration flows, or
          user profiles on this Site.
        </p>
      </Section>

      <Section title="3. How We Use Information">
        The limited information we collect is used exclusively to:
        <ul style={{ paddingLeft: 24, marginTop: 8 }}>
          <li>Operate and maintain the Site</li>
          <li>Enforce rate limiting to prevent abuse and ensure availability</li>
          <li>Monitor for security threats</li>
          <li>Debug technical issues</li>
        </ul>
        We do not use any collected information for advertising, profiling, or marketing purposes.
      </Section>

      <Section title="4. Data Sharing">
        We do not sell, rent, trade, or otherwise share your personal information with any third
        party. Server logs containing IP addresses are not shared with anyone. The Site is hosted
        on Render.com (backend) and GitHub Pages (frontend), which may process requests in
        accordance with their own privacy policies.
      </Section>

      <Section title="5. Third-Party Services">
        The Site relies on the following third-party services:
        <ul style={{ paddingLeft: 24, marginTop: 8 }}>
          <li><strong>Render.com</strong> — Backend hosting. Subject to Render's privacy policy.</li>
          <li><strong>GitHub Pages</strong> — Frontend hosting. Subject to GitHub's privacy policy.</li>
          <li><strong>MLB Stats API</strong> — Live baseball data. No user data is transmitted to MLB.</li>
          <li><strong>Baseball Savant</strong> — Statcast data. No user data is transmitted.</li>
        </ul>
        We do not use Google Analytics, Facebook Pixel, or any third-party tracking or advertising
        services.
      </Section>

      <Section title="6. Data Retention">
        Server logs containing IP addresses are automatically deleted after 30 days. We do not
        maintain any long-term database of user activity or personal information.
      </Section>

      <Section title="7. Your Rights Under California Law (CCPA/CPRA)">
        If you are a California resident, you have the following rights under the California
        Consumer Privacy Act (CCPA) and the California Privacy Rights Act (CPRA):
        <ul style={{ paddingLeft: 24, marginTop: 8 }}>
          <li><strong>Right to Know:</strong> You may request what personal information we have collected about you. Given our minimal data collection, this is limited to server log entries.</li>
          <li><strong>Right to Delete:</strong> You may request deletion of any personal information we hold.</li>
          <li><strong>Right to Opt-Out of Sale:</strong> We do not sell personal information. There is nothing to opt out of.</li>
          <li><strong>Right to Non-Discrimination:</strong> We will not discriminate against you for exercising any of these rights.</li>
        </ul>
        <p style={{ marginTop: 12 }}>
          To exercise any of these rights, contact us at the email address below.
        </p>
      </Section>

      <Section title="8. Do Not Track">
        This Site does not track users across third-party websites. We honor Do Not Track (DNT)
        browser signals by default, as we do not engage in tracking.
      </Section>

      <Section title="9. Children's Privacy">
        This Site is not directed at children under 13. We do not knowingly collect personal
        information from children. If you believe a child has provided us with personal
        information, please contact us and we will delete it.
      </Section>

      <Section title="10. Security">
        We implement reasonable technical measures to protect the limited data we collect,
        including rate limiting, input sanitization, and HTTPS encryption.
      </Section>

      <Section title="11. Changes to This Policy">
        We may update this Privacy Policy from time to time. Changes will be posted on this
        page with an updated "Last updated" date. Continued use of the Site after changes
        constitutes acceptance of the revised policy.
      </Section>

      <Section title="12. Contact">
        For privacy-related questions or to exercise your California privacy rights, contact:
        <div style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          padding: 16,
          marginTop: 12,
          fontSize: 14,
        }}>
          Andrew Maxwell<br />
          andrewmaxwellbusiness@gmail.com
        </div>
      </Section>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <section style={{ marginBottom: 28 }}>
      <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 10, color: 'var(--text-primary)' }}>
        {title}
      </h2>
      <div style={{ color: 'var(--text-secondary)', fontSize: 15 }}>
        {children}
      </div>
    </section>
  )
}
