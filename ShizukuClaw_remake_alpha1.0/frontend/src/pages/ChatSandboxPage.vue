<template>
  <section class="sandbox-page">
    <header class="sandbox-header">
      <h1>沙箱聊天</h1>
      <p>已迁移 chat-sandbox.html 核心结构，后续接入真实对话 API 与审批流程。</p>
    </header>

    <div class="sandbox-layout">
      <article class="panel sandbox-chat">
        <div class="chat-title">会话窗口</div>
        <div class="chat-messages">
          <div v-for="(item, index) in messages" :key="index" :class="['message', item.role === 'user' ? 'user' : 'bot']">
            {{ item.content }}
          </div>
        </div>
        <div class="chat-input">
          <select v-model="appStore.currentPersona" class="persona-select">
            <option v-for="persona in personaOptions" :key="persona.skill_id" :value="persona.skill_id">
              {{ persona.name }}
            </option>
          </select>
          <textarea v-model="message" placeholder="输入消息，将发送到后端智能体..." />
          <button type="button" class="btn" :disabled="appStore.loading" @click="sendMessage">
            {{ appStore.loading ? "发送中..." : "发送" }}
          </button>
        </div>
      </article>

      <article class="panel sandbox-side">
        <h2>工作模式</h2>

        <h2>快捷动作</h2>
        <div class="quick-actions-grid">
          <button type="button" class="btn ghost">运行诊断</button>
          <button type="button" class="btn ghost">查看日志</button>
          <button type="button" class="btn ghost">打开配置</button>
          <button type="button" class="btn ghost">刷新状态</button>
          <button type="button" class="btn ghost memory-trigger" @click="openPermanentMemory">查看永久记忆</button>
        </div>

        <section v-if="memoryVisible" class="memory-viewer">
          <div class="memory-viewer-header">
            <h2>永久记忆</h2>
            <div class="memory-viewer-actions">
              <button type="button" class="btn ghost" :disabled="memoryLoading" @click="refreshPermanentMemory">
                {{ memoryLoading ? "加载中..." : "刷新" }}
              </button>
              <button type="button" class="btn ghost" @click="memoryVisible = false">收起</button>
            </div>
          </div>
          <p v-if="memoryError" class="memory-error">{{ memoryError }}</p>
          <pre v-else-if="memoryLoading && !longTermMemory" class="memory-content">正在读取永久记忆...</pre>
          <pre v-else class="memory-content">{{ longTermMemory || "暂无永久记忆内容。" }}</pre>
          <details v-if="memoryMetaText" class="memory-meta">
            <summary>元信息</summary>
            <pre class="memory-content">{{ memoryMetaText }}</pre>
          </details>
        </section>

        <h2>审批队列</h2>
        <div class="approval-placeholder">暂无待审批项目</div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { storeToRefs } from "pinia";
import { useAppStore } from "../store/app";

const appStore = useAppStore();
const { personas } = storeToRefs(appStore);
const message = ref("");
const memoryVisible = ref(false);
const memoryLoading = ref(false);
const memoryError = ref("");
const longTermMemory = ref("");
const memoryMeta = ref<Record<string, unknown> | null>(null);
const messages = ref<Array<{ role: "user" | "bot"; content: string }>>([
  { role: "bot", content: "你好，我是沙箱助手。选择人格后可以直接对话。" }
]);
const personaOptions = computed(() =>
  personas.value.length
    ? personas.value
    : [
        { skill_id: "shizuku", name: "Shizuku" }
      ]
);

const memoryMetaText = computed(() => {
  if (!memoryMeta.value) {
    return "";
  }
  return JSON.stringify(memoryMeta.value, null, 2);
});

const sendMessage = async () => {
  const text = message.value.trim();
  if (!text) {
    return;
  }
  messages.value.push({ role: "user", content: text });
  message.value = "";
  try {
    const data = await appStore.chat(text);
    messages.value.push({ role: "bot", content: data.reply || "（空回复）" });
  } catch (error) {
    const err = error instanceof Error ? error.message : "发送失败";
    messages.value.push({ role: "bot", content: `发送失败: ${err}` });
  }
};

const refreshPermanentMemory = async () => {
  memoryLoading.value = true;
  memoryError.value = "";
  try {
    const response = await fetch("/api/agent/memory/long_term?include_meta=1", {
      method: "GET"
    });
    const data = await response.json();
    if (!response.ok || !data?.success) {
      throw new Error(data?.error || "读取永久记忆失败");
    }
    longTermMemory.value = String(data.long_term || "").trim();
    memoryMeta.value = data.meta ?? null;
  } catch (error) {
    memoryError.value = error instanceof Error ? error.message : "读取永久记忆失败";
  } finally {
    memoryLoading.value = false;
  }
};

const openPermanentMemory = async () => {
  memoryVisible.value = true;
  await refreshPermanentMemory();
};

onMounted(() => {
  void appStore.loadStatus();
});
</script>

<style scoped>
.persona-select {
  min-width: 140px;
  margin-right: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.45);
  background: #fff;
}

.memory-viewer {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.18);
}

.memory-viewer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.memory-viewer-header h2 {
  margin: 0;
}

.memory-viewer-actions {
  display: flex;
  gap: 8px;
}

.memory-error {
  margin-top: 10px;
  color: #f87171;
}

.memory-content {
  margin-top: 10px;
  padding: 10px;
  border-radius: 8px;
  max-height: 260px;
  overflow: auto;
  background: rgba(15, 23, 42, 0.45);
  color: #e2e8f0;
  white-space: pre-wrap;
  word-break: break-word;
}

.memory-meta {
  margin-top: 10px;
}

.memory-trigger {
  border-radius: 999px;
  border-color: rgba(16, 185, 129, 0.5);
  color: #065f46;
  background:
    linear-gradient(135deg, rgba(236, 253, 245, 0.96) 0%, rgba(220, 252, 231, 0.92) 100%);
  box-shadow: 0 3px 12px rgba(5, 150, 105, 0.14);
  transition: transform 0.18s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.memory-trigger:hover {
  border-color: rgba(16, 185, 129, 0.78);
  box-shadow: 0 8px 18px rgba(5, 150, 105, 0.18);
  transform: translateY(-1px);
}

.memory-trigger:focus-visible {
  outline: 2px solid rgba(16, 185, 129, 0.45);
  outline-offset: 1px;
}

.memory-trigger:active {
  transform: translateY(0);
  box-shadow: 0 4px 10px rgba(5, 150, 105, 0.15);
}
</style>
