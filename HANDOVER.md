# AstrBot BlogWriter 项目交接与开发指南 (HANDOVER)

> 本文档用于在新的对话会话中快速为 AI 助手或开发者提供上下文，涵盖架构设计、博客契约、外部依赖及规范守则。

---

## 📌 一、项目定位与基础信息

- **项目名称**：`AstrBot-BlogWriter`（插件唯一标识：`astrbot_plugin_blog_writer`）
- **本地代码目录**：`F:\GitHub\Blog-astrbot`
- **目标博客仓库（生产端）**：
  - 本地仓库：`F:\GitHub\Blog-plus`
  - GitHub 远程仓库：`mengkuikun/Blog-2.0`（分支：`main`，历史曾用 `tianshihao2003/dumplingandcakeblog`）
  - 博客生产域名：`https://imki.cn`（EdgeOne Pages 托管，GitHub `push main` 自动构建部署）
- **自建图床服务**：
  - 上传地址：`https://img.imki.cn/upload`（基于 Cloudflare/HuggingFace 自建）
  - 目录划分惯例：动态进 `blog/moments`，相册进 `blog/album/<相册名>`，番剧进 `blog/bangumi`
- **支持接入平台**：`weixin_oc`（微信公众号/企业微信）、`aiocqhttp`（QQ）
- **开发与运行环境**：Python 3.11+，AstrBot `>=4.22.0`

---

## 🏗️ 二、核心架构与分层硬性边界

项目采用严格的**纯逻辑层与框架粘合层隔离**模式，禁止混淆两者依赖：

```text
               ┌────────────────────────────────────────────────────────┐
               │                        main.py                         │
               │  - AstrBot Star 插件接入 (@filter.event_message_type) │
               │  - 会话状态机 (_sessions) 与交互流                    │
               │  - 外部 I/O：GitHub API (PUT/GET)、图床上传、网络拉取    │
               └──────────────────────────┬─────────────────────────────┘
                                          │ 传递数据与调用
                                          ▼
               ┌────────────────────────────────────────────────────────┐
               │                  blog_writer_core.py                   │
               │  - 纯 Python 逻辑层：指令解析、交互向导状态机           │
               │  - Frontmatter / YAML / Markdown 内容拼装与生成        │
               │  - 请求体构造与 API 响应数据解析                       │
               │  🚨 铁律：严禁 import astrbot，必须保持 100% 独立单测   │
               └────────────────────────────────────────────────────────┘
```

1. **`blog_writer_core.py`**：纯逻辑层，绝不调用任何 AstrBot 特有 API，保证纯 Python 标准库 + 基础依赖即可独立执行单测。
2. **`main.py`**：框架胶水层。所有网络调用（`httpx`）、会话存储、消息回复（`yield event.plain_result(...)`）在此实现。
3. **`_conf_schema.json`**：WebUI 配置定义文件。新增配置项必须在此声明默认值和类型，并在 `main.py` 的 `_cfg()` 中读取。
4. **`metadata.yaml`**：插件元数据。`name` 必须以 `astrbot_plugin_` 为前缀；内部 `version` 声明保持 `v1.0.0`。
5. **`tests/`**：
   - `test_core.py`：对 `blog_writer_core.py` 的单元测试；
   - `test_smoke.py`：Stub 了 AstrBot 模块的冒烟测试。
   - **当前状态**：189 个测试用例，运行 `python -m unittest discover -s tests` 全部通过。

---

## 📝 三、博客端（Blog-plus）集合契约与最新规则

插件向博客仓库 `src/content/` 写入 Markdown 文件触发生产构建。**生成的 Frontmatter 必须与博客端 `src/content.config.ts` 中的 Zod Schema 严格对齐**：

### 1. 动态说说 (`src/content/moments/YYYY-MM-DD-*.md`)
- **字段**：`title`, `published` (ISO 带时区), `tags: string[]`, `images: string[]`。
- 🚨 **重要避坑**：博客已移除了说说级别的 `author` 与 `avatar` 自定义字段（Schema 会自动提供默认作者），**插件严禁再写这两个字段**。图片自动上传到图床 `blog/moments`。

### 2. 笔记本笔记 (`src/content/life/notebooks/<分类>/YYYY-MM-DD-*.md`)
- **字段**：`title`, `published`, `description`, `tags`, `images: string[]`。
- 🚨 **重要避坑**：正文中不要散落普通 Markdown 图片语法，所有插图收集进 Frontmatter 的 `images` 数组（前端以瀑布流/九宫格展示）；若新建分类目录，必须配套生成 `_index.json` 定义元数据。

