import { defineStore } from "pinia";

const API_BASE = import.meta.env.VITE_API_BASE || "";

type Persona = {
  skill_id: string;
  name: string;
  description?: string;
};

type ChatResponse = {
  success: boolean;
  persona: string;
  reply: string;
  memory?: unknown[];
  engine?: string;
  error?: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {})
    },
    ...init
  });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const message =
      typeof payload === "object" && payload && "error" in payload
        ? String((payload as { error?: string }).error)
        : `HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload as T;
}

export const useAppStore = defineStore("app", {
  state: () => ({
    counter: 0,
    apiBase: API_BASE || "/",
    personas: [] as Persona[],
    currentPersona: "shizuku",
    loading: false,
    lastReply: "",
    memoryText: "",
    memoryMeta: null as Record<string, unknown> | null
  }),
  actions: {
    increment() {
      this.counter += 1;
    },
    async loadStatus() {
      const data = await request<{
        personas?: Persona[];
        default_persona?: string;
      }>("/api/agent/status");
      this.personas = data.personas || [];
      if (data.default_persona) {
        this.currentPersona = data.default_persona;
      }
    },
    async chat(message: string) {
      this.loading = true;
      try {
        const data = await request<ChatResponse>("/api/chat", {
          method: "POST",
          body: JSON.stringify({
            message,
            persona: this.currentPersona
          })
        });
        this.lastReply = data.reply;
        return data;
      } finally {
        this.loading = false;
      }
    },
    async loadMemory() {
      const data = await request<{
        success: boolean;
        long_term?: string;
        meta?: Record<string, unknown>;
        error?: string;
      }>("/api/agent/memory/long_term?include_meta=1");
      this.memoryText = String(data.long_term || "").trim();
      this.memoryMeta = data.meta ?? null;
      return data;
    }
  }
});
