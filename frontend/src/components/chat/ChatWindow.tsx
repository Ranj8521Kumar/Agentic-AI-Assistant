"use client";

import { useEffect, useRef } from "react";
import { useChatStore } from "@/store/chatStore";
import { MessageBubble } from "./MessageBubble";
import styles from "./ChatWindow.module.css";

const SUGGESTED_PROMPTS = [
  "Read my last 5 emails",
  "Send a Slack message to #general",
  "Schedule a meeting tomorrow at 10am",
  "Create a Jira task: Review Q2 roadmap",
  "Show my upcoming calendar events",
];

export function ChatWindow() {
  const { messages, isStreaming, sendMessage } = useChatStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const isEmpty = messages.length === 0;

  return (
    <div className={styles.window}>
      {isEmpty ? (
        <div className={styles.empty}>
          <div className={styles.emptyLogo}>⬡</div>
          <h2 className={styles.emptyTitle}>How can I help you today?</h2>
          <p className={styles.emptySubtitle}>
            Ask me to send emails, post Slack messages, schedule meetings,
            create Jira issues, or read your Notion pages.
          </p>
          <div className={styles.prompts}>
            {SUGGESTED_PROMPTS.map((p, i) => (
              <button
                key={i}
                id={`prompt-${i}`}
                className={styles.promptBtn}
                onClick={() => sendMessage(p)}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className={styles.messages}>
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          {isStreaming && (
            <div className={styles.typingIndicator} aria-label="Assistant is typing">
              <span />
              <span />
              <span />
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}
