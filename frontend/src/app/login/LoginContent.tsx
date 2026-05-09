"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { API_URL } from "@/lib/api";
import { useChatStore } from "@/store/chatStore";
import styles from "./login.module.css";

const PROVIDERS = [
  {
    id: "google",
    label: "Continue with Google",
    icon: (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none">
        <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
        <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
        <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/>
        <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
      </svg>
    ),
    href: `${API_URL}/auth/google/login`,
  },
  {
    id: "microsoft",
    label: "Continue with Microsoft",
    icon: (
      <svg viewBox="0 0 24 24" width="18" height="18">
        <path d="M11.4 11.4H0V0h11.4v11.4z" fill="#F25022"/>
        <path d="M24 11.4H12.6V0H24v11.4z" fill="#7FBA00"/>
        <path d="M11.4 24H0V12.6h11.4V24z" fill="#00A4EF"/>
        <path d="M24 24H12.6V12.6H24V24z" fill="#FFB900"/>
      </svg>
    ),
    href: `${API_URL}/auth/microsoft/login`,
  },
  {
    id: "slack",
    label: "Continue with Slack",
    icon: (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none">
        <path d="M5.042 15.165a2.528 2.528 0 01-2.52 2.521A2.528 2.528 0 010 15.165a2.527 2.527 0 012.522-2.52h2.52v2.52zm1.271 0a2.527 2.527 0 012.521-2.52 2.527 2.527 0 012.521 2.52v6.313A2.528 2.528 0 018.834 24a2.528 2.528 0 01-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 01-2.521-2.52A2.528 2.528 0 018.834 0a2.527 2.527 0 012.521 2.522v2.52H8.834zm0 1.271a2.527 2.527 0 012.521 2.521 2.527 2.527 0 01-2.521 2.521H2.522A2.528 2.528 0 010 8.834a2.528 2.528 0 012.522-2.521h6.312zm10.122 2.521a2.528 2.528 0 012.522-2.521A2.528 2.528 0 0124 8.834a2.527 2.527 0 01-2.522 2.521h-2.522V8.834zm-1.268 0a2.527 2.527 0 01-2.523 2.521 2.526 2.526 0 01-2.52-2.521V2.522A2.527 2.527 0 0115.165 0a2.528 2.528 0 012.523 2.522v6.312zm-2.523 10.122a2.528 2.528 0 012.523 2.522A2.528 2.528 0 0115.165 24a2.527 2.527 0 01-2.52-2.522v-2.522h2.52zm0-1.268a2.527 2.527 0 01-2.52-2.523 2.526 2.526 0 012.52-2.52h6.313A2.527 2.527 0 0124 15.165a2.528 2.528 0 01-2.522 2.523h-6.313z" fill="#E01E5A"/>
      </svg>
    ),
    href: `${API_URL}/auth/slack/login`,
  },
];

export default function LoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { setUser, setAccessToken } = useChatStore();

  useEffect(() => {
    const token = searchParams.get("access_token");
    const refreshToken = searchParams.get("refresh_token");
    const userStr = searchParams.get("user");
    if (token && userStr) {
      try {
        const user = JSON.parse(decodeURIComponent(userStr));
        setAccessToken(token, refreshToken ?? undefined);
        setUser(user);
        router.replace("/chat");
        return;
      } catch {
        // ignore malformed params
      }
    }
    const existing = localStorage.getItem("access_token");
    if (existing) router.replace("/chat");
  }, [searchParams, router, setAccessToken, setUser]);

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <div className={styles.logo}>
          <span className={styles.logoIcon}>⬡</span>
          <span className={styles.logoText}>Agentic AI</span>
        </div>
        <h1 className={styles.title}>Enterprise Assistant</h1>
        <p className={styles.subtitle}>
          Control Gmail, Slack, Teams, Calendar, Jira and Notion
          <br />entirely through natural language chat.
        </p>
        <div className={styles.providers}>
          {PROVIDERS.map((p) => (
            <a key={p.id} href={p.href} className={styles.providerBtn} id={`oauth-${p.id}`}>
              {p.icon}
              <span>{p.label}</span>
            </a>
          ))}
        </div>
        <p className={styles.footer}>
          By signing in, you agree to our Terms of Service and Privacy Policy.
          <br />Your tokens are encrypted at rest and never shared.
        </p>
      </div>
    </div>
  );
}
