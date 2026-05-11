"use client";

import { Message } from "@/types";
import { ToolCallCard } from "./ToolCallCard";
import styles from "./MessageBubble.module.css";
import { marked, Tokens } from "marked";
import { useState, useEffect, useRef } from "react";

interface Props {
  message: Message;
}

// ── marked configuration ──────────────────────────────────────────────────────
// Force synchronous mode so it works correctly during rapid streaming re-renders
const renderer = new marked.Renderer();

// Open all links in a new tab
renderer.link = ({ href, title, tokens }: Tokens.Link) => {
  const text = tokens.map((t) => ("text" in t ? t.text : "")).join("");
  const titleAttr = title ? ` title="${title}"` : "";
  return `<a href="${href}"${titleAttr} target="_blank" rel="noopener noreferrer">${text}</a>`;
};

marked.setOptions({
  gfm: true,    // GitHub Flavored Markdown (tables, task lists, strikethrough)
  breaks: true, // Convert \n → <br> inside paragraphs
  renderer,
});

/** Parse markdown → HTML string. Always synchronous. */
function renderMarkdown(text: string): string {
  if (!text) return "";
  // Pass async:false to guarantee a string return (not a Promise)
  return marked.parse(text, { async: false }) as string;
}

export function MessageBubble({ message }: Props) {
  const isUser      = message.role === "user";
  const isAssistant = message.role === "assistant";

  // Maintain rendered HTML in local state so it updates on every content change,
  // including during streaming when chunks arrive rapidly.
  const [renderedHtml, setRenderedHtml] = useState(() =>
    renderMarkdown(message.content || "")
  );

  // Re-render markdown every time message.content changes (streaming chunks)
  useEffect(() => {
    setRenderedHtml(renderMarkdown(message.content || ""));
  }, [message.content]);

  const contentRef = useRef<HTMLDivElement>(null);

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

        {/* Message content — fully rendered markdown */}
        {message.content && (
          <div
            ref={contentRef}
            className={`${styles.content} ${styles.markdown}`}
            dangerouslySetInnerHTML={{ __html: renderedHtml }}
          />
        )}

        {/* Streaming cursor — only shown while streaming with no content yet */}
        {message.isStreaming && !message.content && (
          <span className={styles.cursor} />
        )}
      </div>
    </div>
  );
}
