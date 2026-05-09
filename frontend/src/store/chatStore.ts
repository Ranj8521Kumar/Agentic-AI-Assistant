/**
 * Zustand store for chat state.
 */

import { create } from "zustand";
import { Conversation, Message, ToolEvent, User } from "@/types";
import { streamChat, apiGet, setTokens, clearTokens } from "@/lib/api";

const TOOL_EVENT_PREFIX = "__tool_event__:";

interface ChatStore {
  // Auth
  user: User | null;
  accessToken: string | null;
  setUser: (user: User | null) => void;
  setAccessToken: (token: string | null, refreshToken?: string | null) => void;
  logout: () => void;

  // Conversations
  conversations: Conversation[];
  activeConversationId: string | null;
  setConversations: (convos: Conversation[]) => void;
  setActiveConversation: (id: string | null) => void;

  // Messages
  messages: Message[];
  setMessages: (messages: Message[]) => void;
  addMessage: (message: Message) => void;

  // Streaming state
  isStreaming: boolean;
  abortController: AbortController | null;

  // Send a message (triggers streaming)
  sendMessage: (text: string) => void;
  stopStreaming: () => void;
}

export const useChatStore = create<ChatStore>((set, get) => ({
  // ── Auth ────────────────────────────────────────────────────────────────
  user: null,
  accessToken: null,
  setUser: (user) => set({ user }),
  setAccessToken: (token, refreshToken) => {
    set({ accessToken: token });
    if (token) {
      localStorage.setItem("access_token", token);
      if (refreshToken) localStorage.setItem("refresh_token", refreshToken);
    } else {
      clearTokens();
    }
  },
  logout: () => {
    clearTokens();
    set({
      user: null,
      accessToken: null,
      messages: [],
      conversations: [],
      activeConversationId: null,
    });
  },

  // ── Conversations ────────────────────────────────────────────────────────
  conversations: [],
  activeConversationId: null,
  setConversations: (conversations) => set({ conversations }),

  setActiveConversation: (id) => {
    set({ activeConversationId: id, messages: [] });

    // Load conversation history from backend when selecting an existing conversation
    if (id) {
      apiGet<Array<{
        id: string;
        role: "user" | "assistant" | "system" | "tool";
        content: string | null;
        tool_calls: unknown[] | null;
        created_at: string;
      }>>(`/chat/conversations/${id}/messages`)
        .then((msgs) => {
          const mapped: Message[] = msgs.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            tool_calls: m.tool_calls as Message["tool_calls"],
            created_at: m.created_at,
          }));
          // Only update if this conversation is still active
          if (get().activeConversationId === id) {
            set({ messages: mapped });
          }
        })
        .catch(() => {
          // Silent fail — user still sees empty conversation
        });
    }
  },

  // ── Messages ─────────────────────────────────────────────────────────────
  messages: [],
  setMessages: (messages) => set({ messages }),
  addMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),

  // ── Streaming ─────────────────────────────────────────────────────────────
  isStreaming: false,
  abortController: null,

  sendMessage: (text: string) => {
    const { activeConversationId, addMessage } = get();

    // Add user message immediately
    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    addMessage(userMsg);

    // Add placeholder assistant message
    const assistantMsgId = `assistant-${Date.now()}`;
    const assistantMsg: Message = {
      id: assistantMsgId,
      role: "assistant",
      content: "",
      created_at: new Date().toISOString(),
      isStreaming: true,
      toolEvents: [],
    };
    addMessage(assistantMsg);

    set({ isStreaming: true });

    const controller = streamChat(
      text,
      activeConversationId,
      // onChunk
      (chunk: string) => {
        if (chunk.startsWith(TOOL_EVENT_PREFIX)) {
          try {
            const event: ToolEvent = JSON.parse(chunk.slice(TOOL_EVENT_PREFIX.length));
            set((state) => ({
              messages: state.messages.map((m) =>
                m.id === assistantMsgId
                  ? { ...m, toolEvents: [...(m.toolEvents || []), event] }
                  : m
              ),
            }));
          } catch {
            // ignore malformed tool events
          }
        } else {
          set((state) => ({
            messages: state.messages.map((m) =>
              m.id === assistantMsgId
                ? { ...m, content: (m.content || "") + chunk }
                : m
            ),
          }));
        }
      },
      // onDone
      (newConversationId: string | null) => {
        const finalId = newConversationId || get().activeConversationId;
        set((state) => ({
          isStreaming: false,
          abortController: null,
          activeConversationId: finalId,
          messages: state.messages.map((m) =>
            m.id === assistantMsgId ? { ...m, isStreaming: false } : m
          ),
        }));
        // Refresh conversation list to show new/updated convo
        apiGet<Conversation[]>("/chat/conversations")
          .then((convos) => set({ conversations: convos }))
          .catch(() => {});
      },
      // onError
      (err: Error) => {
        set((state) => ({
          isStreaming: false,
          abortController: null,
          messages: state.messages.map((m) =>
            m.id === assistantMsgId
              ? { ...m, content: `⚠️ Error: ${err.message}`, isStreaming: false }
              : m
          ),
        }));
      }
    );

    set({ abortController: controller });
  },

  stopStreaming: () => {
    const { abortController } = get();
    if (abortController) {
      abortController.abort();
      set({ isStreaming: false, abortController: null });
    }
  },
}));
