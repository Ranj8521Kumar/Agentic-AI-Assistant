/**
 * Zustand store for chat state.
 */

import { create } from "zustand";
import { Conversation, Message, ToolEvent, User } from "@/types";
import { streamChat, apiGet, apiDelete, apiPatch, setTokens, clearTokens } from "@/lib/api";

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
  deleteConversation: (id: string) => Promise<void>;
  renameConversation: (id: string, title: string) => Promise<void>;
  pinConversation: (id: string, pinned: boolean) => Promise<void>;

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

  deleteConversation: async (id: string) => {
    // Optimistic remove
    set((state) => ({
      conversations: state.conversations.filter((c) => c.id !== id),
      activeConversationId: state.activeConversationId === id ? null : state.activeConversationId,
      messages: state.activeConversationId === id ? [] : state.messages,
    }));
    try {
      await apiDelete(`/chat/conversations/${id}`);
    } catch {
      // Re-fetch to restore if request failed
      apiGet<Conversation[]>("/chat/conversations")
        .then((convos) => set({ conversations: convos }))
        .catch(() => {});
    }
  },

  renameConversation: async (id: string, title: string) => {
    // Optimistic update
    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id === id ? { ...c, title } : c
      ),
    }));
    try {
      await apiPatch(`/chat/conversations/${id}/rename`, { title });
    } catch {
      // Re-fetch on failure
      apiGet<Conversation[]>("/chat/conversations")
        .then((convos) => set({ conversations: convos }))
        .catch(() => {});
    }
  },

  pinConversation: async (id: string, pinned: boolean) => {
    // Optimistic update
    set((state) => {
      const updated = state.conversations.map((c) =>
        c.id === id ? { ...c, is_pinned: pinned } : c
      );
      // Re-sort: pinned first, then by updated_at desc
      updated.sort((a, b) => {
        if (a.is_pinned === b.is_pinned) {
          return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
        }
        return a.is_pinned ? -1 : 1;
      });
      return { conversations: updated };
    });
    try {
      await apiPatch(`/chat/conversations/${id}/pin`, { pinned });
    } catch {
      apiGet<Conversation[]>("/chat/conversations")
        .then((convos) => set({ conversations: convos }))
        .catch(() => {});
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
