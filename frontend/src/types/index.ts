/**
 * TypeScript types for the Agentic AI Enterprise Assistant
 */

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  connected_providers: string[];
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string | null;
  tool_calls?: ToolCall[] | null;
  created_at: string;
  // Client-side only fields for streaming
  isStreaming?: boolean;
  toolEvents?: ToolEvent[];
}

export interface ToolCall {
  id: string;
  type: string;
  function: {
    name: string;
    arguments: string;
  };
}

export interface ToolEvent {
  tool: string;
  status: "running" | "success" | "error" | "awaiting_confirmation";
  args?: Record<string, unknown>;
  result?: Record<string, unknown>;
  message?: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}
