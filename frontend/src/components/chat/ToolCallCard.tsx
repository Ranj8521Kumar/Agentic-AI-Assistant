"use client";

import { ToolEvent } from "@/types";
import styles from "./ToolCallCard.module.css";

const STATUS_ICONS: Record<string, string> = {
  running: "⟳",
  success: "✓",
  error: "✕",
  awaiting_confirmation: "?",
};

const TOOL_LABELS: Record<string, string> = {
  gmail_send_email: "Gmail · Send Email",
  gmail_read_inbox: "Gmail · Read Inbox",
  gmail_read_thread: "Gmail · Read Thread",
  slack_send_message: "Slack · Send Message",
  slack_read_channel: "Slack · Read Channel",
  calendar_schedule_meeting: "Calendar · Schedule Meeting",
  calendar_list_events: "Calendar · List Events",
  jira_create_issue: "Jira · Create Issue",
  jira_update_issue: "Jira · Update Issue",
  jira_search_issues: "Jira · Search Issues",
  notion_read_page: "Notion · Read Page",
  notion_append_page: "Notion · Append Page",
  outlook_send_email: "Outlook · Send Email",
  outlook_read_inbox: "Outlook · Read Inbox",
  teams_send_message: "Teams · Send Message",
};

interface Props {
  event: ToolEvent;
}

export function ToolCallCard({ event }: Props) {
  const label = TOOL_LABELS[event.tool] || event.tool;
  const icon = STATUS_ICONS[event.status] || "·";

  return (
    <div className={`${styles.card} ${styles[event.status]}`} role="status">
      <span className={styles.icon}>{icon}</span>
      <div className={styles.body}>
        <span className={styles.label}>{label}</span>
        {event.status === "running" && (
          <span className={styles.detail}>Running…</span>
        )}
        {event.status === "awaiting_confirmation" && (
          <span className={styles.detail}>Awaiting confirmation</span>
        )}
        {event.status === "error" && event.message && (
          <span className={styles.detail}>{event.message}</span>
        )}
        {event.status === "success" && event.result?.summary != null && (
          <span className={styles.detail}>{String(event.result.summary as string)}</span>
        )}
      </div>
    </div>
  );
}
