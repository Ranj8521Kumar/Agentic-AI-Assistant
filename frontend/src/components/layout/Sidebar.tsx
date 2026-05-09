"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useChatStore } from "@/store/chatStore";
import styles from "./Sidebar.module.css";

const INTEGRATIONS = [
  { id: "google", label: "Gmail / Calendar", icon: "✉" },
  { id: "microsoft", label: "Outlook / Teams", icon: "📧" },
  { id: "slack", label: "Slack", icon: "#" },
  { id: "jira", label: "Jira", icon: "⬟" },
  { id: "notion", label: "Notion", icon: "N" },
];

export function Sidebar() {
  const router = useRouter();
  const { user, conversations, activeConversationId, setActiveConversation, logout } = useChatStore();
  const connected = user?.connected_providers ?? [];

  return (
    <aside className={styles.sidebar}>
      {/* Logo */}
      <div className={styles.logo}>
        <span className={styles.logoIcon}>⬡</span>
        <span className={styles.logoName}>Agentic AI</span>
      </div>

      {/* New conversation */}
      <button
        className={styles.newChat}
        id="btn-new-chat"
        onClick={() => setActiveConversation(null)}
      >
        <span>＋</span>
        <span>New Chat</span>
      </button>

      {/* Conversations */}
      <nav className={styles.convList}>
        <p className={styles.sectionLabel}>Recents</p>
        {conversations.length === 0 ? (
          <p className={styles.empty}>No conversations yet</p>
        ) : (
          conversations.map((c) => (
            <button
              key={c.id}
              id={`conv-${c.id}`}
              className={`${styles.convItem} ${c.id === activeConversationId ? styles.active : ""}`}
              onClick={() => setActiveConversation(c.id)}
              title={c.title || "Untitled"}
            >
              <span className={styles.convTitle}>{c.title || "Untitled"}</span>
            </button>
          ))
        )}
      </nav>

      <div className={styles.spacer} />

      {/* Settings link */}
      <Link href="/settings" className={styles.settingsLink} id="link-settings">
        <span>⚙</span>
        <span>Settings & Integrations</span>
      </Link>

      {/* Integrations status */}
      <div className={styles.integrations}>
        <p className={styles.sectionLabel}>Integrations</p>
        {INTEGRATIONS.map((i) => {
          const isConnected = connected.includes(i.id);
          return (
            <div key={i.id} className={styles.integration}>
              <span className={styles.intIcon}>{i.icon}</span>
              <span className={styles.intLabel}>{i.label}</span>
              <span className={`${styles.intStatus} ${isConnected ? styles.connected : styles.disconnected}`}>
                {isConnected ? "●" : "○"}
              </span>
            </div>
          );
        })}
      </div>

      {/* User / logout */}
      {user && (
        <div className={styles.userRow}>
          <div className={styles.userInfo}>
            {user.avatar_url ? (
              <img src={user.avatar_url} alt="avatar" className={styles.avatar} />
            ) : (
              <div className={styles.avatarFallback}>
                {(user.full_name || user.email).charAt(0).toUpperCase()}
              </div>
            )}
            <div className={styles.userText}>
              <span className={styles.userName}>{user.full_name || user.email}</span>
              <span className={styles.userEmail}>{user.email}</span>
            </div>
          </div>
          <button
            className={styles.logoutBtn}
            id="btn-logout"
            onClick={() => {
              logout();
              router.replace("/login");
            }}
            title="Sign out"
          >
            ⎋
          </button>
        </div>
      )}
    </aside>
  );
}
