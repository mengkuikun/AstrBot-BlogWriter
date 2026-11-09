# AstrBot BlogWriter

通过微信（个人微信 / QQ 等 IM 平台）对话，直接发布博客内容到静态博客仓库（Firefly Astro）：

- **动态（moments）** —— 随手一条消息，图片自动上链
- **笔记（notebooks）** —— 分类 + 标题 + 正文，多段自动拼接
- **足迹（places）** —— 输入地名，坐标由高德地理编码自动获取
- **友链（friends）** —— 键值对文本自动识别字段，一键上链
- **相册（album）** —— 报个相册名直接发图，图片进图床 `blog/album/<相册名>`，博客动态加载

图片自动上传 CloudFlare-ImgBed 图床，内容生成 markdown（严格对齐博客 zod schema）后通过 GitHub API 提交 main 分支，触发 Actions 构建与 EdgeOne Pages 自动部署，全链路零人工干预。

## 功能特性

- ✅ 微信对话直接发布动态 / 笔记 / 足迹 / 友链 / 相册 / 账单 / 日程（全部命令式，2026-08 起移除 AI 抽取，纯正则解析零外部 AI 依赖）
- ✅ **自然语言正则记账 + 支出/收入两类型**（2026-09-05 对齐博客去负债后的模型）：`/账单 今天午餐微信花了32`（支出）/ `/账单 发工资12000 银行卡`（收入）；**自动提取时刻**（`下午3点半打车12` → `time: "15:30"`，支持 `X点/X点半/X点X分/14:30` 与凌晨/早上/中午/下午/晚上换算，没说时间记当前时刻）；首词可显式指定类型 `支出/收入` 和分类白名单名（如 `/账单 食品酒水 买了箱牛奶45`、组合 `/账单 支出 餐饮 午餐30`）；分类自动识别靠关键词表（午餐→餐饮、打车→交通、奖金→职业收入…），**识别不到可向导里直接发自定义分类名（1-10 字，如「水产」），或发 `分类:任意名`、`账户:现金` 在发布前纠正**；支持一句多笔 `午餐30晚餐45打车12`；自动识别花呗/白条/信用卡账户（账户仅是记账口径）；负债/借款不再支持（命中提示下线；若内容提到还款仅按普通支出解析、分类「还款」，不再单独提示），与博客累计结余卡片联动
- ✅ **日程细分三命令**（2026-08-23）：`/日程` 普通日程（如 `明天下午3点高优在会议室A开周会 每周 提前15分钟`）、`/生日` 生日（category: birthday，支持一句多人+农历，农历按 `isLunar/lunarMonth/lunarDay` 存储、文件名 `lunar-M-D` 前缀）、`/纪念日` 纪念日（category: anniversary，每年重复，支持 `@人物`）；用错命令会自动提示纠正，杜绝 category 生成错
- ✅ **日程微信提醒**：到点前 `N` 分钟（可口语“提前15分钟”或设置默认）微信私聊 `🔔 提醒`，`apscheduler` 持久化，重启不丢，支持 `/提醒 列表/取消`
- ✅ 动态支持图片、动图 GIF 与视频：微信视频自动下载、上传图床，URL 进动态 `images` 数组（视频仅动态支持）
- ✅ 相册发布：新相册自动建 `src/content/album/<名>.md`（含 `subtitle`/`imgbedFolder`，对齐博客现有格式）触发构建；已有相册（按标题/文件名判断）只传图不写文件，照片进命中相册自己的图床目录
- ✅ 图片自动上传图床（统一上传到 `imgbed_upload_folder`，默认 `blog/moments`，与博客图床目录惯例一致）
- ✅ 足迹坐标自动获取（高德地理编码 API）；足迹格式对齐博客最新（含 `description` 固定句式）
- ✅ 自定义标签：`/动态 内容 #日常 #2026`，自动合并默认标签（纯数字标签自动加引号防 schema 校验失败）
- ✅ 友链字段智能识别：兼容中英文键名（站点名称/名称/name/博客名…）、冒号/单空格分隔、乱序、缺字段提示；`weight: 0` + `group: other` 对齐现有文件
- ✅ 会话式图片收集：微信图片不能图文同发，先发命令再发图，`/发布` 统一提交
- ✅ 文件名自动冲突处理：同日多条自动追加 `-1`、`-2` 后缀
- ✅ **影视记录**（2026-08-23）：`/影视 侏罗纪世界` 自动从 TMDB 搜索中文片名并获取封面，封面上传图床独立目录（默认 `blog/bangumi`）；随后可发 `评分 8`、`#标签`、一句话影评，生成 `src/content/bangumi/anime/片名.md`（category: anime + subcategory: movie/tv）；**自己发图可替换封面**；TMDB 搜不到自动转手动模式（自己发图 + `名称:`/`类型:` 修正）；TMDB 连不上可在配置填反代地址
- ✅ **书籍记录**（2026-08-23）：`/书籍 书名` 自己发封面图（必须），评分/标签/书评同影视，生成 `src/content/bangumi/book/书名.md`（category: book）
- ✅ **导航网站**（2026-08-23，2026-09-21 对齐博客新格式）：`/导航 https://example.com` 自动通过 xxapi（v2.xxapi.cn，无需 Key）获取网站图标，图标上传图床独立目录（默认 `blog/daohang`）；向导从博客现有分类文件夹里选（或新建/回复分类名，缺省 `daohang_default_category`）；随后键值对补 `名称/描述` + `#标签`，生成 `src/content/daohang/<分类>/域名-slug.md`（分类=文件夹，条目只写 `name/url/icon/description/tags`）
- ✅ 白名单控制：非白名单用户静默忽略，绝不抢占其他插件/AI 的消息处理
- ✅ 微信图片下载兜底：适配器 aiohttp 被微信 CDN TLS 风控拒绝时，自动改用 curl 下载 + AES 解密

