"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useChatStore } from "@/store/chatStore";
import { Sidebar } from "@/components/layout/Sidebar";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { InputBar } from "@/components/chat/InputBar";
import { apiGet } from "@/lib/api";
import { Conversation, User } from "@/types";
import styles from "./chat.module.css";

export default function ChatPage() {
  const router = useRouter();
  const { user, setUser, setConversations, setAccessToken, logout } = useChatStore();

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    const refreshToken = localStorage.getItem("refresh_token");
    if (!token) {
      router.replace("/login");
      return;
    }
    setAccessToken(token, refreshToken);

    // Fetch current user and conversations in parallel
    Promise.all([
      apiGet<User>("/auth/me").then(setUser),
      apiGet<Conversation[]>("/chat/conversations").then(setConversations),
    ]).catch(() => {
      logout();
      router.replace("/login");
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className={styles.shell}>
      <Sidebar />
      <main className={styles.main}>
        <ChatWindow />
        <InputBar />
      </main>
    </div>
  );
}
