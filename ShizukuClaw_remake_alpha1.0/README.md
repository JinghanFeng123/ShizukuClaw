# ShizukuClaw Remake Alpha 1.0

前后端分离的本地智能体：LangGraph 路由 + Skill 人格 + MCP 插件 + SQLite 默认存储。

许可证：GPL-3.0

## 启动

Windows 一键启动（推荐）：

```bat
start-all.bat
```

或分别启动：

```bat
start-backend.bat
start-frontend.bat
```

手动启动：

```powershell
pip install -r requirements.txt
uvicorn app.main:app --reload
```

另开终端：

```powershell
cd frontend
npm run dev
```

- 前端: http://127.0.0.1:5173
- 后端端口自动选择：优先 8888，8000 被占用则换端口
- 实际端口写在 `data/dev_port.txt`，前端代理会读这个文件

`npm run dev` 会先跑 `scripts/auto-install.js`，自动补齐缺失的前端依赖。

## 存储

默认 SQLite：`data/storage/agent.db`

切换 MySQL / PostgreSQL：改 `config/storage.yaml` 的 `storage.driver`，并安装对应驱动。

```yaml
storage:
  driver: mysql   # sqlite | mysql | postgresql
```

## 人格

人格是 Skill，不是写死的子图。目录：`plugins/skills/*/SKILL.md`

内置：`companion` / `engineer` / `operator` / `iot`