## 安装

1. 将 `main.py`、`blog_writer_core.py`、`metadata.yaml`、`README.md`、`_conf_schema.json` 打包为 `AstrBot-BlogWriter-vX.Y.Z.zip`（打包规范见 `AGENTS.md`）
2. AstrBot 后台 → 插件管理 → 安装插件 → 上传 zip
3. 在 WebUI 插件的「配置」面板中填写配置项（见下）

> 要求 AstrBot >= v4.22.0（`metadata.yaml` 中已声明 `astrbot_version: ">=4.22.0"`）

## 配置

| 配置项 | 说明 |
|---|---|
| github_token | GitHub fine-grained PAT（Contents 读写，仅限博客仓库） |
| github_repo | 博客仓库，默认 `mengkuikun/Blog-2.0` |
| github_branch | 目标分支，默认 `main` |
| blog_base_url | 博客主页链接，默认 `https://imki.cn` |
| imgbed_upload_url | 图床上传地址，默认 `https://img.imki.cn/upload` |
| imgbed_token | 图床 API Token（`Authorization: Bearer` 认证） |
| imgbed_upload_folder | 图片上传目录（动态/笔记/足迹照片统一），默认 `blog/moments` |
| album_folder_prefix | 相册图片目录前缀，默认 `blog/album`（实际目录 = 前缀 + 相册名） |
| wx_cdn_base_url | 微信媒体 CDN 地址（图片下载兜底用），默认 `https://novac2c.cdn.weixin.qq.com/c2c` |
| amap_key | 高德 Web 服务 Key（足迹坐标用）；留空读环境变量 `AMAP_KEY` |
| tmdb_api_key | TMDB API Key（影视封面用）；themoviedb.org 免费注册申请 v3 Key |
| tmdb_api_base / tmdb_image_base | TMDB API/图片地址（服务器连不上官方时填自建反代；默认官方地址） |
| bangumi_upload_folder | 影视封面上传图床目录（独立于动态图片目录），默认 `blog/bangumi` |
| daohang_upload_folder | 导航网站图标上传图床目录，默认 `blog/daohang` |
| daohang_default_category | 导航默认分类文件夹（分类列表拉取失败或回复“跳过”时用），默认 `未分类` |
| article_default_dir | 转载文章发布目录（博客分类=文件夹路径），默认 `技术分享` |
| article_upload_folder | 转载文章图片转存图床目录，默认 `blog/article` |
| article_tags | 转载文章默认标签，默认 `["转载"]` |
| moment_tags / place_tags | 动态/足迹默认标签，默认 `["日常"]` / `["旅游"]` |
| default_note_dir | 笔记默认分类目录，默认 `日常随笔` |
| friend_default_avatar | 友链默认头像（未提供头像链接时），默认 `/avatar.jpg` |
| friend_tags | 友链默认标签，默认 `["Blog"]` |
| allow_users | 允许使用的用户 ID 列表（个人微信为 `xxx@im.wechat` 格式）；空列表 = 全部拒绝 |
| allow_groups | 允许交互的群号列表（QQ 群号）；留空 = 不限制群；填了以后列表外的群一律静默 |
| bill_default_account / bill_default_category | 账单默认账户/分类（解析为「其他」时替换） |
| schedule_default_priority / schedule_remind_before | 日程默认优先级/默认提前提醒分钟（0=准点） |