### 3. 记账账单 (`src/content/bills/YYYY-MM-DD-*.md`)
- **字段**：`title`, `amount` (float), `type` (`income` 或 `expense`), `category` (支持自定义), `account` (微信/支付宝/银行卡等), `date` ("YYYY-MM-DD"), `time` ("HH:mm")。
- 🚨 **重要避坑**：已彻底移除“负债/借款/欠款”类型，「还款」统一记为支出。支持自动从口语（如“下午3点打车12”）提取 `time: "15:30"`。

### 4. 日程提醒 (`src/content/schedules/YYYY-MM-DD-*.md`)
- **字段**：`title`, `date`, `time`, `status: "todo"`, `location`, `repeat`, `category` (schedule/birthday/anniversary/holiday), `isLunar`, `lunarMonth`, `lunarDay`。
- 插件本地通过 `data/schedules_reminder.json` 持久化任务，并通过 `apscheduler` 触发微信/QQ 定时提醒。

### 5. 网站导航 (`src/content/daohang/<分类文件夹>/*.md`)
- **字段**：`name`, `url`, `icon` (图标名), `description`。
- 🚨 **重要避坑**：**分类完全由所属文件夹决定**（如 `学习网站/`、`AI 工具/`），Frontmatter **绝对不要写 `category` 字段**。

### 6. 友情链接 (`src/content/friends/*.md`)
- **字段**：`name`, `url`, `avatar` (默认 `/avatar.jpg`), `description`, `tags`, `added` ("YYYY-MM-DD")。

### 7. 文章与转载 (`src/content/posts/<分类文件夹>/*.md`)
- **字段**：`title`, `published`, `description`, `tags`, `image` (封面大图)。
- 🚨 **重要避坑**：分类同样由存放的子目录决定，**不要写 `category` 字段**。博客前端集成了三合一手风琴引言卡（时效警示 + AI 摘要 + 封面折叠）。

---

## 🔍 四、本地当前状态（Working Tree）

在当前工作区中，已完成以下适配改造（未 Commit 状态，可直接在此基础上继续）：
1. **仓库地址**：统一迁移为 `mengkuikun/Blog-2.0`；
2. **图床地址**：统一默认指向自建图床 `https://img.imki.cn/upload`；
3. **回显主页**：新增 `blog_base_url`（默认 `https://imki.cn`），发布成功后在聊天窗口直接回显博客访问链接；
4. **友链头像**：默认指向 `/avatar.jpg`；
5. **单测状态**：189 个测试通过，无语法与断言错误。

---

## 🚀 五、发版与打包交付规范

开发新功能或修复缺陷后，必须按以下标准流程交付：

1. **测试前置**：
   ```bash
   python -m unittest discover -s tests
   ```
   必须确保 100% 通过。
2. **打包规范（严格 5 个文件）**：
   - 压缩包**只能包含**：`main.py`, `blog_writer_core.py`, `metadata.yaml`, `README.md`, `_conf_schema.json`；
   - 输出至插件根目录下的 `打包/` 目录，文件命名为：`AstrBot-BlogWriter-v1.0.X.zip`；
   - `打包/` 目录下**最多保留最近 10 个历史版本**，多余的旧包自动删除。
3. **推送远端**：
   - 提交信息：`feat: AstrBot BlogWriter 插件 v1.0.X`（或 `fix: ...`）；
   - 推送至 `origin main`（`https://github.com/mengkuikun/AstrBot-BlogWriter`）。

---

## 💬 六、新对话启动提示词（直接复制给新 AI）

在新对话建立时，直接将以下提示词发送给 AI 即可开始高效开发：

```markdown
你好！我现在要在当前会话中进行【AstrBot-BlogWriter】插件（项目路径：F:\GitHub\Blog-astrbot）的开发工作。
本项目是专门为我的个人博客（F:\GitHub\Blog-plus，线上地址 https://imki.cn，GitHub 仓库 mengkuikun/Blog-2.0）配套开发的微信/QQ 自动化内容发布机器人插件。

请先仔细阅读项目根目录下的 HANDOVER.md、AGENTS.md 和 DESIGN.md：
1. 严格遵守分层架构：blog_writer_core.py 严禁 import astrbot，必须保持纯 Python 逻辑可独立单测；
2. 生成的 Markdown 文件严格对齐博客端 src/content.config.ts 的 Zod Schema（分类由文件夹决定，不得写 category，账单无负债，动态无 author/avatar）；
3. 任何修改后必须运行 python -m unittest discover -s tests 确保 189+ 单测全绿；
4. 全程使用中文回复。

请确认你已完全阅读并理解上述规范，等待我的开发指令！
```
