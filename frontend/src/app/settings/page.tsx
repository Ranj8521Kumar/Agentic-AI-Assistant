"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useChatStore } from "@/store/chatStore";
import { apiGet, apiPost, API_URL } from "@/lib/api";
import styles from "./settings.module.css";

interface Integration {
  provider: string;
  provider_email: string | null;
  connected_at: string;
  scopes: string | null;
}

const OAUTH_INTEGRATIONS = [
  { id: "google", label: "Gmail & Google Calendar", description: "Read/send emails, schedule meetings", href: `${API_URL}/auth/google/login?integration=true` },
  { id: "microsoft", label: "Outlook & Microsoft Teams", description: "Read/send emails, send Teams messages", href: `${API_URL}/auth/microsoft/login` },
  { id: "slack", label: "Slack", description: "Send and read Slack messages", href: `${API_URL}/auth/slack/login` },
];

const TOKEN_INTEGRATIONS = [
  { id: "jira", label: "Jira", description: "Create, update, and search Jira issues", placeholder: "Atlassian API token" },
  { id: "notion", label: "Notion", description: "Read and write Notion pages", placeholder: "Notion integration token" },
];

export default function SettingsPage() {
  const router = useRouter();
  const { user, logout } = useChatStore();
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [tokenInputs, setTokenInputs] = useState<Record<string, string>>({});
  const [emailInputs, setEmailInputs] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [feedback, setFeedback] = useState<Record<string, string>>({});

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) { router.replace("/login"); return; }
    apiGet<Integration[]>("/integrations")
      .then(setIntegrations)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [router]);

  const isConnected = (id: string) => integrations.some(i => i.provider === id);
  const connectedEmail = (id: string) => integrations.find(i => i.provider === id)?.provider_email;

  const disconnect = async (provider: string) => {
    if (!confirm(`Disconnect ${provider}? This will stop the assistant from accessing it.`)) return;
    try {
      await apiPost(`/integrations/${provider}`, {});
    } catch {
      // DELETE — use fetch directly
      const token = localStorage.getItem("access_token");
      await fetch(`${API_URL}/integrations/${provider}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
    }
    setIntegrations(prev => prev.filter(i => i.provider !== provider));
    setFeedback(prev => ({ ...prev, [provider]: "Disconnected." }));
    setTimeout(() => setFeedback(prev => { const n = { ...prev }; delete n[provider]; return n; }), 3000);
  };

  const connectToken = async (provider: string) => {
    const t = tokenInputs[provider]?.trim();
    if (!t) return;
    setSaving(prev => ({ ...prev, [provider]: true }));
    try {
      const params = provider === "jira"
        ? `api_token=${encodeURIComponent(t)}&email=${encodeURIComponent(emailInputs[provider] || "")}`
        : `token=${encodeURIComponent(t)}`;
      const token = localStorage.getItem("access_token");
      const res = await fetch(`${API_URL}/integrations/${provider}/connect?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(await res.text());
      setFeedback(prev => ({ ...prev, [provider]: "Connected successfully!" }));
      const updated = await apiGet<Integration[]>("/integrations");
      setIntegrations(updated);
      setTokenInputs(prev => { const n = { ...prev }; delete n[provider]; return n; });
    } catch (e: unknown) {
      setFeedback(prev => ({ ...prev, [provider]: `Error: ${(e as Error).message}` }));
    } finally {
      setSaving(prev => ({ ...prev, [provider]: false }));
      setTimeout(() => setFeedback(prev => { const n = { ...prev }; delete n[provider]; return n; }), 4000);
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        {/* Header */}
        <div className={styles.header}>
          <button className={styles.back} onClick={() => router.push("/chat")} id="btn-back">
            ← Back to Chat
          </button>
          <h1 className={styles.title}>Settings</h1>
          <p className={styles.subtitle}>Manage your connected integrations and account.</p>
        </div>

        {/* OAuth integrations */}
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>OAuth Integrations</h2>
          <p className={styles.sectionDesc}>Click to connect via your provider's login page.</p>
          {OAUTH_INTEGRATIONS.map(int => (
            <div key={int.id} className={styles.card}>
              <div className={styles.cardInfo}>
                <span className={styles.cardLabel}>{int.label}</span>
                <span className={styles.cardDesc}>{int.description}</span>
                {isConnected(int.id) && (
                  <span className={styles.connectedEmail}>{connectedEmail(int.id)}</span>
                )}
              </div>
              <div className={styles.cardActions}>
                {feedback[int.id] && <span className={styles.feedback}>{feedback[int.id]}</span>}
                {isConnected(int.id) ? (
                  <>
                    <span className={styles.badge}>Connected</span>
                    <button className={styles.disconnectBtn} onClick={() => disconnect(int.id)} id={`disconnect-${int.id}`}>
                      Disconnect
                    </button>
                  </>
                ) : (
                  <a href={int.href} className={styles.connectBtn} id={`connect-${int.id}`}>
                    Connect
                  </a>
                )}
              </div>
            </div>
          ))}
        </section>

        {/* Token-based integrations */}
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>API Token Integrations</h2>
          <p className={styles.sectionDesc}>Paste your API token to connect.</p>
          {TOKEN_INTEGRATIONS.map(int => (
            <div key={int.id} className={styles.card}>
              <div className={styles.cardInfo}>
                <span className={styles.cardLabel}>{int.label}</span>
                <span className={styles.cardDesc}>{int.description}</span>
              </div>
              <div className={styles.cardActions}>
                {feedback[int.id] && <span className={styles.feedback}>{feedback[int.id]}</span>}
                {isConnected(int.id) ? (
                  <>
                    <span className={styles.badge}>Connected</span>
                    <button className={styles.disconnectBtn} onClick={() => disconnect(int.id)} id={`disconnect-${int.id}`}>
                      Disconnect
                    </button>
                  </>
                ) : (
                  <div className={styles.tokenForm}>
                    {int.id === "jira" && (
                      <input
                        className={styles.tokenInput}
                        placeholder="your@email.com"
                        value={emailInputs[int.id] || ""}
                        onChange={e => setEmailInputs(p => ({ ...p, [int.id]: e.target.value }))}
                        id={`email-${int.id}`}
                      />
                    )}
                    <input
                      className={styles.tokenInput}
                      type="password"
                      placeholder={int.placeholder}
                      value={tokenInputs[int.id] || ""}
                      onChange={e => setTokenInputs(p => ({ ...p, [int.id]: e.target.value }))}
                      id={`token-${int.id}`}
                    />
                    <button
                      className={styles.connectBtn}
                      onClick={() => connectToken(int.id)}
                      disabled={saving[int.id]}
                      id={`save-${int.id}`}
                    >
                      {saving[int.id] ? "Saving…" : "Save"}
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </section>

        {/* Account */}
        {user && (
          <section className={styles.section}>
            <h2 className={styles.sectionTitle}>Account</h2>
            <div className={styles.card}>
              <div className={styles.cardInfo}>
                <span className={styles.cardLabel}>{user.full_name || user.email}</span>
                <span className={styles.cardDesc}>{user.email}</span>
              </div>
              <div className={styles.cardActions}>
                <button className={styles.disconnectBtn} id="btn-logout-settings"
                  onClick={() => { logout(); router.replace("/login"); }}>
                  Sign Out
                </button>
              </div>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
