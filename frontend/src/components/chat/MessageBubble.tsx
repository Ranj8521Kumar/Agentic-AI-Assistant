"use client";

import { Message } from "@/types";
import { ToolCallCard } from "./ToolCallCard";
import styles from "./MessageBubble.module.css";

interface Props {
  message: Message;
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";

  return (
    <div className={`${styles.row} ${isUser ? styles.userRow : styles.assistantRow}`}>
      {isAssistant && (
        <div className={styles.avatar} aria-hidden="true">⬡</div>
      )}
      <div className={`${styles.bubble} ${isUser ? styles.userBubble : styles.assistantBubble}`}>
        {/* Tool call events */}
        {isAssistant && message.toolEvents && message.toolEvents.length > 0 && (
          <div className={styles.toolEvents}>
            {message.toolEvents.map((event, i) => (
              <ToolCallCard key={i} event={event} />
            ))}
          </div>
        )}

        {/* Message content */}
        {message.content && (
          <div
            className={`${styles.content} prose`}
            dangerouslySetInnerHTML={{
              __html: formatContent(message.content),
            }}
          />
        )}

        {/* Streaming cursor */}
        {message.isStreaming && !message.content && (
          <span className={styles.cursor} />
        )}
      </div>
    </div>
  );
}

/** Very simple markdown → HTML converter (no dependencies). */
function formatContent(text: string): string {
  // URL regex — matches http(s):// links
  const URL_RE = /(https?:\/\/[^\s<>"]+)/g;

  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\n/g, "<br/>")
    // Convert bare URLs into clickable links that wrap at any char
    .replace(
      URL_RE,
      (url) =>
        `<a href="${url}" target="_blank" rel="noopener noreferrer" ` +
        `style="color:var(--accent);word-break:break-all;overflow-wrap:anywhere;">${url}</a>`
    );
}

