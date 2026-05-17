"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useChatStore } from "@/store/chatStore";
import { Conversation } from "@/types";
import styles from "./Sidebar.module.css";

const INTEGRATIONS = [
  { id: "google", label: "Gmail / Calendar", icon: "✉" },
  { id: "microsoft", label: "Outlook / Teams", icon: "📧" },
  { id: "slack", label: "Slack", icon: "#" },
  { id: "jira", label: "Jira", icon: "⬟" },
  { id: "notion", label: "Notion", icon: "N" },
];

// ── Context menu ─────────────────────────────────────────────────────────────

interface ContextMenuState {
  conversationId: string;
  x: number;
  y: number;
}

// ── Rename inline input ───────────────────────────────────────────────────────

interface ConvItemProps {
  conversation: Conversation;
  isActive: boolean;
  onSelect: () => void;
  onMenuOpen: (e: React.MouseEvent, id: string) => void;
  renamingId: string | null;
  onRenameCommit: (id: string, title: string) => void;
  onRenameCancel: () => void;
}

function ConvItem({
  conversation: c,
  isActive,
  onSelect,
  onMenuOpen,
  renamingId,
  onRenameCommit,
  onRenameCancel,
}: ConvItemProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const isRenaming = renamingId === c.id;

  useEffect(() => {
    if (isRenaming && inputRef.current) {
      inputRef.current.value = c.title || "Untitled";
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isRenaming, c.title]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      const val = inputRef.current?.value.trim();
      if (val) onRenameCommit(c.id, val);
      else onRenameCancel();
    } else if (e.key === "Escape") {
      onRenameCancel();
    }
  };

  return (
    <div
      className={`${styles.convItem} ${isActive ? styles.active : ""}`}
      id={`conv-${c.id}`}
    >
      {c.is_pinned && <span className={styles.pinIcon} title="Pinned">📌</span>}

      {isRenaming ? (
        <input
          ref={inputRef}
          className={styles.renameInput}
          onKeyDown={handleKeyDown}
          onBlur={() => {
            const val = inputRef.current?.value.trim();
            if (val) onRenameCommit(c.id, val);
            else onRenameCancel();
          }}
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <button
          className={styles.convBtn}
          onClick={onSelect}
          title={c.title || "Untitled"}
        >
          <span className={styles.convTitle}>{c.title || "Untitled"}</span>
        </button>
      )}

      {!isRenaming && (
        <button
          className={styles.menuTrigger}
          id={`conv-menu-${c.id}`}
          title="More options"
          onClick={(e) => onMenuOpen(e, c.id)}
          aria-label="More options"
        >
          ···
        </button>
      )}
    </div>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────

export function Sidebar() {
  const router = useRouter();
  const {
    user,
    conversations,
    activeConversationId,
    setActiveConversation,
    deleteConversation,
    renameConversation,
    pinConversation,
    logout,
  } = useChatStore();

  const connected = user?.connected_providers ?? [];

  const [menu, setMenu] = useState<ContextMenuState | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenu(null);
        setDeleteConfirmId(null);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const openMenu = useCallback((e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    e.preventDefault();
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setMenu({ conversationId: id, x: rect.right + 4, y: rect.top });
    setDeleteConfirmId(null);
  }, []);

  const closeMenu = () => {
    setMenu(null);
    setDeleteConfirmId(null);
  };

  const handleRename = () => {
    if (!menu) return;
    setRenamingId(menu.conversationId);
    closeMenu();
  };

  const handleRenameCommit = (id: string, title: string) => {
    renameConversation(id, title);
    setRenamingId(null);
  };

  const handlePin = (pinned: boolean) => {
    if (!menu) return;
    pinConversation(menu.conversationId, pinned);
    closeMenu();
  };

  const handleDeleteClick = () => {
    if (!menu) return;
    setDeleteConfirmId(menu.conversationId);
  };

  const handleDeleteConfirm = () => {
    if (!deleteConfirmId) return;
    deleteConversation(deleteConfirmId);
    closeMenu();
  };

  // Separate pinned vs unpinned
  const pinned = conversations.filter((c) => c.is_pinned);
  const recents = conversations.filter((c) => !c.is_pinned);

  const menuConvo = menu ? conversations.find((c) => c.id === menu.conversationId) : null;

  return (
    <>
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
          {conversations.length === 0 ? (
            <p className={styles.empty}>No conversations yet</p>
          ) : (
            <>
              {pinned.length > 0 && (
                <>
                  <p className={styles.sectionLabel}>📌 Pinned</p>
                  {pinned.map((c) => (
                    <ConvItem
                      key={c.id}
                      conversation={c}
                      isActive={c.id === activeConversationId}
                      onSelect={() => setActiveConversation(c.id)}
                      onMenuOpen={openMenu}
                      renamingId={renamingId}
                      onRenameCommit={handleRenameCommit}
                      onRenameCancel={() => setRenamingId(null)}
                    />
                  ))}
                </>
              )}

              {recents.length > 0 && (
                <>
                  <p className={styles.sectionLabel}>Recents</p>
                  {recents.map((c) => (
                    <ConvItem
                      key={c.id}
                      conversation={c}
                      isActive={c.id === activeConversationId}
                      onSelect={() => setActiveConversation(c.id)}
                      onMenuOpen={openMenu}
                      renamingId={renamingId}
                      onRenameCommit={handleRenameCommit}
                      onRenameCancel={() => setRenamingId(null)}
                    />
                  ))}
                </>
              )}
            </>
          )}
        </nav>

        <div className={styles.spacer} />

        {/* Settings link */}
        <Link href="/settings" className={styles.settingsLink} id="link-settings">
          <span>⚙</span>
          <span>Settings &amp; Integrations</span>
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

      {/* Floating context menu — rendered outside aside to avoid clipping */}
      {menu && (
        <div
          ref={menuRef}
          className={styles.contextMenu}
          style={{ top: menu.y, left: menu.x }}
          role="menu"
          id={`ctx-menu-${menu.conversationId}`}
        >
          {deleteConfirmId === menu.conversationId ? (
            <div className={styles.deleteConfirm}>
              <p className={styles.confirmText}>Delete this chat?</p>
              <div className={styles.confirmButtons}>
                <button
                  className={`${styles.menuItem} ${styles.danger}`}
                  onClick={handleDeleteConfirm}
                  id={`btn-confirm-delete-${menu.conversationId}`}
                >
                  🗑 Delete
                </button>
                <button className={styles.menuItem} onClick={closeMenu}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <>
              <button
                className={styles.menuItem}
                onClick={handleRename}
                id={`btn-rename-${menu.conversationId}`}
                role="menuitem"
              >
                ✏️ Rename
              </button>
              {menuConvo?.is_pinned ? (
                <button
                  className={styles.menuItem}
                  onClick={() => handlePin(false)}
                  id={`btn-unpin-${menu.conversationId}`}
                  role="menuitem"
                >
                  📌 Unpin
                </button>
              ) : (
                <button
                  className={styles.menuItem}
                  onClick={() => handlePin(true)}
                  id={`btn-pin-${menu.conversationId}`}
                  role="menuitem"
                >
                  📌 Pin
                </button>
              )}
              <div className={styles.menuDivider} />
              <button
                className={`${styles.menuItem} ${styles.danger}`}
                onClick={handleDeleteClick}
                id={`btn-delete-${menu.conversationId}`}
                role="menuitem"
              >
                🗑 Delete
              </button>
            </>
          )}
        </div>
      )}
    </>
  );
}
