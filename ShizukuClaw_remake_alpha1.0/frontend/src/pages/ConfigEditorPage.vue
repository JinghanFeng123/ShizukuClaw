<template>
  <section class="config-page">
    <header class="config-header">
      <h1>配置编辑器</h1>
      <p>只需配置一个主模型。聊天和识图都走这一套。</p>
    </header>

    <div v-if="status.message" :class="['config-status', status.type]">
      {{ status.message }}
    </div>

    <form class="config-form" @submit.prevent="saveConfig">
      <article class="panel">
        <h2>主模型</h2>
        <div class="field-grid two-col">
          <label>
            模型名
            <input v-model="form.llm.model" type="text" placeholder="gpt-4o-mini" />
          </label>
          <label>
            Base URL
            <input v-model="form.llm.base_url" type="text" placeholder="https://api.openai.com/v1" />
          </label>
          <label>
            API Key
            <input v-model="form.llm.api_key" type="password" placeholder="留空表示不修改" />
          </label>
        </div>
      </article>

      <article class="panel">
        <h2>数据库配置</h2>
        <div class="field-grid two-col">
          <label>
            主机地址
            <input v-model="form.database.host" type="text" />
          </label>
          <label>
            用户名
            <input v-model="form.database.user" type="text" />
          </label>
          <label>
            密码
            <input v-model="form.database.password" type="password" />
          </label>
          <label>
            数据库名
            <input v-model="form.database.database" type="text" />
          </label>
        </div>
      </article>

      <article class="panel">
        <h2>角色配置</h2>
        <div class="field-grid two-col">
          <label>
            角色名称
            <input v-model="form.character.name" type="text" />
          </label>
          <label>
            角色性格
            <input v-model="form.character.personality" type="text" />
          </label>
          <label>
            哥哥QQ号
            <input v-model="form.character.brother_qqid" type="text" />
          </label>
          <label>
            身高
            <input v-model="form.character.height" type="text" />
          </label>
          <label>
            体重
            <input v-model="form.character.weight" type="text" />
          </label>
          <label>
            口癖(逗号分隔)
            <input v-model="form.character.catchphrases" type="text" />
          </label>
        </div>
      </article>

      <div class="config-actions">
        <button type="submit" class="btn" :disabled="loading">
          {{ loading ? "保存中..." : "保存配置" }}
        </button>
        <button type="button" class="btn ghost" :disabled="loading" @click="resetConfig">重置</button>
      </div>
    </form>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";

type ConfigData = {
  database: {
    host: string;
    user: string;
    password: string;
    database: string;
  };
  llm: {
    model: string;
    base_url: string;
    api_key: string;
  };
  character: {
    name: string;
    personality: string;
    brother_qqid: string;
    height: string;
    weight: string;
    catchphrases: string;
  };
};

const createEmptyForm = (): ConfigData => ({
  database: { host: "", user: "", password: "", database: "" },
  llm: { model: "", base_url: "", api_key: "" },
  character: {
    name: "",
    personality: "",
    brother_qqid: "",
    height: "",
    weight: "",
    catchphrases: ""
  }
});

const form = reactive<ConfigData>(createEmptyForm());
const loading = ref(false);
const status = reactive<{ type: "success" | "error"; message: string }>({
  type: "success",
  message: ""
});

const applyConfig = (incoming: Partial<ConfigData> & { llm?: Partial<ConfigData["llm"]> }) => {
  const next = createEmptyForm();
  next.database.host = incoming.database?.host ?? "";
  next.database.user = incoming.database?.user ?? "";
  next.database.password = incoming.database?.password ?? "";
  next.database.database = incoming.database?.database ?? "";
  next.llm.model = incoming.llm?.model ?? "";
  next.llm.base_url = incoming.llm?.base_url ?? "";
  next.llm.api_key = "";
  next.character.name = incoming.character?.name ?? "";
  next.character.personality = incoming.character?.personality ?? "";
  next.character.brother_qqid = incoming.character?.brother_qqid ?? "";
  next.character.height = incoming.character?.height ?? "";
  next.character.weight = incoming.character?.weight ?? "";
  next.character.catchphrases = incoming.character?.catchphrases ?? "";
  Object.assign(form, next);
};

const setStatus = (type: "success" | "error", message: string) => {
  status.type = type;
  status.message = message;
};

const loadCurrentConfig = async () => {
  loading.value = true;
  try {
    const response = await fetch("/api/config");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const config = (await response.json()) as Partial<ConfigData>;
    applyConfig(config);
    setStatus("success", "配置加载成功");
  } catch (error) {
    const message = error instanceof Error ? error.message : "未知错误";
    setStatus("error", `加载配置失败: ${message}`);
  } finally {
    loading.value = false;
  }
};

const resetConfig = async () => {
  await loadCurrentConfig();
};

const saveConfig = async () => {
  loading.value = true;
  try {
    const response = await fetch("/api/config", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(form)
    });

    if (!response.ok) {
      let errMsg = `HTTP ${response.status}`;
      try {
        const payload = (await response.json()) as { error?: string };
        errMsg = payload.error ?? errMsg;
      } catch {
        // ignore parse error
      }
      throw new Error(errMsg);
    }

    setStatus("success", "配置保存成功");
  } catch (error) {
    const message = error instanceof Error ? error.message : "未知错误";
    setStatus("error", `保存配置失败: ${message}`);
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  loadCurrentConfig();
});
</script>