`allow_users` 怎么拿自己的 ID：发一条消息，在 AstrBot 控制台日志里看发送者 ID，填进去。

## 使用

> 2026-08-25 起（v1.0.42+）主要命令支持**交互式向导**：空参发命令会分步提问，回数字选择、回“取消”退出、回“跳过”走默认；带参快捷写法保留不变。支持微信（weixin_oc）与 QQ（aiocqhttp）。

| 命令 | 说明 |
|---|---|
| `/动态 今天去了公园 #日常` | 创建动态会话，可发图片 / GIF / 视频（可多发） |
| `/笔记` | **向导**：列出 GitHub 上现有笔记本（回数字选或直接回名字新建）→ 问标题 → 发正文/图片，`/发布` 提交；新笔记本发布时自动补建 `_index.json`（否则博客书架不显示） |
| `/笔记 日常随笔 标题` | 快捷：跳过向导直达正文（分类名会自动清洗非法字符） |
| `/足迹 陕西 华阴市华山 去找宝宝了 #旅游` | 创建足迹会话，坐标自动获取，可发照片 |
| `/友链` | 创建友链会话，逐行发送键值对信息自动识别 |
| `/相册` | **向导**：列出博客现有相册（标题+文件名，回数字选）或选新建；选已有相册只追加照片 |
| `/相册 情侣头像` | 快捷：直达发图；相册已存在（按标题/文件名判断）则只追加照片 |
| `/账单 午餐微信花了32` | 正则识别后**确认向导**：1.支出 2.收入 3.直接发布 4.重说；分类/账户已识别的直接跳过不重复问；问分类时可回数字选常用分类或直接发自定义分类名；支持历史补记（如 `/账单 昨天 午餐30` 或 `/账单 10-08 午餐30`） |
| `/账单 花呗借款5000` | 负债类型已下线，返回提示不再支持（账单仅支出/收入）；一句多笔自动批量（批量不走向导） |
| `/存账 绿茶3` / `/记一笔` | **待发暂存箱**：随手记账不占会话（零阻塞，发完可立即发动态/发笔记）；支持一句多笔与历史日期；随时发 `/查存账` 查看、发 `/清存账` 清空；睡前或任意时刻发 `/发布` 一键合并打包并触发单次 Git Commit 部署 |
| `/撤回` / `/撤销` | 暂存箱发布后 10 分钟内一键防手滑撤回：自动调用 GitHub API 删除已发布的 md 文件并恢复账单至暂存箱 |
| `/日程 明天15点开周会 @会议室A 高优 每周 提前15分钟` / `/日程` | 普通日程（category: schedule），到点提醒 |
| `/生日 我的农历8.24` / `/生日` | 生日（category: birthday，每年重复全天）；一句多个：`/生日 我的农历8.24对象12.22妈8.7都是农历`；农历文件名 `lunar-M-D` |
| `/纪念日 结婚纪念日 农历5月20` / `/纪念日` | 纪念日（category: anniversary，每年重复全天），格式 `标题 日期 [@人物]`，日期支持 `1月1日` / `2026-01-01` / `农历5月20` |
| `/影视 侏罗纪世界` | TMDB 自动搜片取封面（上传图床 `blog/bangumi`）；搜不到转手动模式：发封面图后**向导选类型**（1.电影 2.电视剧 3.动漫 4.纪录片 5.游戏）→ 评分 → 标签；游戏落 `bangumi/game/`、动漫/纪录片写对应 subcategory |
| `/书籍 认知觉醒` | 书籍记录：自己发封面图（必须），评分/标签/书评同影视，生成 bangumi/book 条目 |
| `/导航 https://example.com` | 添加导航网站：xxapi 自动取图标（上传图床 `blog/daohang`），**向导选分类文件夹**（列出现有分类，可选新建），随后发键值对 `名称/描述` 与 `#标签`，`/发布` 生成 `src/content/daohang/<分类>/` 条目（`name/url/icon/description/tags`，对齐博客 2026-09-21） |
| `/转载 https://mp.weixin.qq.com/s/xxxx` | 公众号文章转载：抓取正文转 Markdown、图片转存图床（默认 `blog/article`），生成博客文章（sourceLink + 转载声明）到配置目录（默认 `技术分享`），一次命令直达发布 |
| `/提醒 列表` / `/提醒 取消 标题` | 查看/取消待提醒日程 |
| `/发布` | 结束会话：上传图床 → 生成 markdown → GitHub 提交 |
| `/取消` | 放弃当前会话（向导中发“取消”同样生效） |
| `/状态` | 查看当前会话 |

