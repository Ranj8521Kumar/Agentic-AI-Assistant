"use client";

import { useRef, useState, KeyboardEvent } from "react";
import { useChatStore } from "@/store/chatStore";
import styles from "./InputBar.module.css";

export function InputBar() {
  const [value, setValue] = useState("");
  const { sendMessage, stopStreaming, isStreaming } = useChatStore();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    const text = value.trim();
    if (!text || isStreaming) return;
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
    sendMessage(text);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  };

  return (
    <div className={styles.wrapper}>
      <div className={styles.bar}>
        <textarea
          ref={textareaRef}
          id="chat-input"
          className={styles.input}
          placeholder="Message the assistant… (Shift+Enter for new line)"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          rows={1}
          disabled={false}
          aria-label="Chat message input"
        />
        <button
          id="btn-send"
          className={`${styles.sendBtn} ${isStreaming ? styles.stop : ""}`}
          onClick={isStreaming ? stopStreaming : handleSend}
          aria-label={isStreaming ? "Stop" : "Send"}
          title={isStreaming ? "Stop generating" : "Send message"}
        >
          {isStreaming ? (
            <span className={styles.stopIcon}>■</span>
          ) : (
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
              <path d="M2 21l21-9L2 3v7l15 2-15 2v7z"/>
            </svg>
          )}
        </button>
      </div>
      <p className={styles.hint}>
        AI can make mistakes. Always review actions before they're executed.
      </p>
    </div>
  );
}