### 友链示例

```
我：/友链
我：网站名称: RAGNote
    描述:Life is code. I will debug it.
    网站地址: https://ragnote.top/
    头像:https://ragnote.top/Avatar.png
我：/发布
```

支持键名：名称（站点名称/名称/名字/昵称/博客名/博主/name/title…）、描述（简介/介绍/签名/desc/descr…）、链接（网址/地址/主页/url/link/siteurl…）、头像（图标/logo/avatar/imgurl…）。键名不认识但冒号后是完整 URL 的按值自动归类。

### 会话规则

- 会话 30 分钟无操作自动作废
- 同一用户同时只允许一个会话
- 非白名单用户的消息一律静默放行，不干扰其他功能

## 注意事项

- GitHub Token 只保存在服务器 AstrBot 配置中，泄露请立即在 GitHub 撤销重建
- 足迹坐标获取失败会中止发布（避免产生无坐标数据）
- 任一图片上传失败会中止整个发布，不会产生半成品提交
- 微信图片下载兜底依赖服务器 `curl`（需可用）
- 动态的作者/头像由博客端统一配置（`content.config.ts` 的 schema 默认值），插件不再按条写入 `author`/`avatar` 字段
- 相册追加模式不触发博客构建：详情页照片即时可见，列表页预览图在下次构建后刷新
- 相册按标题判断是否存在（文件名与标题不一定相同，如 `xiangce1.md` 的标题是「测试相册」）；追加照片会上传到命中相册自己的图床目录
- 图片上传按扩展名声明真实 MIME（jpg/png/webp/gif/heic/mp4…），修复早期版本图床存成 `application/octet-stream` 导致浏览器打开直接下载的问题；旧图需在图床后台改类型或重传
- 笔记图片自 2026-09-27 起写 frontmatter `images:` 数组（对齐博客归档卡片宫格），不再往正文拼 `![](url)`
- 笔记分类/相册名等用户输入会经文件名清洗（非法字符转 `-`），防止路径注入
- 命令/会话消息处理后调用 `stop_event` 阻断事件传播（符合官方规范，避免 LLM 对同一条消息重复回复）；无关消息放行不阻断
- 日程提醒持久化自 v1.0.49 起存 AstrBot 根 `data/plugin_data/blog_writer/`（官方规范：防插件重装覆盖）；升级后自动读旧插件目录文件迁移，无需手动搬
- 插件卸载/重载时 `terminate()` 会关闭 httpx 客户端与 APScheduler，避免调度器残留
- 群聊不主动插嘴：白名单用户「无会话发图提示」仅在**私聊**生效；配置 `allow_groups` 后（非空），不在列表内的群完全静默（含命令）
- `allow_groups` 与 `allow_users` 是两层控制：前者管「哪个群」，后者管「哪个人」；私聊只受 allow_users 约束

## 测试

```bash
pip install httpx pycryptodome
python -m unittest discover -s tests
```

189 个单元测试 + 集成冒烟测试（stub astrbot 依赖），覆盖命令解析、markdown 生成（含 YAML 边界与最新格式）、图床/高德/GitHub/TMDB/xxapi 响应解析、友链字段识别、账单支出/收入两类型（含还款记支出与负债下线回归）、向导全流程（笔记/相册/影视类型/账单确认，含选项错位与字段跳过回归）、日程/生日/纪念日解析（含农历与防呆）、影视（TMDB/手动/换封面/game 落盘）与书籍全流程、导航全流程（文件夹分类 + tags）、消息权限与放行逻辑。

## 致谢

- [AstrBot](https://github.com/AstrBotDevs/AstrBot) —— 多平台 AI 聊天机器人框架
- 插件 API 依据 AstrBot 官方文档：[插件开发指南](https://docs.astrbot.app/dev/star/)
