# -*- coding: utf-8 -*-
"""
AstrBot BlogWriter 插件
通过微信对话更新博客的动态（moments）、笔记（notebooks）、足迹（places）。

用法：
  /动态 今天去了公园            # 创建动态会话，可继续发图片/GIF/视频
  /笔记 日常随笔 标题            # 创建笔记会话，正文由后续文本消息追加
  /足迹 陕西 华阴市华山 去找宝宝了  # 创建足迹会话（坐标由高德地理编码获取）
  /相册 情侣头像                # 创建相册会话，图片传到 blog/album/<相册名>
  /发布                      # 结束会话：上传图床 → 生成 md → 提交 GitHub
  /取消                      # 丢弃当前会话
  /状态                      # 查看会话状态

API 依据官方文档（https://docs.astrbot.app/dev/star/）：
- 消息监听：@filter.event_message_type(filter.EventMessageType.ALL)
- 插件配置：_conf_schema.json + __init__(self, context, config)
- 网络请求：httpx（AstrBot 内置依赖）
"""

import asyncio
import base64
import json
import os
import re
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx

SHANGHAI_TZ = timezone(timedelta(hours=8))


def now_shanghai() -> datetime:
    return datetime.now(SHANGHAI_TZ).replace(tzinfo=None)


def now_shanghai_tz() -> datetime:
    return datetime.now(SHANGHAI_TZ)


try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.date import DateTrigger

    HAS_APSCHEDULER = True
except ImportError:
    BackgroundScheduler = None  # type: ignore
    DateTrigger = None  # type: ignore
    HAS_APSCHEDULER = False

REMINDER_FILE = Path(__file__).parent / "data" / "schedules_reminder.json"
PENDING_BILLS_FILE = Path(__file__).parent / "data" / "pending_bills.json"

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult, filter
from astrbot.api.message_components import Image, Plain

try:
    from astrbot.api.message_components import Video
except ImportError:  # 兼容极老版本（无 Video 组件）
    Video = None
from astrbot.api.star import Context, Star, register

try:
    from .blog_writer_core import (
        BILL_ACCOUNTS,
        BILL_CATEGORIES,
        COMMANDS,
        SCHEDULE_PRIORITIES,
        build_album_md,
        build_amap_url,
        build_bangumi_md,
        build_article_md,
        extract_wx_article,
        extract_wx_url,
        assemble_article_body,
        build_daohang_md,
        build_tmdb_search_url,
        build_xxapi_ico_url,
        build_bill_md,
        build_github_commit_body,
        build_github_delete_tree_body,
        build_github_put_body,
        build_github_ref_update_body,
        build_github_tree_body,
        build_imgbed_upload,
        build_moment_md,
        build_note_md,
        build_notebook_index_json,
        build_place_md,
        build_schedule_md,
        build_upload_url,
        build_friend_md,
        clean_filename_part,
        extract_tags,
        _parse_bill_date,
        _parse_bill_time,
        github_base,
        github_commit_url,
        github_commits_url,
        github_put_url,
        github_ref_url,
        github_refs_url,
        github_trees_url,
        moment_filename,
        next_friend_index,
        note_filename,
        parse_amap_response,
        parse_album,
        parse_album_frontmatter,
        parse_anniversary,
        parse_media_score,
        parse_media_fields,
        parse_tmdb_search_response,
        parse_xxapi_ico_response,
        parse_bill,
        parse_bills_batch,
        parse_daohang_text,
        parse_dynamic,
        parse_friend_text,
        parse_github_put_response,
        parse_imgbed_response,
        parse_message,
        parse_note,
        parse_place,
        parse_schedule,
        parse_schedules_batch,
        place_filename,
        schedule_filename,
        daohang_slug,
        site_host,
        tmdb_poster_url,
        upload_base_host,
        validate_friend_data,
        with_suffix,
        Session,
        format_choices,
        parse_choice,
        is_wizard_cancel,
        is_wizard_skip,
        MEDIA_WIZARD_CATEGORIES,
        BILL_WIZARD_CREDIT_ACCOUNTS,
    )
except ImportError:  # 兼容非包形式加载
    from blog_writer_core import (
        BILL_ACCOUNTS,
        BILL_CATEGORIES,
        COMMANDS,
        SCHEDULE_PRIORITIES,
        build_album_md,
        build_amap_url,
        build_bangumi_md,
        build_article_md,
        extract_wx_article,
        extract_wx_url,
        assemble_article_body,
        build_daohang_md,
        build_tmdb_search_url,
        build_xxapi_ico_url,
        build_bill_md,
        build_github_commit_body,
        build_github_delete_tree_body,
        build_github_put_body,
        build_github_ref_update_body,
        build_github_tree_body,
        build_imgbed_upload,
        build_moment_md,
        build_note_md,
        build_notebook_index_json,
        build_place_md,
        build_schedule_md,
        build_upload_url,
        build_friend_md,
        clean_filename_part,
        extract_tags,
        _parse_bill_date,
        _parse_bill_time,
        github_base,
        github_commit_url,
        github_commits_url,
        github_put_url,
        github_ref_url,
        github_refs_url,
        github_trees_url,
        moment_filename,
        next_friend_index,
        note_filename,
        parse_amap_response,
        parse_album,
        parse_album_frontmatter,
        parse_anniversary,
        parse_media_score,
        parse_media_fields,
        parse_tmdb_search_response,
        parse_xxapi_ico_response,
        parse_bill,
        parse_bills_batch,
        parse_daohang_text,
        parse_dynamic,
        parse_friend_text,
        parse_github_put_response,
        parse_imgbed_response,
        parse_message,
        parse_note,
        parse_place,
        parse_schedule,
        parse_schedules_batch,
        place_filename,
        schedule_filename,
        daohang_slug,
        site_host,
        tmdb_poster_url,
        upload_base_host,
        validate_friend_data,
        with_suffix,
        Session,
        format_choices,
        parse_choice,
        is_wizard_cancel,
        is_wizard_skip,
        MEDIA_WIZARD_CATEGORIES,
        BILL_WIZARD_CREDIT_ACCOUNTS,
    )

CONNECT_TIMEOUT = 15
READ_TIMEOUT = 30
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB
MAX_VIDEO_SIZE = 100 * 1024 * 1024  # 100MB（微信视频常超 20MB）
RETRY_COUNT = 2
RETRY_DELAYS = (1.0, 3.0)


@register(
    "blog_writer",
    "tianshihao2003",
    "通过微信/QQ对话更新博客的动态、笔记、足迹、相册、友链、账单、日程（交互式向导 + 日程提醒）",
    "v1.0.0",
)
class BlogWriter(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        self._sessions: Dict[str, Session] = {}
        self._lock = asyncio.Lock()
        self._client = None
        self._reminders: List[Tuple[str, str, datetime]] = []
        self._reminder_file = self._resolve_reminder_file()
        self._pending_bills_file = self._resolve_pending_bills_file()
        self._pending_bills: Dict[str, List[Dict]] = self._load_pending_bills()
        self._last_published: Dict[str, Dict[str, Any]] = {}
        self._loop = None
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                self._loop = asyncio.get_event_loop()
            except Exception:
                self._loop = None
        self._scheduler = None
        if HAS_APSCHEDULER:
            try:
                # 显式指定上海时区，避免 UTC 偏差
                try:
                    self._scheduler = BackgroundScheduler(timezone=SHANGHAI_TZ)
                except Exception:
                    self._scheduler = BackgroundScheduler()
                self._scheduler.start()
                self._restore_reminders()
                logger.info("BlogWriter: APScheduler 提醒调度器已启动（持久化：%s）", self._reminder_file)
            except Exception as e:
                logger.warning("BlogWriter: APScheduler 启动失败: %s", e)
                self._scheduler = None
        else:
            logger.warning("BlogWriter: 未安装 apscheduler，提醒功能将仅内存生效（重启丢失）")
            # 无调度器时仍把持久化提醒恢复到内存列表（否则 /提醒 列表 在重启后为空）
            self._restore_reminders()

    def _resolve_reminder_file(self) -> Path:
        """提醒持久化路径。官方规范（docs.astrbot.app/dev/star）：持久化数据应存
        AstrBot 根 data/ 目录，而非插件自身目录——否则重装/更新插件 zip 时被覆盖。
        识别 AstrBot 根：cwd 下存在 data/plugins 或 data/config；识别不到（本地开发/
        测试）回退插件目录旧行为。"""
        try:
            cwd = Path(os.getcwd())
            if (cwd / "data" / "plugins").is_dir() or (cwd / "data" / "config").is_dir():
                return cwd / "data" / "plugin_data" / "blog_writer" / "schedules_reminder.json"
        except Exception as e:
            logger.warning("BlogWriter: 解析提醒持久化路径失败，回退插件目录: %s", e)
        return REMINDER_FILE

    def _load_reminders(self) -> List[Dict]:
        # 测试通过替换模块级 REMINDER_FILE 隔离路径时优先之；否则先读新路径，
        # 再读插件目录旧路径（老用户迁移兼容，不丢历史提醒）
        rf = globals().get("REMINDER_FILE", REMINDER_FILE)
        if rf != REMINDER_FILE:
            paths = [rf]
        else:
            paths = [self._reminder_file, REMINDER_FILE]
        for p in paths:
            try:
                if p.exists():
                    return json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("BlogWriter: 读取提醒文件失败: %s (%s)", e, p)
        return []

    def _save_reminders(self, data: List[Dict]) -> None:
        try:
            p = self._reminder_file
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("BlogWriter: 保存提醒文件失败: %s", e)

    def _resolve_pending_bills_file(self) -> Path:
        """待发暂存箱持久化路径。"""
        try:
            cwd = Path(os.getcwd())
            if (cwd / "data" / "plugins").is_dir() or (cwd / "data" / "config").is_dir():
                return cwd / "data" / "plugin_data" / "blog_writer" / "pending_bills.json"
        except Exception as e:
            logger.warning("BlogWriter: 解析待发暂存箱持久化路径失败，回退插件目录: %s", e)
        return PENDING_BILLS_FILE

    def _load_pending_bills(self) -> Dict[str, List[Dict]]:
        pf = globals().get("PENDING_BILLS_FILE", PENDING_BILLS_FILE)
        if pf != PENDING_BILLS_FILE:
            paths = [pf]
        else:
            paths = [self._pending_bills_file, PENDING_BILLS_FILE]
        for p in paths:
            try:
                if p.exists():
                    raw = json.loads(p.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        return raw
            except Exception as e:
                logger.warning("BlogWriter: 读取待发暂存箱失败: %s (%s)", e, p)
        return {}

    def _save_pending_bills(self) -> None:
        try:
            def _dt_serial(obj):
                if isinstance(obj, (datetime, date)):
                    return obj.strftime("%Y-%m-%d")
                raise TypeError(f"Type {type(obj)} not serializable")

            p = self._pending_bills_file
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(self._pending_bills, default=_dt_serial, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error("BlogWriter: 保存待发暂存箱失败: %s", e)

    def _restore_reminders(self) -> None:
        if not hasattr(self, "_reminders"):
            self._reminders = []
        if not HAS_APSCHEDULER or not self._scheduler:
            # 无调度器时仍恢复到内存列表，供列表展示
            try:
                for item in self._load_reminders():
                    try:
                        remind_at = datetime.fromisoformat(item["remind_at"])
                        if remind_at.tzinfo is not None:
                            remind_at = remind_at.astimezone(SHANGHAI_TZ).replace(tzinfo=None)
                        if remind_at <= now_shanghai():
                            continue
                        self._reminders.append((item["user_id"], item["title"], remind_at))
                    except Exception:
                        continue
            except Exception as e:
                logger.warning("BlogWriter: 恢复提醒(内存)异常: %s", e)
            return
        try:
            for item in self._load_reminders():
                try:
                    remind_at = datetime.fromisoformat(item["remind_at"])
                    if remind_at.tzinfo is not None:
                        remind_at = remind_at.astimezone(SHANGHAI_TZ).replace(tzinfo=None)
                    if remind_at <= now_shanghai():
                        continue
                    self._reminders.append((item["user_id"], item["title"], remind_at))
                    origin = item.get("origin") or ""
                    # 调度时用上海时区，存的是 naive，按上海解释
                    try:
                        remind_at_tz = remind_at.replace(tzinfo=SHANGHAI_TZ)
                    except Exception:
                        remind_at_tz = remind_at
                    self._scheduler.add_job(
                        self._send_remind_sync,
                        trigger=DateTrigger(run_date=remind_at_tz),
                        args=[item["user_id"], item["title"], origin],
                        # 与 _schedule_remind 的 id 格式一致，保证 replace_existing 生效
                        id=item.get("id") or f"{item['user_id']}_{item['title']}_{remind_at.isoformat()}",
                        replace_existing=True,
                    )
                except Exception as e:
                    logger.warning("BlogWriter: 恢复提醒失败: %s %s", item, e)
        except Exception as e:
            logger.warning("BlogWriter: 恢复提醒异常: %s", e)

    def _send_remind_sync(self, user_id: str, title: str, origin: str = "") -> None:
        # 使用初始化时保存的 loop，避免取到错误 loop 导致 Timeout context manager 异常
        loop = getattr(self, "_loop", None)
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
                self._loop = loop
            except RuntimeError:
                try:
                    loop = asyncio.get_event_loop()
                    self._loop = loop
                except Exception:
                    loop = None
        try:
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(self._send_remind(user_id, title, origin), loop)
            else:
                asyncio.run(self._send_remind(user_id, title, origin))
        except RuntimeError:
            # 无运行中的 loop 时创建临时 loop
            try:
                asyncio.run(self._send_remind(user_id, title, origin))
            except Exception as e:
                logger.warning("BlogWriter: 同步发送提醒失败: %s", e)

    async def _send_remind(self, user_id: str, title: str, origin: str = "") -> None:
        try:
            logger.info("BlogWriter: 到点提醒 user=%s title=%s origin=%s", user_id, title, origin)
            sent = False
            # 1. 优先用 origin + MessageChain（按 AstrBot 官方文档：MessageChain().message() + send_message(origin, chain)）
            if origin and hasattr(self.context, "send_message"):
                def _make_chain(text: str):
                    # 标准构造：优先尝试最简的 List[Plain]，再尝试 MessageChain
                    # 先试最简，避免 MessageChain().message() 内部的 timeout 陷阱
                    try:
                        from astrbot.core.message.message_event_result import MessageChain as _MC  # type: ignore

                        # 直接构造，避免调用 .message()（其内部可能用 asyncio.timeout）
                        try:
                            return _MC(chain=[Plain(text)])  # type: ignore
                        except Exception:
                            try:
                                return _MC([Plain(text)])  # type: ignore
                            except Exception:
                                pass
                    except ImportError:
                        pass
                    except Exception:
                        pass
                    try:
                        from astrbot.core.message.message import MessageChain as _MC1  # type: ignore

                        try:
                            return _MC1([Plain(text)])  # type: ignore
                        except Exception:
                            try:
                                return _MC1(chain=[Plain(text)])  # type: ignore
                            except Exception:
                                pass
                    except ImportError:
                        pass
                    except Exception:
                        pass
                    # 兜底：直接 Plain 列表，很多版本 send_message 也接受
                    return [Plain(text)]  # type: ignore

                for idx, maker in enumerate(
                    [
                        lambda: _make_chain(title),
                        lambda: [Plain(title)],  # type: ignore
                        lambda: Plain(title),  # type: ignore
                        lambda: title,  # type: ignore
                    ]
                ):
                    try:
                        chain = maker()  # type: ignore
                        await self.context.send_message(origin, chain)  # type: ignore
                        sent = True
                        logger.info("BlogWriter: 主动推送 via origin 成功 origin=%s attempt=%s", origin, idx)
                        break
                    except Exception as e:
                        logger.warning("BlogWriter: 主动推送 via origin 失败 attempt=%s err=%s", idx, e)
                        continue
                if not sent:
                    logger.warning("BlogWriter: 主动推送 via origin 失败: all attempts failed origin=%s", origin)
            # 2. 兜底：按 origin 解析平台名再试（兼容 weixin_oc / weixin_personal_bglh）
            if not sent and hasattr(self.context, "get_platform"):
                plat_names = []
                if origin and ":" in origin:
                    plat_names.append(origin.split(":")[0])
                plat_names.extend(["weixin_oc", "weixin_personal_bglh", "weixin"])

                def _plat_chain(text: str):
                    try:
                        from astrbot.core.message.message import MessageChain as _PMC1  # type: ignore

                        try:
                            return _PMC1(chain=[Plain(text)])  # type: ignore
                        except Exception:
                            try:
                                _mc = _PMC1()  # type: ignore
                                _mc.chain = [Plain(text)]  # type: ignore
                                return _mc
                            except Exception:
                                return _PMC1([Plain(text)])  # type: ignore
                    except ImportError:
                        try:
                            from astrbot.core.message.components import MessageChain as _PMC2  # type: ignore

                            return _PMC2([Plain(text)])  # type: ignore
                        except ImportError:
                            return [Plain(text)]  # type: ignore
                    except Exception:
                        return [Plain(text)]  # type: ignore

                seen = set()
                for pname in plat_names:
                    if not pname or pname in seen:
                        continue
                    seen.add(pname)
                    try:
                        plat = self.context.get_platform(pname)
                        if plat and hasattr(plat, "send_message"):
                            for idx, attempt in enumerate(
                                [
                                    lambda p=plat: p.send_message(_plat_chain(title), user_id),  # type: ignore
                                    lambda p=plat: p.send_message(Plain(title), user_id),  # type: ignore
                                    lambda p=plat: p.send_message(title, user_id),  # type: ignore
                                    lambda p=plat: p.send_message([Plain(title)], user_id),  # type: ignore
                                    lambda p=plat: p.send_message(user_id, _plat_chain(title)),  # type: ignore
                                ]
                            ):
                                try:
                                    await attempt()  # type: ignore
                                    sent = True
                                    logger.info("BlogWriter: 平台推送成功 via %s attempt=%s", pname, idx)
                                    break
                                except Exception as e:
                                    logger.warning("BlogWriter: 平台 %s 尝试 %s 失败: %s", pname, idx, e)
                                    continue
                        if sent:
                            break
                    except Exception as e:
                        logger.warning("BlogWriter: 平台 %s 获取失败: %s", pname, e)
            if not sent:
                logger.warning("BlogWriter: 未能主动推送，提醒仅记录日志 user=%s title=%s", user_id, title)
        except Exception as e:
            logger.warning("BlogWriter: 发送提醒失败: %s", e)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT),
                follow_redirects=True,
                headers={"User-Agent": "AstrBot-BlogWriter/1.0"},
            )
        return self._client

    # ---------- 配置 ----------

    def _cfg(self, key: str, default=None):
        try:
            value = self.config.get(key)
            return value if value is not None else default
        except Exception:
            return default

    def _amap_key(self) -> str:
        return (self._cfg("amap_key") or "").strip() or os.environ.get("AMAP_KEY", "").strip()

    def _allowed(self, user_id: str) -> bool:
        allow = self._cfg("allow_users") or []
        if not allow:
            return False
        return user_id in [str(x).strip() for x in allow]

    @staticmethod
    def _is_group_message(event: AstrMessageEvent) -> bool:
        """判断消息是否来自群聊。

        优先解析 unified_msg_origin 类型段（如 aiocqhttp:GroupMessage:123456），
        其次探测 get_group_id()。识别不出时按私聊处理（宁可提示也不丢消息）。
        """
        try:
            origin = str(getattr(event, "unified_msg_origin", "") or "")
            if "GroupMessage" in origin:
                return True
            if "FriendMessage" in origin or "PrivateMessage" in origin:
                return False
            getter = getattr(event, "get_group_id", None)
            if callable(getter):
                if str(getter() or "").strip():
                    return True
        except Exception:
            pass
        return False

    def _group_allowed(self, event: AstrMessageEvent) -> bool:
        """群聊白名单：allow_groups 为空 → 不限制（保持既有行为）；
        非空 → 仅列表内的群可交互，其余群完全静默（含命令）。"""
        allow = self._cfg("allow_groups") or []
        if not allow:
            return True
        allowed = [str(x).strip() for x in allow if str(x).strip()]
        gid = ""
        try:
            getter = getattr(event, "get_group_id", None)
            if callable(getter):
                gid = str(getter() or "").strip()
        except Exception:
            gid = ""
        if not gid:
            origin = str(getattr(event, "unified_msg_origin", "") or "")
            parts = origin.split(":")
            if len(parts) >= 3 and "GroupMessage" in origin:
                gid = parts[-1].strip()
        return bool(gid) and gid in allowed

    @staticmethod
    def _merge_tags(default_tags, extra) -> List[str]:
        """默认标签 + 自定义标签，保持顺序并去重。"""
        result = [str(t).strip() for t in (default_tags or []) if str(t).strip()]
        seen = set(result)
        for t in (extra or []):
            t = str(t).strip()
            if t and t not in seen:
                seen.add(t)
                result.append(t)
        return result

    def _sweep(self) -> None:
        now = now_shanghai()
        expired = [uid for uid, s in self._sessions.items() if s.expired(now)]
        for uid in expired:
            del self._sessions[uid]

    def _schedule_remind(self, user_id: str, title: str, remind_at: datetime, unified_msg_origin: str = "", remind_before: int = 10) -> None:
        """持久化调度：写入 json + APScheduler 定时，到点私聊提醒。 past 则不调度。"""
        try:
            if remind_at <= now_shanghai():
                logger.info("BlogWriter: 提醒时间已过，不调度 user=%s title=%s at=%s", user_id, title, remind_at)
                return
            # 确保 remind_at 为上海时区的 naive 时间，调度器按本地时间触发
            # APScheduler 默认使用本地时区，但容器内可能为 UTC，需显式指定
            try:
                remind_at_tz = remind_at.replace(tzinfo=SHANGHAI_TZ) if remind_at.tzinfo is None else remind_at.astimezone(SHANGHAI_TZ)
            except Exception:
                remind_at_tz = remind_at
            logger.info("BlogWriter: 调度提醒 user=%s title=%s at=%s origin=%s before=%s", user_id, title, remind_at, unified_msg_origin, remind_before)
            if not hasattr(self, "_reminders"):
                self._reminders = []
            self._reminders.append((user_id, title, remind_at))
            # 持久化
            try:
                data = self._load_reminders()
                rid = f"{user_id}_{title}_{remind_at.isoformat()}"
                data.append({"id": rid, "user_id": user_id, "title": title, "remind_at": remind_at.isoformat(), "remind_before": remind_before, "origin": unified_msg_origin})
                # 只保留未来 100 条
                data = [d for d in data if datetime.fromisoformat(d["remind_at"]) > now_shanghai() - timedelta(days=1)][-100:]
                self._save_reminders(data)
            except Exception as e:
                logger.warning("BlogWriter: 保存提醒持久化失败: %s", e)
            # 调度
            if HAS_APSCHEDULER and self._scheduler:
                try:
                    rid = f"{user_id}_{title}_{remind_at.isoformat()}"
                    # 显式指定上海时区，避免 UTC 偏差
                    trigger = DateTrigger(run_date=remind_at_tz) if HAS_APSCHEDULER else DateTrigger(run_date=remind_at)
                    self._scheduler.add_job(
                        self._send_remind_sync,
                        trigger=trigger,
                        args=[user_id, f"🔔 日程提醒：{title} 时间到了", unified_msg_origin],
                        id=rid,
                        replace_existing=True,
                    )
                except Exception as e:
                    logger.warning("BlogWriter: APScheduler 添加任务失败: %s", e)
        except Exception as e:
            logger.warning("BlogWriter: 调度提醒失败: %s", e)

    # ---------- 向导辅助 ----------

    _BILL_TYPE_LABELS = {"expense": "支出", "income": "收入"}

    def _bill_accounts_all(self) -> List[str]:
        """账户全量选项：基础白名单 + 信用账户别名（账户仅是记账口径）。"""
        return BILL_ACCOUNTS + [a for a in BILL_WIZARD_CREDIT_ACCOUNTS if a not in BILL_ACCOUNTS]

    def _bill_type_prompt(self) -> str:
        return format_choices(
            "请确认类型：",
            ["支出", "收入"],
            extra=["直接发布", "重说"],
            with_skip_cancel=False,
        )

    def _bill_next_step(self, sess: Session) -> Optional[str]:
        """类型确认后下一步：只问缺失字段，全齐返回 None（可直接发布）。"""
        if str(sess.meta.get("category") or "其他") == "其他":
            return "bill_pick_category"
        if str(sess.meta.get("account") or "其他") == "其他":
            return "bill_pick_account"
        return None

    def _bill_step_prompt(self, step: str) -> str:
        if step == "bill_pick_category":
            return format_choices(
                "请选择分类（回数字选常用分类，或直接发自定义分类名）：",
                BILL_CATEGORIES,
                with_skip_cancel=False,
            )
        return (
            format_choices("请选择账户：", self._bill_accounts_all(), with_skip_cancel=False)
            + "\n也可直接回复账户名"
        )

    def _bill_confirm_text(self, sess: Session) -> str:
        """发布前确认摘要。"""
        return "账单已确认：{} 金额{}，分类{}，账户{}。发 /发布 提交。".format(
            sess.meta.get("title"), sess.meta.get("amount"),
            sess.meta.get("category"), sess.meta.get("account"))

    async def _list_notebook_names(self, repo: str, branch: str, token: str) -> Optional[List[str]]:
        """列出 src/content/life/notebooks 下的一级目录名（笔记本名）。

        返回排序后的目录名列表；**请求失败返回 None**（区别于空仓库的 []，
        发布笔记时依赖该区分决定是否补建 _index.json）。"""
        url = "https://api.github.com/repos/{}/contents/src/content/life/notebooks?ref={}".format(
            repo, urllib.parse.quote(branch)
        )
        headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            resp = await self._get_client().get(url, headers=headers)
            if resp.status_code != 200:
                return None
            import json as _json
            items = _json.loads(resp.text)
            names = []
            for it in items:
                if isinstance(it, dict) and it.get("type") == "dir":
                    n = str(it.get("name") or "").strip()
                    if n and not n.startswith("."):
                        names.append(n)
            return sorted(names)
        except Exception as e:
            logger.warning("BlogWriter: 列笔记本失败: %s", e)
            return None

    async def _ensure_notebook_index(self, note_dir: str, repo: str, branch: str, token: str) -> Tuple[bool, str]:
        """笔记本不存在时补建 _index.json（博客书架/归档页靠它识别，缺了文件夹不可见）。

        返回 (是否新建了索引, 错误信息)。目录列表拉取失败时不动作（返回 False, ""），
        宁可沿用旧行为也不误判已有笔记本。"""
        names = await self._list_notebook_names(repo, branch, token)
        if names is None or note_dir in names:
            return False, ""
        idx_path = "src/content/life/notebooks/{}/_index.json".format(note_dir)
        exists = await self._github_exists(repo, idx_path, branch, token)
        if exists is not False:  # True（已存在）或 None（查询失败）都不再建
            return False, ""
        idx_md = build_notebook_index_json(note_dir)
        ok, err = await self._github_put(repo, idx_path, idx_md, token, branch)
        if not ok:
            return False, err or "GitHub 提交失败"
        logger.info("BlogWriter: 已补建笔记本索引 %s", idx_path)
        return True, ""

    # ---------- 会话创建（账单/日程/提醒） ----------

    def _apply_bill_defaults(self, item: Dict) -> None:
        """正则解析出的账单项应用配置默认值（账户/分类为「其他」时替换）。"""
        if item.get("account") == "其他":
            default_acc = self._cfg("bill_default_account", "其他")
            if default_acc in BILL_ACCOUNTS:
                item["account"] = default_acc
        if item.get("category") == "其他":
            default_cat = self._cfg("bill_default_category", "其他")
            if default_cat in BILL_CATEGORIES:
                item["category"] = default_cat

    async def _start_bill(self, event: AstrMessageEvent, user_id: str, args: List[str], raw: str):
        text = " ".join(args).strip()
        if not text:
            self._sessions[user_id] = Session("bill", {})
            return event.plain_result(
                "账单会话已创建，请发送账单内容，发 /发布 提交，发 /取消 放弃。\n"
                "支出：今天午餐微信花了32（或首词「支出」显式指定）\n"
                "收入：发工资12000 银行卡（或首词「收入」）\n"
                "补记：昨天 午餐30 或 10-08 午餐30\n"
                "批量：午餐30晚餐45打车12\n"
                "暂存：/存账 绿茶3（随手记不占会话，睡前 /发布 合并提交）"
            )
        # 批量正则（一句含多个金额，如“午餐30晚餐45打车12”）
        try:
            batch, _ = parse_bills_batch(text)
            if batch and len(batch) > 1:
                for item in batch:
                    self._apply_bill_defaults(item)
                self._sessions[user_id] = Session("bill_batch", {"items": batch})
                titles = "、".join(f"{x['title']}{x['amount']}" for x in batch[:5])
                more = f"等{len(batch)}笔" if len(batch) > 5 else ""
                return event.plain_result(f"已识别 {len(batch)} 笔账单：{titles}{more}，发 /发布 批量提交，发 /取消 放弃。")
        except Exception:
            pass
        # 单条正则
        parsed, err = parse_bill(text)
        if parsed is None:
            return event.plain_result("账单解析失败：{}，请重发或发 /取消。".format(err))
        self._apply_bill_defaults(parsed)
        sess = Session("bill", parsed)
        # 进入账单向导：让用户确认类型
        t = parsed.get("type")
        label = self._BILL_TYPE_LABELS.get(t, t)
        sess.wizard = {"step": "bill_confirm_type"}
        self._sessions[user_id] = sess
        return event.plain_result(
            "已识别账单：{} 金额{}（{}），分类{}，账户{}\n\n".format(
                parsed.get("title"), parsed.get("amount"), label, parsed.get("category"), parsed.get("account")
            )
            + self._bill_type_prompt()
            + f"\n\n当前猜测：{label}（选对应数字，或 3 直接发布）"
        )

    def _apply_schedule_defaults(self, item: Dict) -> None:
        """正则解析出的日程项应用配置默认值。"""
        if item.get("priority") == "none":
            default_p = self._cfg("schedule_default_priority", "none")
            if default_p in SCHEDULE_PRIORITIES:
                item["priority"] = default_p
        if item.get("remind_before") is None:
            item["remind_before"] = self._cfg("schedule_remind_before", 10)

    async def _handle_save_bill(self, event: AstrMessageEvent, user_id: str, args: List[str]):
        text = " ".join(args).strip()
        if not text:
            return self._handle_list_pending_bills(event, user_id)

        now = now_shanghai()
        # 1. 批量解析（一句含多个金额）
        items = []
        try:
            batch, _ = parse_bills_batch(text, now)
            if batch and len(batch) > 1:
                items = batch
        except Exception:
            pass

        # 2. 单条解析
        if not items:
            parsed, err = parse_bill(text, now)
            if parsed is None:
                return event.plain_result(f"账单解析失败：{err}。格式参考：/存账 绿茶3 或 /存账 昨天 午餐30")
            items = [parsed]

        # 3. 应用默认值与规范化日期
        for it in items:
            self._apply_bill_defaults(it)
            d = it.get("date")
            if isinstance(d, datetime):
                it["date"] = d.strftime("%Y-%m-%d")

        # 4. 存入待发暂存箱
        pending = self._pending_bills.setdefault(user_id, [])
        pending.extend(items)
        self._save_pending_bills()

        # 5. 回复
        total_exp = sum(abs(it.get("amount", 0)) for it in pending if it.get("type") == "expense")
        total_inc = sum(abs(it.get("amount", 0)) for it in pending if it.get("type") == "income")
        summary_parts = []
        if total_exp > 0:
            summary_parts.append(f"支出 ¥{total_exp:.2f}")
        if total_inc > 0:
            summary_parts.append(f"收入 ¥{total_inc:.2f}")
        summary_str = "、".join(summary_parts) or "¥0.00"

        if len(items) == 1:
            it = items[0]
            label = "支出" if it.get("type") == "expense" else "收入"
            amt_str = f"{abs(it.get('amount', 0)):g}"
            return event.plain_result(
                f"📥 已存入暂存箱（第 {len(pending)} 笔）：\n"
                f"📌 {it.get('title')}（{label} {amt_str} 元）\n"
                f"🏷️ 分类：{it.get('category')} · 账户：{it.get('account')}\n"
                f"📅 日期：{it.get('date')} {it.get('time', '')}\n\n"
                f"💡 暂存箱共 {len(pending)} 笔（合计 {summary_str}）。\n"
                f"随手记不占会话，随时发 /存账 继续添加，睡前发送 /发布 一次性合并提交！"
            )
        else:
            titles = "、".join(f"{it.get('title')}{abs(it.get('amount', 0)):g}元" for it in items[:3])
            more = f"等 {len(items)} 笔" if len(items) > 3 else ""
            return event.plain_result(
                f"📥 已存入暂存箱（本次存入 {len(items)} 笔）：\n"
                f"📌 {titles}{more}\n\n"
                f"💡 暂存箱共 {len(pending)} 笔（合计 {summary_str}）。\n"
                f"发送 /查存账 查看清单，发送 /发布 一次性合并提交！"
            )

    def _handle_list_pending_bills(self, event: AstrMessageEvent, user_id: str):
        pending = self._pending_bills.get(user_id) or []
        if not pending:
            return event.plain_result("📦 待发暂存箱是空的。\n发送 /存账 <内容>（如：/存账 绿茶3）即可随手暂存。")

        lines = [f"📦 待发暂存箱清单（共 {len(pending)} 笔）："]
        for idx, it in enumerate(pending, 1):
            label = "-" if it.get("type") == "expense" else "+"
            amt = abs(it.get("amount", 0))
            lines.append(
                f"{idx}. {it.get('title')} {label}{amt:g}元（{it.get('category')} · {it.get('account')} | {it.get('date')} {it.get('time', '')}）"
            )

        total_exp = sum(abs(it.get("amount", 0)) for it in pending if it.get("type") == "expense")
        total_inc = sum(abs(it.get("amount", 0)) for it in pending if it.get("type") == "income")
        stats = []
        if total_exp > 0:
            stats.append(f"支出 ¥{total_exp:.2f}")
        if total_inc > 0:
            stats.append(f"收入 ¥{total_inc:.2f}")
        stats_str = "、".join(stats) or "¥0.00"

        lines.append(f"\n📊 汇总：{stats_str}")
        lines.append("💡 发送 /发布 即可打包为 1 个 Git Commit 提交到博客；发送 /清存账 可清空。")
        return event.plain_result("\n".join(lines))

    def _handle_clear_pending_bills(self, event: AstrMessageEvent, user_id: str):
        pending = self._pending_bills.pop(user_id, [])
        self._save_pending_bills()
        if not pending:
            return event.plain_result("待发暂存箱本来就是空的。")
        return event.plain_result(f"🗑️ 已清空待发暂存箱（共清空 {len(pending)} 笔账单）。")

    async def _handle_recall_last_publish(self, event: AstrMessageEvent, user_id: str):
        rec = self._last_published.get(user_id)
        if not rec:
            return event.plain_result("⚠️ 最近没有可撤回的发布记录。")

        now = now_shanghai()
        pub_time = rec.get("time") or now
        diff = (now - pub_time).total_seconds()
        if diff > 600:
            return event.plain_result("⏰ 已超过撤回时限（发布已超过 10 分钟），无法自动撤回。如需修改请直接前往博客仓库调整。")

        paths = rec.get("paths") or []
        if not paths:
            self._last_published.pop(user_id, None)
            return event.plain_result("未找到需要删除的文件记录。")

        msg = f"blog: 通过 AstrBot 撤回最近发布的内容（共 {len(paths)} 个文件）"
        ok, err = await self._commit_batch_delete(paths, msg)
        if not ok:
            return event.plain_result(f"撤回失败：{err}")

        # 若是暂存箱发布的账单，自动恢复至暂存箱供修改
        restored_hint = ""
        items = rec.get("items")
        if items:
            pending = self._pending_bills.setdefault(user_id, [])
            pending.extend(items)
            self._save_pending_bills()
            restored_hint = f"\n📦 已将撤回的 {len(items)} 笔账单恢复至暂存箱，发送 /查存账 可查看修改。"

        self._last_published.pop(user_id, None)
        path_list = "\n".join(f"- {p}" for p in paths)
        return event.plain_result(
            f"↩️ 撤回成功 ✅\n\n已从博客仓库中移除以下文件：\n{path_list}\n\nGit 提交已回滚，EdgeOne 正在重新部署。{restored_hint}"
        )

    async def _start_schedule(self, event: AstrMessageEvent, user_id: str, args: List[str], raw: str):
        text = " ".join(args).strip()
        if not text:
            self._sessions[user_id] = Session("schedule", {})
            return event.plain_result("日程会话已创建，请发送日程内容（如：明天下午3点在会议室A开周会），发 /发布 提交，发 /取消 放弃。")
        # 批量正则（一句含多个生日，如“我的生日农历8.24对象12.22妈8.7都是农历”；建议用 /生日）
        try:
            batch, _ = parse_schedules_batch(text)
            if batch and len(batch) > 1:
                for item in batch:
                    self._apply_schedule_defaults(item)
                self._sessions[user_id] = Session("schedule_batch", {"items": batch})
                titles = "、".join(x["title"] for x in batch[:5])
                more = f"等{len(batch)}条" if len(batch) > 5 else ""
                return event.plain_result(f"已识别 {len(batch)} 条生日：{titles}{more}，发 /发布 批量提交，发 /取消 放弃。\n（提示：生日请优先用 /生日 命令）")
        except Exception:
            pass
        # 防呆：生日/纪念日请用专用命令，避免 category 生成错
        if "生日" in text or "生气" in text:
            return event.plain_result("检测到生日内容，请用 /生日 命令添加（如：/生日 我的农历8.24，支持一句多个：/生日 我的农历8.24对象12.22妈8.7都是农历）。")
        if "纪念日" in text:
            return event.plain_result("检测到纪念日内容，请用 /纪念日 命令添加（如：/纪念日 我和宝宝认识的纪念日 1月1日 @宝宝，支持农历：/纪念日 结婚纪念日 农历5月20）。")
        # 单条正则
        parsed, err = parse_schedule(text)
        if parsed is None:
            return event.plain_result("日程解析失败：{}，请重发或发 /取消。".format(err))
        self._apply_schedule_defaults(parsed)
        self._sessions[user_id] = Session("schedule", parsed)
        return event.plain_result(
            "已识别日程：{} 时间{} 优先级{}。发 /发布 提交，发 /取消 放弃。".format(
                parsed.get("title"),
                parsed.get("date").strftime("%Y-%m-%d %H:%M:%S") if isinstance(parsed.get("date"), datetime) else parsed.get("date"),
                parsed.get("priority"),
            )
        )

    def _fmt_birthday(self, item: Dict) -> str:
        """生日条目摘要：我生日（农历8月24，每年）"""
        if item.get("isLunar"):
            when = "农历{}月{}".format(item.get("lunarMonth"), item.get("lunarDay"))
        else:
            dt = item.get("date")
            when = dt.strftime("%m月%d日") if isinstance(dt, datetime) else str(dt)
        return "{}（{}，每年重复）".format(item.get("title"), when)

    async def _start_birthday(self, event: AstrMessageEvent, user_id: str, args: List[str], raw: str):
        """/生日 —— 专用生日命令，category 固定 birthday，杜绝文件类型生成错。"""
        text = " ".join(args).strip()
        if not text:
            self._sessions[user_id] = Session("birthday", {})
            return event.plain_result(
                "生日会话已创建，请发送生日内容（如：我的农历8.24、宝宝的 12.22），\n"
                "支持一句多个：我的农历8.24对象12.22妈8.7都是农历。\n"
                "发 /发布 提交，发 /取消 放弃。"
            )
        items, err = parse_schedules_batch(text)
        if not items:
            return event.plain_result("生日解析失败：{}，请重发（示例：我的农历8.24）或发 /取消。".format(err))
        for item in items:
            self._apply_schedule_defaults(item)
        if len(items) == 1:
            self._sessions[user_id] = Session("schedule", items[0])
            return event.plain_result("已识别生日：{}。发 /发布 提交，发 /取消 放弃。".format(self._fmt_birthday(items[0])))
        self._sessions[user_id] = Session("schedule_batch", {"items": items})
        titles = "、".join(x["title"] for x in items[:5])
        more = f"等{len(items)}条" if len(items) > 5 else ""
        return event.plain_result(f"已识别 {len(items)} 条生日：{titles}{more}，发 /发布 批量提交，发 /取消 放弃。")

    async def _start_anniversary(self, event: AstrMessageEvent, user_id: str, args: List[str], raw: str):
        """/纪念日 —— 专用纪念日命令，category 固定 anniversary、每年重复、全天。"""
        text = " ".join(args).strip()
        if not text:
            self._sessions[user_id] = Session("anniversary", {})
            return event.plain_result(
                "纪念日会话已创建，请发送纪念日内容（格式：标题 日期 [@人物]），如：\n"
                "我和宝宝认识的纪念日 1月1日 @宝宝\n"
                "结婚纪念日 农历5月20\n"
                "发 /发布 提交，发 /取消 放弃。"
            )
        parsed, err = parse_anniversary(text)
        if parsed is None:
            return event.plain_result("纪念日解析失败：{}，请重发（示例：结婚纪念日 农历5月20）或发 /取消。".format(err))
        self._apply_schedule_defaults(parsed)
        self._sessions[user_id] = Session("schedule", parsed)
        when = "农历{}月{}".format(parsed.get("lunarMonth"), parsed.get("lunarDay")) if parsed.get("isLunar") else parsed.get("date").strftime("%Y-%m-%d")
        return event.plain_result("已识别纪念日：{}（{}，每年重复）。发 /发布 提交，发 /取消 放弃。".format(parsed.get("title"), when))

    async def _list_daohang_folders(self, repo: str, branch: str, token: str) -> Optional[List[str]]:
        """列出 src/content/daohang 下的一级分类文件夹名。

        返回排序后的文件夹名列表；请求失败返回 None（区别于空目录的 []）。
        """
        url = "https://api.github.com/repos/{}/contents/src/content/daohang?ref={}".format(
            repo, urllib.parse.quote(branch)
        )
        headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            resp = await self._get_client().get(url, headers=headers)
            if resp.status_code != 200:
                return None
            import json as _json
            items = _json.loads(resp.text)
            names = []
            for it in items:
                if isinstance(it, dict) and it.get("type") == "dir":
                    n = str(it.get("name") or "").strip()
                    if n and not n.startswith("."):
                        names.append(n)
            return sorted(names)
        except Exception as e:
            logger.warning("BlogWriter: 列导航分类失败: %s", e)
            return None

    async def _start_daohang(self, event: AstrMessageEvent, user_id: str, args: List[str]):
        """/导航 网址 —— xxapi 取网站图标，向导选分类文件夹（2026-09-21 起分类=文件夹），
        键值对补名称/描述、#标签 补标签；/发布 上传图标到 blog/daohang 并提交 src/content/daohang/<分类>/。"""
        url = " ".join(args).strip()
        if not url:
            return event.plain_result("格式：/导航 网址（如：/导航 https://example.com），图标自动获取。")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        host = site_host(url)
        if "." not in host:
            return event.plain_result("网址无效，请检查（如：/导航 https://example.com）。")
        # xxapi 取图标（博客 scripts/添加导航 同款 API，无需 key）
        icon_url = ""
        try:
            resp = await self._get_client().get(build_xxapi_ico_url(url))
            icon_url, _err = parse_xxapi_ico_response(resp.status_code, resp.text)
        except Exception as e:
            logger.warning("BlogWriter: 图标接口请求失败: %s", e)
        icon_bytes = None
        if icon_url:
            icon_bytes = await self._download_http(icon_url)
        session = Session("daohang", {
            "url": url,
            "name": host,  # 默认名称=域名，可键值对改
            "category": "",  # 分类文件夹，待向导选择
            "description": "",
        })
        if icon_bytes:
            ext = (icon_url.rsplit(".", 1)[-1].split("?")[0].lower() or "png")
            if ext not in ("jpg", "jpeg", "png", "webp", "gif", "ico", "svg", "bmp"):
                ext = "png"
            session.add_image("{}-icon.{}".format(host, ext), icon_bytes)  # 对齐现有图床命名 blog.tsh520.com-icon.webp
            icon_hint = "图标已就绪"
        else:
            icon_hint = "⚠ 图标获取失败（将无图标发布，不影响其他字段）"
        self._sessions[user_id] = session
        # 向导：选分类文件夹（博客导航分类=文件夹，如 学习网站/AI 工具/未分类）
        repo = self._cfg("github_repo") or "mengkuikun/Blog-2.0"
        branch = self._cfg("github_branch") or "main"
        token = (self._cfg("github_token") or "").strip()
        folders = await self._list_daohang_folders(repo, branch, token)
        if not folders:
            # 列表拉取失败/为空：用配置默认分类，直接进入键值对
            session.meta["category"] = clean_filename_part(
                self._cfg("daohang_default_category", "未分类") or "未分类", fallback="未分类"
            )
            return event.plain_result(
                "{}：{}\n\n"
                "分类：{}（未能读取分类列表，可在配置 daohang_default_category 调整）\n"
                "可继续发（键值对，可多行）：名称: xxx / 描述: xxx / #标签\n"
                "发 /发布 提交，/取消 放弃。".format(icon_hint, host, session.meta["category"])
            )
        session.wizard = {"step": "daohang_pick_category", "folders": folders}
        return event.plain_result(
            "{}：{}\n\n".format(icon_hint, host)
            + format_choices("请选择分类（文件夹）：", folders, extra=["新建分类"], with_skip_cancel=False)
            + "\n也可直接回复分类名（如：学习网站）"
        )

    def _start_book(self, event: AstrMessageEvent, user_id: str, args: List[str]):
        """/书籍 书名 —— 封面用户自己发（无 API），评分/标签/书评同影视。"""
        name = " ".join(args).strip()
        if not name:
            return event.plain_result("格式：/书籍 书名（如：/书籍 认知觉醒），随后发封面图。")
        session = Session("book", {"title": name, "score": None, "tags": []})
        self._sessions[user_id] = session
        return event.plain_result(
            "《{}》书籍会话已创建。请直接发一张封面图（必须），\n"
            "然后可发：评分 8、#标签、书评文字（多条自动拼接），\n"
            "发 /发布 提交，/取消 放弃。".format(name)
        )

    def _media_type_prompt(self) -> str:
        items = [f"{label}（{val}）" for label, val in MEDIA_WIZARD_CATEGORIES]
        return format_choices("请选择类型：", items, with_skip_cancel=False)

    async def _start_media(self, event: AstrMessageEvent, user_id: str, args: List[str]):
        """/影视 片名 —— TMDB 搜索取中文片名+封面（字节立即下载入会话，/发布 时上传图床独立目录）。"""
        name = " ".join(args).strip()
        if not name:
            return event.plain_result("格式：/影视 片名（如：/影视 侏罗纪世界），封面自动从 TMDB 获取。")
        api_key = (self._cfg("tmdb_api_key") or "").strip()
        if not api_key:
            return event.plain_result(
                "未配置 tmdb_api_key。请到 themoviedb.org 免费注册 → 设置 → API 申请 v3 Key，填到插件配置。"
            )
        url = build_tmdb_search_url(name, api_key, self._cfg("tmdb_api_base"))
        try:
            resp = await self._get_client().get(url)
        except Exception as e:
            logger.warning("BlogWriter: TMDB 请求失败: %s", e)
            return event.plain_result("TMDB 请求失败（网络不通？可在配置 tmdb_api_base 填反代地址）。")
        info, err = parse_tmdb_search_response(resp.status_code, resp.text)
        if info is None:
            # TMDB 搜不到 → 手动模式：等用户发封面图，类型用向导选
            session = Session("media", {"title": name, "subcategory": "", "score": None, "tags": [], "manual": True})
            session.wizard = {"step": "media_need_cover"}
            self._sessions[user_id] = session
            return event.plain_result(
                "TMDB 未找到「{}」，已转手动模式：\n"
                "请直接发一张封面图（必须）。\n发图后我会让你选类型/评分/标签。".format(name)
            )
        # 下载封面字节（立即，避免发布时再等网络）
        poster_bytes = None
        if info["poster_path"]:
            poster_url = tmdb_poster_url(info["poster_path"], self._cfg("tmdb_image_base"))
            poster_bytes = await self._download_http(poster_url)
        ext = (info["poster_path"].rsplit(".", 1)[-1].lower() if "." in info["poster_path"] else "jpg")
        if ext not in ("jpg", "jpeg", "png", "webp"):
            ext = "jpg"
        filename = "{}.{}".format(clean_filename_part(info["title"]), ext)
        session = Session("media", {
            "title": info["title"],
            "subcategory": "movie" if info["media_type"] == "movie" else "tv",
            "score": None,
            "tags": [],
            "year": info["year"],
        })
        if poster_bytes:
            session.add_image(filename, poster_bytes)
        else:
            # 封面下载失败（无海报/CDN 不通）→ 手动模式，发图后走类型向导
            session.meta["manual"] = True
            session.wizard = {"step": "media_need_cover"}
            self._sessions[user_id] = session
            return event.plain_result(
                "已找到《{}》（{}）但封面下载失败，请直接发一张封面图。\n发图后我会让你选类型/评分/标签。".format(info["title"], info["year"] or "未知年份")
            )
        self._sessions[user_id] = session
        vote = info.get("vote_average")
        vote_hint = " TMDB评分{}".format(vote) if isinstance(vote, (int, float)) and vote else ""
        sub_label = "电影" if info["media_type"] == "movie" else "剧集"
        return event.plain_result(
            "已找到《{}》（{} {}）{}，封面已就绪。\n\n"
            "接下来可发：\n"
            "评分 8　→ 打分（0-10）\n"
            "#科幻 #冒险　→ 标签\n"
            "直接发文字　→ 一句话影评\n"
            "发 /发布 提交，/取消 放弃。".format(info["title"], info["year"] or "未知年份", sub_label, vote_hint)
        )

    def _handle_remind(self, event: AstrMessageEvent, user_id: str, args: List[str]):
        text = " ".join(args).strip().lower()
        # 取消
        if text.startswith("取消") or text.startswith("cancel"):
            target = text.replace("取消", "").replace("cancel", "").strip()
            if not target:
                return event.plain_result("用法：/提醒 取消 <标题关键词> 或 /提醒 取消 全部")
            try:
                data = self._load_reminders()
                before = len(data)
                if target in ("全部", "all", "所有"):
                    data = [d for d in data if d["user_id"] != user_id]
                    if HAS_APSCHEDULER and self._scheduler:
                        for job in list(self._scheduler.get_jobs()):
                            if job.id.startswith(user_id):
                                self._scheduler.remove_job(job.id)
                else:
                    new_data = []
                    for d in data:
                        if d["user_id"] == user_id and target in d["title"]:
                            if HAS_APSCHEDULER and self._scheduler:
                                try:
                                    self._scheduler.remove_job(d["id"])
                                except Exception:
                                    pass
                            continue
                        new_data.append(d)
                    data = new_data
                self._save_reminders(data)
                return event.plain_result(f"已取消 {before - len(data)} 条提醒。")
            except Exception as e:
                return event.plain_result(f"取消失败：{e}")
        # 列表
        try:
            data = self._load_reminders()
            mine = [d for d in data if d["user_id"] == user_id and datetime.fromisoformat(d["remind_at"]) > now_shanghai()]
            if not mine:
                # 兼容旧内存
                if hasattr(self, "_reminders") and self._reminders:
                    lines = ["提醒列表（内存）："]
                    for uid, title, at in self._reminders[-10:]:
                        if uid == user_id:
                            lines.append(f"- {title} 于 {at.strftime('%Y-%m-%d %H:%M:%S') if isinstance(at, datetime) else at}")
                    if len(lines) > 1:
                        return event.plain_result("\n".join(lines))
                return event.plain_result("当前无待提醒日程（可通过 /日程 创建带时间的提醒，系统将提前通知。可用 /提醒 取消 标题关键词 取消）")
            lines = ["提醒列表："]
            for d in mine[-10:]:
                rb = d.get("remind_before", self._cfg('schedule_remind_before',10))
                try:
                    rb = int(rb)
                except Exception:
                    rb = 10
                # 兼容旧数据：remind_at 可能为 naive，需按上海时间显示
                at_str = d['remind_at'].replace('T',' ')[:19]
                lines.append(f"- {d['title']} 于 {at_str} (提前{rb}分)")
            return event.plain_result("\n".join(lines))
        except Exception as e:
            return event.plain_result(f"读取提醒失败：{e}")

    # ---------- 消息入口 ----------

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id() or "")
        if not user_id:
            return

        async with self._lock:
            self._sweep()
            cmd, args, raw = parse_message(event.message_str)
            session = self._session(user_id)
            logger.info(
                "BlogWriter: 收到消息 user=%s cmd=%s has_session=%s msg_str=%r",
                user_id, cmd, session is not None, (event.message_str or "")[:60],
            )

            # 非白名单用户：静默忽略，不回复（避免在群聊中抢占其他插件/AI 的消息处理，
            # 也防止非白名单用户触发「无会话媒体提示」）
            if not self._allowed(user_id):
                logger.info(
                    "BlogWriter: 用户 %s（id=%s）无权限，已忽略。如需使用，请将 ID 加入 allow_users 配置。",
                    event.get_sender_name() or "?",
                    user_id,
                )
                return

            # 群聊白名单：配置了 allow_groups 后，列表外的群完全静默（含命令）
            if self._is_group_message(event) and not self._group_allowed(event):
                logger.info("BlogWriter: 群消息不在 allow_groups 白名单，已忽略 user=%s origin=%s",
                            user_id, getattr(event, "unified_msg_origin", ""))
                return

            # 与博客无关的消息（非命令、无进行中会话）一律放行，绝不回复
            if cmd not in COMMANDS and not session:
                # 例外：白名单用户**私聊**无会话时收到图片/视频 → 提示，避免媒体被静默丢弃；
                # 群聊里一律不插嘴（2026-09-15：群里随手发图被提示刷屏）
                if not self._is_group_message(event) and self._extract_images(event, allow_video=True):
                    logger.info("BlogWriter: 用户 %s 私聊无会话发送媒体，已提示", user_id)
                    # 本条消息已被插件完整消费，阻断传播（否则 LLM 阶段还会再收到）
                    _stop = getattr(event, "stop_event", None)
                    if callable(_stop):
                        _stop()
                    yield event.plain_result(
                        "当前没有进行中的会话，图片/视频未接收。请先发 /动态、/笔记、/足迹、/相册 等命令。"
                    )
                    return
                return

            # 命令或已有会话的消息由本插件完整消费：按官方规范 stop_event 阻断传播，
            # 否则 yield 结果后事件仍会进入 LLM 阶段（/ 前缀或 @ 唤醒时 LLM 会再答一次）
            _stop = getattr(event, "stop_event", None)
            if callable(_stop):
                _stop()

            if not self._cfg("github_token"):
                yield event.plain_result("插件未配置 GitHub Token，请在插件设置中填写后再使用。")
                return

            if cmd == "动态":
                yield self._start_moment(event, user_id, args)
                return
            if cmd == "笔记":
                yield await self._start_note(event, user_id, args)
                return
            if cmd == "足迹":
                yield self._start_place(event, user_id, args)
                return
            if cmd == "友链":
                yield self._start_friend(event, user_id, raw)
                return
            if cmd == "相册":
                yield await self._start_album(event, user_id, args)
                return
            if cmd == "账单":
                yield await self._start_bill(event, user_id, args, raw)
                return
            if cmd in ("存账", "记一笔"):
                yield await self._handle_save_bill(event, user_id, args)
                return
            if cmd == "查存账":
                yield self._handle_list_pending_bills(event, user_id)
                return
            if cmd == "清存账":
                yield self._handle_clear_pending_bills(event, user_id)
                return
            if cmd in ("撤回", "撤销"):
                yield await self._handle_recall_last_publish(event, user_id)
                return
            if cmd == "日程":
                yield await self._start_schedule(event, user_id, args, raw)
                return
            if cmd == "生日":
                yield await self._start_birthday(event, user_id, args, raw)
                return
            if cmd == "纪念日":
                yield await self._start_anniversary(event, user_id, args, raw)
                return
            if cmd == "影视":
                yield await self._start_media(event, user_id, args)
                return
            if cmd == "书籍":
                yield self._start_book(event, user_id, args)
                return
            if cmd == "导航":
                yield await self._start_daohang(event, user_id, args)
                return
            if cmd == "转载":
                yield await self._handle_article(event, user_id, args)
                return
            if cmd == "提醒":
                yield self._handle_remind(event, user_id, args)
                return
            if cmd == "发布":
                yield await self._publish(event, user_id)
                return
            if cmd == "取消":
                self._sessions.pop(user_id, None)
                yield event.plain_result("已取消当前会话。")
                return
            if cmd == "状态":
                if session:
                    yield event.plain_result(
                        "当前会话：{}（文本 {} 条、图片 {} 张）。".format(
                            session.kind, len(session.text_parts), len(session.images)
                        )
                    )
                else:
                    yield event.plain_result("当前没有进行中的会话。")
                return
            if cmd == "帮助":
                yield event.plain_result(self._help_text())
                return

            # 非命令消息：归入会话
            if session:
                if session.expired():
                    self._sessions.pop(user_id, None)
                    yield event.plain_result("上一个会话已超时作废，请重新发指令。")
                    return
                # 影视/书籍：先一次性探测封面图（避免向导拦截图片、避免重复提取日志）
                allow_video = session.kind == "moment"  # 视频仅动态支持；笔记/足迹/相册仍只收图片
                cover_payload = None
                if session.kind in ("media", "book"):
                    cover_refs = self._extract_images(event, allow_video=False)
                    if cover_refs:
                        cover_data = await self._read_image_bytes(cover_refs[-1])
                        if cover_data is not None:
                            cover_payload = (cover_refs[-1], cover_data)
                    else:
                        # 兜底：微信 raw_message 加密媒体 curl 下载（下载的字节直接作封面）
                        for enc, aes_hex, aes_b64, _kind in self._extract_wx_raw_media(event, allow_video=False):
                            dl = await self._download_wx_media(enc, aes_hex, aes_b64)
                            if dl is not None:
                                cover_payload = ("wxraw_{}.jpg".format(enc[:16]), dl)
                                break
                if cover_payload is not None:
                    ref, data = cover_payload
                    filename = ref.rsplit("/", 1)[-1].split("?")[0].split("#")[0] or "cover.jpg"
                    if "." not in filename:
                        filename += ".jpg"
                    base_title = session.meta.get("title") or "cover"
                    filename = "{}{}".format(
                        clean_filename_part(base_title),
                        filename[filename.rfind("."):] if "." in filename else ".jpg",
                    )
                    session.images.clear()
                    session.add_image(filename, data)
                    session.touch()
                    # 手动模式下发图后进入类型向导
                    if getattr(session, "wizard", None) and session.wizard.get("step") == "media_need_cover":
                        session.wizard = {"step": "media_pick_category"}
                        yield event.plain_result(
                            "封面已更新。\n" + self._media_type_prompt()
                        )
                        return
                    yield event.plain_result(
                        "封面已更新（发布时上传图床）。继续发评分/#标签/影评，或 /发布 提交。"
                    )
                    return
                # 无图：向导分发（如有）
                if getattr(session, "wizard", None):
                    res = await self._handle_wizard(event, user_id, raw)
                    if res is not None:
                        yield res
                        return
                images = self._extract_images(event, allow_video=allow_video)
                if images:
                    logger.info("BlogWriter: 提取到 %d 张图片引用: %s", len(images), images[:3])
                    stored = []
                    for ref in images:
                        # 立即读取字节：data/temp 临时文件在消息处理完后会被清理
                        data = await self._read_image_bytes(ref)
                        if data is None:
                            logger.warning("BlogWriter: 图片读取失败: %s", ref)
                            yield event.plain_result(
                                "图片读取失败（{}），请重发。".format(ref[:60])
                            )
                            return
                        stored.append((ref, data))
                else:
                    # 兜底：适配器下载媒体失败（如微信 CDN TLS 握手被拒）时，
                    # 从 raw_message 提取加密参数，用 curl 下载 + AES 解密。
                    raw_media = self._extract_wx_raw_media(event, allow_video=allow_video)
                    if raw_media:
                        logger.info("BlogWriter: 尝试 curl 兜底下载 %d 张微信媒体", len(raw_media))
                        stored = []
                        for enc, aes_hex, aes_b64, kind in raw_media:
                            data = await self._download_wx_media(enc, aes_hex, aes_b64)
                            if data is None:
                                yield event.plain_result(
                                    "微信媒体下载失败（CDN 握手异常且 curl 兜底失败），请重发。"
                                )
                                return
                            suffix = ".mp4" if kind == "video" else ""
                            stored.append(("wxraw_{}{}".format(enc[:16], suffix), data))
                    else:
                        stored = []
                if stored:
                    session.touch()
                    for ref, data in stored:
                        session.add_image(ref, data)
                    logger.info("BlogWriter: 图片已入会话，共 %d 张", len(session.images))
                    yield event.plain_result(
                        "已收到 {} 张图片（共 {} 张）。发 /发布 结束，发 /取消 放弃。".format(
                            len(stored), len(session.images)
                        )
                    )
                    return
                logger.info("BlogWriter: 消息链中未发现图片组件（共 %d 个组件）", len(event.get_messages()))
                text = raw.strip()
                if text:
                    session.touch()
                    if session.kind == "friend":
                        data = parse_friend_text(text)
                        if data:
                            session.meta.update(data)
                            summary = "，".join(
                                "{}：{}".format(k, v[:40]) for k, v in data.items()
                            )
                            yield event.plain_result(
                                "已识别：{}\n\n发 /发布 提交，发 /取消 放弃。".format(summary)
                            )
                        else:
                            yield event.plain_result(
                                "未能识别有效字段，请按「站点名称: xxx」这样的格式发送。"
                            )
                    elif session.kind == "album":
                        # 相册会话只收图片（博客相册由图床目录动态加载，md 只需标题/日期）
                        yield event.plain_result(
                            "相册只接收图片。请直接发图片，或发 /发布 提交、/取消 放弃。"
                        )
                    elif session.kind in ("bill", "bill_batch"):
                        # 手动修改：分类:餐饮 / 账户:支付宝 / 日期:2026-10-08 / 时间:14:30 / 金额:30 / 标题:午餐
                        m_cat = re.match(r"^(?:分类|类别|category)\s*[:：]?\s*(\S{1,10})\s*$", text)
                        m_acc = re.match(r"^(?:账户|账号|account)\s*[:：]?\s*(\S{1,10})\s*$", text)
                        m_date = re.match(r"^(?:日期|date)\s*[:：]?\s*(.+)$", text)
                        m_time = re.match(r"^(?:时间|时刻|time)\s*[:：]?\s*(.+)$", text)
                        m_amt = re.match(r"^(?:金额|多少钱|amount)\s*[:：]?\s*(-?\d+(?:\.\d+)?)\s*(?:块钱|元钱|块|元)?$", text)
                        m_title = re.match(r"^(?:标题|备注|名称|title)\s*[:：]?\s*(.+)$", text)
                        if m_cat or m_acc or m_date or m_time or m_amt or m_title:
                            if session.kind == "bill_batch":
                                yield event.plain_result("批量账单暂不支持逐条修改，请发 /取消 后重新记录。")
                                return
                            if m_cat:
                                cat = m_cat.group(1)
                                session.meta["category"] = cat
                            elif m_acc:
                                acc = m_acc.group(1)
                                session.meta["account"] = acc
                            elif m_date:
                                dt = _parse_bill_date(m_date.group(1).strip(), now_shanghai())
                                session.meta["date"] = dt
                            elif m_time:
                                tm = _parse_bill_time(m_time.group(1).strip(), now_shanghai())
                                if tm:
                                    session.meta["time"] = tm
                            elif m_amt:
                                val = float(m_amt.group(1))
                                if session.meta.get("type") == "expense":
                                    session.meta["amount"] = -abs(val)
                                else:
                                    session.meta["amount"] = abs(val)
                            elif m_title:
                                t = m_title.group(1).strip()
                                session.meta["title"] = t
                                session.meta["description"] = t

                            session.touch()
                            t_val = session.meta.get("type", "expense")
                            l_val = "支出" if t_val == "expense" else "收入"
                            d_val = session.meta.get("date")
                            ds_val = d_val.strftime("%Y-%m-%d") if isinstance(d_val, datetime) else str(d_val)[:10]

                            if m_cat:
                                prefix = f"已修改分类：{session.meta['category']}。"
                            elif m_acc:
                                prefix = f"已修改账户：{session.meta['account']}。"
                            elif m_date:
                                prefix = f"已修改日期：{ds_val}。"
                            elif m_time:
                                prefix = f"已修改时间：{session.meta.get('time', '')}。"
                            elif m_amt:
                                prefix = f"已修改金额：{session.meta.get('amount')}。"
                            elif m_title:
                                prefix = f"已修改标题：{session.meta.get('title')}。"
                            else:
                                prefix = "已更新账单信息。"

                            yield event.plain_result(
                                "{}当前账单：{} 金额{}，分类{}，账户{}。发 /发布 提交。".format(
                                    prefix,
                                    session.meta.get("title"),
                                    session.meta.get("amount"),
                                    session.meta.get("category"),
                                    session.meta.get("account"),
                                )
                            )
                            return
                        # 空会话后下一句口语：正则解析（支持批量）
                        try:
                            batch, _ = parse_bills_batch(text)
                            if batch and len(batch) > 1:
                                for item in batch:
                                    self._apply_bill_defaults(item)
                                session.kind = "bill_batch"
                                session.meta = {"items": batch}
                                session.touch()
                                titles = "、".join(f"{x['title']}{x['amount']}" for x in batch[:5])
                                yield event.plain_result(f"已识别 {len(batch)} 笔账单：{titles}，发 /发布 批量提交，发 /取消 放弃。")
                                return
                        except Exception:
                            pass
                        parsed, err = parse_bill(text)
                        if parsed:
                            self._apply_bill_defaults(parsed)
                            session.meta.update(parsed)
                            session.kind = "bill"
                            session.touch()
                            # 与 /账单 带参路径统一：进入类型确认向导
                            session.wizard = {"step": "bill_confirm_type"}
                            t = parsed.get("type")
                            label = self._BILL_TYPE_LABELS.get(t, t)
                            yield event.plain_result(
                                "已识别账单：{} 金额{}（{}），分类{}，账户{}\n\n".format(
                                    parsed.get("title"), parsed.get("amount"), label,
                                    parsed.get("category"), parsed.get("account"))
                                + self._bill_type_prompt()
                                + f"\n\n当前猜测：{label}（选对应数字，或 5 直接发布）"
                            )
                        else:
                            yield event.plain_result("账单解析失败：{}，请重发。".format(err))
                    elif session.kind == "daohang":
                        # 导航会话：键值对（名称/描述；分类=文件夹，发「分类: xxx」可改），#标签 追加标签
                        # 先摘 #标签 再解析键值对，避免标签粘在描述里（tags 2026-09-21 起回归为可选字段）
                        kv_text, tags = extract_tags(text)
                        kv = parse_daohang_text(kv_text)
                        if kv:
                            for k, v in kv.items():
                                if k == "category":
                                    # 分类改为文件夹名：清洗后写入（对齐博客 2026-09-21 文件夹分类）
                                    v = clean_filename_part(v, fallback="")
                                    if not v:
                                        continue
                                session.meta[k] = v
                        if tags:
                            existing = session.meta.setdefault("tags", [])
                            for t in tags:
                                if t not in existing:
                                    existing.append(t)
                        session.touch()
                        summary = "，".join(
                            "{}：{}".format(label, str(session.meta.get(key))[:30])
                            for key, label in (("name", "名称"), ("category", "分类"), ("description", "描述"))
                            if session.meta.get(key)
                        )
                        tag_hint = (
                            "，标签：{}".format(" ".join("#" + t for t in session.meta.get("tags", [])))
                            if session.meta.get("tags")
                            else ""
                        )
                        yield event.plain_result(
                            "已记录：{}{}。发 /发布 提交，发 /取消 放弃。".format(summary, tag_hint)
                        )
                        return
                    elif session.kind in ("media", "book"):
                        # 影视/书籍会话：键值对（名称/类型）→ 评分行 → #标签 → 其余为正文
                        fields = parse_media_fields(text)
                        if fields:
                            if fields.get("title"):
                                session.meta["title"] = fields["title"]
                            if fields.get("subcategory"):
                                session.meta["subcategory"] = fields["subcategory"]
                            session.touch()
                            yield event.plain_result(
                                "已修改：{}。发 /发布 提交，发 /取消 放弃。".format(
                                    "，".join("{}={}".format(k, v) for k, v in fields.items())
                                )
                            )
                            return
                        score = parse_media_score(text)
                        if score is not None:
                            session.meta["score"] = score
                            session.touch()
                            yield event.plain_result("已记录评分：{}。发 /发布 提交，发 /取消 放弃。".format(score))
                            return
                        clean, tags = extract_tags(text)
                        if tags:
                            existing = session.meta.setdefault("tags", [])
                            for t in tags:
                                if t not in existing:
                                    existing.append(t)
                        if clean:
                            session.add_text(clean)
                        session.touch()
                        tag_hint = "，标签：{}".format(" ".join("#" + t for t in session.meta.get("tags", []))) if session.meta.get("tags") else ""
                        score_hint = "，评分：{}".format(session.meta.get("score")) if session.meta.get("score") is not None else ""
                        yield event.plain_result("已记录{}{}。发 /发布 提交，发 /取消 放弃。".format(score_hint, tag_hint))
                        return
                    elif session.kind == "birthday":
                        # 生日会话：下一句口语走批量生日正则（支持单条与多个人物）
                        items, err = parse_schedules_batch(text)
                        if not items:
                            yield event.plain_result("生日解析失败：{}，请重发（示例：我的农历8.24）。".format(err))
                            return
                        for item in items:
                            self._apply_schedule_defaults(item)
                        if len(items) == 1:
                            session.meta.update(items[0])
                            session.kind = "schedule"
                        else:
                            session.kind = "schedule_batch"
                            session.meta = {"items": items}
                        session.touch()
                        titles = "、".join(x["title"] for x in items[:5])
                        more = f"等{len(items)}条" if len(items) > 5 else ""
                        yield event.plain_result(f"已识别生日：{titles}{more}。发 /发布 提交，发 /取消 放弃。")
                        return
                    elif session.kind == "anniversary":
                        # 纪念日会话：下一句口语走纪念日正则
                        parsed, err = parse_anniversary(text)
                        if parsed is None:
                            yield event.plain_result("纪念日解析失败：{}，请重发（示例：结婚纪念日 农历5月20）。".format(err))
                            return
                        self._apply_schedule_defaults(parsed)
                        session.meta.update(parsed)
                        session.kind = "schedule"
                        session.touch()
                        yield event.plain_result(
                            "已识别纪念日：{}。发 /发布 提交，发 /取消 放弃。".format(parsed.get("title"))
                        )
                        return
                    elif session.kind in ("schedule", "schedule_batch"):
                        # 空会话后下一句口语：优先批量生日正则，再单条正则
                        try:
                            batch, _ = parse_schedules_batch(text)
                            if batch and len(batch) > 1:
                                for item in batch:
                                    self._apply_schedule_defaults(item)
                                session.kind = "schedule_batch"
                                session.meta = {"items": batch}
                                session.touch()
                                titles = "、".join(x["title"] for x in batch[:5])
                                yield event.plain_result(f"已识别 {len(batch)} 条生日：{titles}，发 /发布 批量提交，发 /取消 放弃。")
                                return
                        except Exception:
                            pass
                        # 防呆：生日/纪念日走专用命令
                        if "生日" in text or "生气" in text:
                            yield event.plain_result("检测到生日内容，请取消后用 /生日 命令添加（如：/生日 我的农历8.24）。")
                            return
                        if "纪念日" in text:
                            yield event.plain_result("检测到纪念日内容，请取消后用 /纪念日 命令添加（如：/纪念日 结婚纪念日 农历5月20）。")
                            return
                        parsed, err = parse_schedule(text)
                        if parsed:
                            self._apply_schedule_defaults(parsed)
                            session.meta.update(parsed)
                            session.kind = "schedule"
                            session.touch()
                            yield event.plain_result(
                                "已识别日程：{} 时间{}。发 /发布 提交，发 /取消 放弃。".format(
                                    parsed.get("title"),
                                    parsed.get("date").strftime("%Y-%m-%d %H:%M:%S") if isinstance(parsed.get("date"), datetime) else parsed.get("date"),
                                )
                            )
                        else:
                            yield event.plain_result("日程解析失败：{}，请重发。".format(err))
                    else:
                        session.add_text(text)
                        yield event.plain_result("内容已追加。发 /发布 提交，发 /取消 放弃。")
                    return
            # 其他消息一律放行（不 yield 结果即放行）
            return

    # ---------- 会话创建 ----------

    def _session(self, user_id: str) -> Optional[Session]:
        return self._sessions.get(user_id)

    def _start_moment(self, event: AstrMessageEvent, user_id: str, args: List[str]):
        content, tags = parse_dynamic(args)
        if not content:
            return event.plain_result("格式：/动态 内容 [#标签]（例如：/动态 今天去了公园 #日常）")
        self._sessions[user_id] = Session("moment", {"content": content, "tags": tags})
        tag_hint = "，标签：{}".format(" ".join("#" + t for t in tags)) if tags else ""
        return event.plain_result(
            "动态已创建：{}{}\n\n可以直接发图片、动图 GIF 或视频（可多发），发完说 /发布。".format(content, tag_hint)
        )

    async def _start_note(self, event: AstrMessageEvent, user_id: str, args: List[str]):
        default_dir = self._cfg("default_note_dir") or "日常随笔"
        # 带参快车道：/笔记 分类 标题（分类名清洗，防路径注入）
        if args:
            note_dir, title = parse_note(args, default_dir)
            if title:
                note_dir = clean_filename_part(note_dir, fallback=default_dir)
                self._sessions[user_id] = Session("note", {"note_dir": note_dir, "title": title})
                return event.plain_result(
                    "笔记已创建：分类「{}」标题「{}」。\n\n接下来直接发正文（可多条，自动拼接），也可以发图片，发完说 /发布。".format(
                        note_dir, title
                    )
                )
        # 空参进向导：先选笔记本
        repo = self._cfg("github_repo") or "mengkuikun/Blog-2.0"
        branch = self._cfg("github_branch") or "main"
        token = (self._cfg("github_token") or "").strip()
        names = await self._list_notebook_names(repo, branch, token)
        if not names:
            names = [default_dir]
        # 去重并把默认放首位
        uniq = []
        seen = set()
        for n in [default_dir] + names:
            if n not in seen:
                seen.add(n)
                uniq.append(n)
        sess = Session("note", {"note_dir": "", "title": ""})
        sess.wizard = {"step": "note_pick_notebook", "notebooks": uniq, "default_dir": default_dir}
        self._sessions[user_id] = sess
        return event.plain_result(
            format_choices("请选择笔记本：", uniq, extra=["新建笔记本"], with_skip_cancel=False)
            + "\n\n也可直接回复笔记本名称新建。"
        )

    def _start_friend(self, event: AstrMessageEvent, user_id: str, raw: str):
        """/友链 [键值对文本]。后续文本消息继续追加解析。"""
        rest = re.sub(r"^/?(友链)\s*", "", raw or "", count=1).strip()
        session = Session("friend", {})
        if rest:
            data = parse_friend_text(rest)
            session.meta.update(data)
        self._sessions[user_id] = session
        lines = [
            "友链会话已创建。请发送友链信息（每行一条，格式随意，我会自动识别）：",
            "站点名称: 名称",
            "站点描述: 一句话介绍",
            "站点链接: https://xxx.com",
            "头像链接: https://头像图片地址 或 /相对路径",
            "发 /发布 提交，发 /取消 放弃。",
        ]
        if rest:
            lines.insert(0, "已识别到内容，还可在下一条消息补充或修改。")
        return event.plain_result("\n".join(lines))

    def _start_place(self, event: AstrMessageEvent, user_id: str, args: List[str]):
        province, city, experience, tags = parse_place(args)
        if not province or not city:
            return event.plain_result("格式：/足迹 省 地点 体验 [#标签]（例如：/足迹 陕西 华阴市华山 去找宝宝了 #旅游 #2026）")
        self._sessions[user_id] = Session(
            "place",
            {"province": province, "city": city, "experience": experience, "tags": tags},
        )
        tag_hint = "，标签：{}".format(" ".join("#" + t for t in tags)) if tags else ""
        return event.plain_result(
            "足迹已创建：{} {}{}（坐标将用高德地理编码获取）。\n\n可以直接发照片（可多发），发完说 /发布。".format(
                province, city, tag_hint
            )
        )

    async def _start_album(self, event: AstrMessageEvent, user_id: str, args: List[str]):
        # 带参快车道
        name = parse_album(args)
        if name:
            self._sessions[user_id] = Session("album", {"name": name})
            return event.plain_result(
                "相册「{}」已创建。\n\n请直接发图片（可多发），发完说 /发布。".format(name)
            )
        # 空参进向导：列出现有相册（一次拉取，排序后同时生成展示与映射，保证选项不错位）
        repo = self._cfg("github_repo") or "mengkuikun/Blog-2.0"
        branch = self._cfg("github_branch") or "main"
        token = (self._cfg("github_token") or "").strip()
        idx = await self._album_index(repo, branch, token)
        if idx is None:
            return event.plain_result("GitHub 查询失败（网络或 Token 问题），请稍后重试或直接发 /相册 相册名 快捷创建。")
        entries = list(idx.get("entries") or [])
        entries.sort(key=lambda e: e[0])  # 按 title 排序
        titles = [t for t, _f, _fd in entries]
        display = ["{}（{}）".format(t, f) for t, f, _fd in entries]
        sess = Session("album", {"name": ""})
        sess.wizard = {"step": "album_pick", "display": display, "titles": titles}
        self._sessions[user_id] = sess
        if not display:
            return event.plain_result("当前还没有相册，直接回复新相册名称即可创建。\n回复“取消”退出。")
        return event.plain_result(
            format_choices("请选择相册：", display, extra=["新建相册"], with_skip_cancel=False)
        )

    _WX_ARTICLE_UA = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.44(0x18002c2d) NetType/WIFI Language/zh_CN"
    )

    @staticmethod
    def _wx_image_ext(url: str, data: bytes) -> str:
        """推断微信文章图片扩展名：wx_fmt 参数 → URL 后缀 → 魔数兜底。"""
        m = re.search(r"[?&]wx_fmt=([a-zA-Z0-9]+)", url or "")
        fmt = (m.group(1).lower() if m else "")
        mapping = {"jpeg": "jpg", "jpg": "jpg", "png": "png", "gif": "gif", "webp": "webp", "bmp": "bmp"}
        if fmt in mapping:
            return mapping[fmt]
        base = (url or "").split("?")[0].rsplit(".", 1)
        if len(base) == 2 and base[1].lower() in mapping:
            return mapping[base[1].lower()]
        if data[:3] == b"\xff\xd8\xff":
            return "jpg"
        if data[:8].startswith(b"\x89PNG"):
            return "png"
        if data[:4] == b"GIF8":
            return "gif"
        if data[:4] == b"RIFF":
            return "webp"
        return "jpg"

    async def _handle_article(self, event: AstrMessageEvent, user_id: str, args: List[str]):
        """/转载 公众号文章链接 —— 抓取 → 解析 → 图片转存图床 → 生成 posts 文章 → 提交（直发，不进会话）。

        实测（2026-09-16 本地验证）：直连抓取正常（HTTP 200，无验证页）；
        微信对部分服务器 IP 会返回「环境异常」验证页 → extract_wx_article 检测后明确报错；
        图片 mmbiz.qpic.cn 无 Referer 可下载，失败再带 Referer 重试（防盗链兜底）。
        原子性：标题解析失败 / 任一张图下载或上传失败 → 中止发布，绝不半成品提交。
        """
        url = extract_wx_url(" ".join(args).strip())
        if not url:
            return event.plain_result("格式：/转载 公众号文章链接（如：/转载 https://mp.weixin.qq.com/s/xxxx）")
        # 1) 抓取（MicroMessenger UA + Referer）
        headers = {
            "User-Agent": self._WX_ARTICLE_UA,
            "Referer": "https://mp.weixin.qq.com/",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        html = ""
        for attempt in range(RETRY_COUNT + 1):
            try:
                resp = await self._get_client().get(url, headers=headers)
                if resp.status_code >= 400:
                    return event.plain_result("转载中止：抓取失败 HTTP {}（请确认链接在微信里可正常打开）。".format(resp.status_code))
                html = resp.text
                break
            except Exception as e:
                logger.warning("BlogWriter: 转载抓取失败(第%d次): %s", attempt + 1, e)
                if attempt < RETRY_COUNT:
                    await asyncio.sleep(RETRY_DELAYS[attempt])
        if not html:
            return event.plain_result("转载中止：网络错误，请稍后重试。")
        data, err = extract_wx_article(html)
        if data is None:
            return event.plain_result("转载中止：{}。".format(err))
        # 2) 图片：下载 → 转存图床（任一失败即中止）
        image_urls: List[str] = []
        if data["image_urls"]:
            stored = []
            for idx, src in enumerate(data["image_urls"]):
                img = await self._download_http(src)
                if img is None:
                    img = await self._download_http(src, referer="https://mp.weixin.qq.com/")
                if img is None:
                    return event.plain_result("转载中止：第 {} 张图片下载失败，请稍后重试。".format(idx + 1))
                stored.append(("article-{}.{}".format(idx + 1, self._wx_image_ext(src, img)), img))
            result = await self._upload_images(stored, self._cfg("article_upload_folder") or "blog/article")
            if isinstance(result, str):
                return event.plain_result("转载中止：图片转存图床失败：{}".format(result))
            image_urls = result
        # 3) 生成 md 并提交
        now = now_shanghai()
        body_md = assemble_article_body(data["body_md"], image_urls)
        md = build_article_md(
            data["title"],
            body_md,
            image_urls,
            self._merge_tags(self._cfg("article_tags", ["转载"]), []),
            description=data["digest"],
            source_link=url,
            author=data["author"],
            publish_date=data["publish_date"],
            now=now,
        )
        article_dir = clean_filename_part(self._cfg("article_default_dir") or "技术分享", fallback="技术分享")
        file_name = clean_filename_part(data["title"], fallback="转载文章")
        path = "src/content/posts/{}/{}.md".format(article_dir, file_name)
        ok, final_path, err2 = await self._commit_md(path, md, now)
        if not ok:
            return event.plain_result("转载提交失败：{}".format(err2))
        slug = final_path[len("src/content/posts/"):-len(".md")]
        blog_base = (self._cfg("blog_base_url") or "https://imki.cn").rstrip("/")
        return event.plain_result(
            "转载成功 ✅\n\n标题：{}\n公众号：{}\n文件：{}\n博客：{}/posts/{}".format(
                data["title"], data["author"] or "未知", final_path, blog_base, slug
            )
        )

    # ---------- 发布 ----------

    async def _publish_pending_bills(self, event: AstrMessageEvent, user_id: str) -> MessageEventResult:
        pending = self._pending_bills.get(user_id) or []
        if not pending:
            return event.plain_result("待发暂存箱为空，无法发布。")

        now = now_shanghai()
        raw_files: List[Tuple[str, str]] = []
        for item in pending:
            try:
                md_item = build_bill_md(item, now)
                title_item = str(item.get("title") or "账单").strip() or "账单"
                slug_item = clean_filename_part(title_item)
                date_val = item.get("date") or now
                if isinstance(date_val, datetime):
                    date_str = date_val.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_val).strip()[:10] or now.strftime("%Y-%m-%d")
                path_item = "src/content/bills/{}-{}.md".format(date_str, slug_item)
                raw_files.append((path_item, md_item))
            except Exception as e:
                return event.plain_result(f"暂存账单「{item.get('title', '?')}」生成失败：{e}，发布已中止。")

        commit_msg = f"blog: 通过 AstrBot 暂存箱合并发布 {len(raw_files)} 笔账单"
        ok, err = await self._commit_batch_md(raw_files, commit_msg, now)
        if not ok:
            return event.plain_result(f"暂存箱合并发布失败：{err}（数据仍安全保留在暂存箱中，请重试）")

        published_items = self._pending_bills.pop(user_id, [])
        self._save_pending_bills()
        self._last_published[user_id] = {
            "time": now,
            "paths": [f[0] for f in raw_files],
            "items": published_items,
            "kind": "bill_pending",
        }

        total_exp = sum(abs(it.get("amount", 0)) for it in published_items if it.get("type") == "expense")
        total_inc = sum(abs(it.get("amount", 0)) for it in published_items if it.get("type") == "income")
        stats = []
        if total_exp > 0:
            stats.append(f"支出 ¥{total_exp:.2f}")
        if total_inc > 0:
            stats.append(f"收入 ¥{total_inc:.2f}")
        stats_str = "、".join(stats) or "¥0.00"

        blog_base = (self._cfg("blog_base_url") or "https://imki.cn").rstrip("/")
        return event.plain_result(
            f"🎉 暂存箱发布成功 ✅\n\n"
            f"共 {len(raw_files)} 笔账单已合并为 1 个 Git Commit 写入博客，仅触发 1 次部署！\n"
            f"📊 汇总：{stats_str}\n"
            f"🌐 博客流水：{blog_base}/bills\n\n"
            f"（💡 如发现记错，可于 10 分钟内发送 /撤回 一键回滚）"
        )

    async def _publish(self, event: AstrMessageEvent, user_id: str) -> MessageEventResult:
        session = self._session(user_id)
        if not session:
            if self._pending_bills.get(user_id):
                return await self._publish_pending_bills(event, user_id)
            return event.plain_result("当前没有进行中的会话，请先发 /动态、/笔记、/足迹、/友链、/相册、/账单 或 /日程。")
        repo = self._cfg("github_repo") or "mengkuikun/Blog-2.0"
        branch = self._cfg("github_branch") or "main"
        token = (self._cfg("github_token") or "").strip()
        album_folder = None
        album_exists = False
        if session.kind == "moment":
            content = ((session.meta.get("content") or "") + "\n\n" + session.full_text()).strip()
            if not content:
                return event.plain_result("动态内容为空，无法发布。")
        elif session.kind == "note" and not session.full_text():
            return event.plain_result("笔记正文为空，无法发布。")
        elif session.kind == "friend":
            ok, err = validate_friend_data(session.meta)
            if not ok:
                return event.plain_result("友链信息不完整：{}。可继续发送补充（格式：站点名称: xxx），或发 /取消。".format(err))
        elif session.kind == "album":
            album_name = (session.meta.get("name") or "").strip()
            if not album_name:
                return event.plain_result("相册名为空，无法发布。")
            if not session.images:
                return event.plain_result("相册至少需要一张图片，无法发布。")
            # 按 title/文件名判断相册是否已存在：博客相册文件名与 title 不一定相同
            # （如 xiangce1.md 的 title 是「测试相册」），必须读文件内容才能对齐。
            album_index = await self._album_index(repo, branch, token)
            if album_index is None:
                return event.plain_result("GitHub 查询失败（网络或 Token 问题），已中止发布。")
            fname = clean_filename_part(album_name)
            default_folder = "{}/{}".format(
                (self._cfg("album_folder_prefix") or "blog/album").strip().strip("/"),
                fname,
            )
            matched_folder = album_index["titles"].get(album_name)
            if matched_folder is not None:
                # title 命中已有相册：追加到它自己的 imgbedFolder
                album_exists = True
                album_folder = matched_folder or default_folder
            elif (fname + ".md") in album_index["files"]:
                # 文件名命中（title 不同）：同样追加
                album_exists = True
                album_folder = album_index["files"][fname + ".md"] or default_folder
            else:
                album_folder = default_folder

        # 1. 图片处理（失败即中止，不写 md）
        image_urls = []
        if session.images:
            if session.kind == "album":
                folder = album_folder
            elif session.kind in ("media", "book"):
                # 影视/书籍封面独立目录（对齐博客图床惯例 blog/bangumi）
                folder = self._cfg("bangumi_upload_folder") or "blog/bangumi"
            elif session.kind == "daohang":
                # 导航图标独立目录（对齐博客图床惯例 blog/daohang）
                folder = self._cfg("daohang_upload_folder") or "blog/daohang"
            else:
                # 博客图床目录已统一（2026-08-13）：插件上传的图片全部进 imgbed_upload_folder（默认 blog/moments）
                folder = self._cfg("imgbed_upload_folder") or "blog/moments"
            result = await self._upload_images(session.images, folder)
            if isinstance(result, str):
                return event.plain_result("图片上传失败，已中止发布：{}".format(result))
            image_urls = result

        # 2. 生成 markdown
        try:
            now = now_shanghai()
            if session.kind == "moment":
                md = build_moment_md(
                    content,
                    image_urls,
                    self._merge_tags(self._cfg("moment_tags", ["日常"]), session.meta.get("tags")),
                    now,
                )
                path = "src/content/moments/{}.md".format(moment_filename(now))
                link = "/moments/{}".format(moment_filename(now))
            elif session.kind == "note":
                md = build_note_md(
                    session.meta.get("title", ""),
                    session.full_text(),
                    image_urls,
                    now,
                )
                note_dir = clean_filename_part(session.meta.get("note_dir") or "日常随笔", fallback="日常随笔")
                # 新笔记本先补 _index.json（博客书架/归档靠它识别，缺了文件夹不可见）
                index_created = False
                ok_idx, err_idx = await self._ensure_notebook_index(note_dir, repo, branch, token)
                if not ok_idx and err_idx:
                    return event.plain_result("新笔记本 _index.json 创建失败：{}，已中止发布（避免出现不可见笔记）。".format(err_idx))
                index_created = ok_idx
                path = "src/content/life/notebooks/{}/{}.md".format(note_dir, note_filename(now))
                link = "/life/notebooks/{}/{}".format(note_dir, note_filename(now))
            elif session.kind == "friend":
                friend_index = await self._github_list_dir_index(
                    "src/content/friends", repo, branch, token
                )
                title = session.meta.get("title", "").strip()
                md = build_friend_md(
                    title,
                    (session.meta.get("desc") or "").strip(),
                    session.meta.get("siteurl", "").strip(),
                    (session.meta.get("imgurl") or "").strip()
                    or (self._cfg("friend_default_avatar") or "/assets/ziyuan/tx.webp"),
                    self._cfg("friend_tags") or ["Blog"],
                )
                path = "src/content/friends/{:02d}-{}.md".format(
                    friend_index, clean_filename_part(title)
                )
                link = "/friends"
            elif session.kind == "album":
                album_name = (session.meta.get("name") or "").strip()
                clean_name = clean_filename_part(album_name)
                if album_exists:
                    # 追加模式：相册已存在（按 title/文件名命中），只传图不写文件。
                    # 博客详情页运行时从图床目录动态拉图，照片即时可见；列表页预览下次构建后更新。
                    self._sessions.pop(user_id, None)
                    return event.plain_result(
                        "已添加到相册「{}」：{} 张照片。\n照片在详情页即时可见（列表页预览将在下次构建后更新）。".format(
                            album_name, len(session.images)
                        )
                    )
                md = build_album_md(album_name, album_folder, now)
                path = "src/content/album/{}.md".format(clean_name)
                link = "/album/{}".format(clean_name)
            elif session.kind == "daohang":
                # 导航条目（2026-09-21 对齐博客）：分类=文件夹，
                # 条目写 name/url/icon/description + 可选 tags（color/image/featured/order 已从 schema 删除）
                icon_url = image_urls[0] if image_urls else ""
                daohang_cat = clean_filename_part(
                    session.meta.get("category") or self._cfg("daohang_default_category", "未分类") or "未分类",
                    fallback="未分类",
                )
                md = build_daohang_md(
                    session.meta.get("name", ""),
                    session.meta.get("url", ""),
                    icon_url,
                    session.meta.get("description", ""),
                    body=session.full_text(),
                    tags=session.meta.get("tags") or [],
                )
                path = "src/content/daohang/{}/{}.md".format(
                    daohang_cat, daohang_slug(session.meta.get("url", ""))
                )
                link = "/projects"
            elif session.kind == "book":
                # 书籍条目：封面用户上传（必须），标准 bangumi 格式 category: book，放 book/ 根目录
                if not image_urls:
                    return event.plain_result("书籍缺少封面图，请先发一张封面图再 /发布（或 /取消 放弃）。")
                book_title = str(session.meta.get("title") or "").strip()
                md = build_bangumi_md(
                    book_title,
                    image_urls[0],
                    score=session.meta.get("score"),
                    tags=session.meta.get("tags") or [],
                    comment=session.full_text(),
                    category="book",
                    now=now,
                )
                path = "src/content/bangumi/book/{}.md".format(clean_filename_part(book_title))
                link = "/books"
            elif session.kind == "media":
                # 影视/游戏条目：category 由向导决定（anime/game），落盘目录随之分流
                if not image_urls:
                    return event.plain_result("封面缺失，无法发布（请发一张封面图，或 /取消 放弃）。")
                media_title = str(session.meta.get("title") or "").strip()
                media_category = str(session.meta.get("category") or "anime")
                if media_category not in ("anime", "game"):
                    media_category = "anime"
                if media_category == "game":
                    # 游戏：category game、无 subcategory，放 bangumi/game/（对齐现有条目）
                    media_sub = ""
                    media_dir = "game"
                else:
                    media_sub = str(session.meta.get("subcategory") or "movie")
                    if media_sub not in ("movie", "tv", "anime", "documentary"):
                        media_sub = "movie"
                    media_dir = "anime"
                md = build_bangumi_md(
                    media_title,
                    image_urls[0],
                    score=session.meta.get("score"),
                    tags=session.meta.get("tags") or [],
                    comment=session.full_text(),
                    subcategory=media_sub,
                    category=media_category,
                    now=now,
                )
                path = "src/content/bangumi/{}/{}.md".format(media_dir, clean_filename_part(media_title))
                link = "/movies-games" if media_category == "game" else "/bangumi"
            elif session.kind == "bill":
                if not session.meta or session.meta.get("amount") is None:
                    return event.plain_result("账单信息不完整，请先发送账单内容（如：今天午餐微信花了32）。")
                md = build_bill_md(session.meta, now)
                title = str(session.meta.get("title") or "账单").strip() or "账单"
                slug = clean_filename_part(title)
                date_val = session.meta.get("date") or now
                if isinstance(date_val, datetime):
                    date_str = date_val.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_val).strip()[:10] or now.strftime("%Y-%m-%d")
                path = "src/content/bills/{}-{}.md".format(date_str, slug)
                link = "/bills/{}".format(slug)
            elif session.kind == "bill_batch":
                items = session.meta.get("items") or []
                if not items:
                    return event.plain_result("批量账单为空，无法发布。")
                raw_files: List[Tuple[str, str]] = []
                for item in items:
                    try:
                        md_item = build_bill_md(item, now)
                        title_item = str(item.get("title") or "账单").strip() or "账单"
                        slug_item = clean_filename_part(title_item)
                        date_val = item.get("date") or now
                        if isinstance(date_val, datetime):
                            date_str = date_val.strftime("%Y-%m-%d")
                        else:
                            date_str = str(date_val).strip()[:10] or now.strftime("%Y-%m-%d")
                        path_item = "src/content/bills/{}-{}.md".format(date_str, slug_item)
                        raw_files.append((path_item, md_item))
                    except Exception as e:
                        return event.plain_result(f"账单「{item.get('title', '?')}」生成失败：{e}，批量发布已中止。")
                commit_msg = f"blog: 通过 AstrBot 批量发布 {len(raw_files)} 笔账单"
                ok, err = await self._commit_batch_md(raw_files, commit_msg, now)
                self._sessions.pop(user_id, None)
                if not ok:
                    return event.plain_result(f"批量账单发布失败：{err}")
                self._last_published[user_id] = {
                    "time": now,
                    "paths": [f[0] for f in raw_files],
                    "items": items,
                    "kind": "bill_batch",
                }
                return event.plain_result(f"批量账单发布成功 ✅ 共{len(raw_files)}条，已写入 bills。（如需撤回可于10分钟内发 /撤回）")
            elif session.kind in ("schedule", "birthday", "anniversary"):
                if not session.meta or not session.meta.get("title"):
                    return event.plain_result("日程/生日/纪念日信息不完整，请先发送内容（如：明天下午3点在会议室A开周会 / 我的农历8.24 / 结婚纪念日 农历5月20）。")
                md = build_schedule_md(session.meta, now)
                title = str(session.meta.get("title") or "日程").strip() or "日程"
                slug = clean_filename_part(title)
                # 农历日程文件名用 lunar-M-D 前缀（对齐博客 lunar-8-24-我的生日.md 惯例）
                path = "src/content/schedules/{}-{}.md".format(schedule_filename(session.meta, now), slug)
                link = "/schedules/{}".format(slug)
            elif session.kind == "schedule_batch":
                items = session.meta.get("items") or []
                if not items:
                    return event.plain_result("批量日程为空，无法发布。")
                raw_files = []
                for item in items:
                    try:
                        md_item = build_schedule_md(item, now)
                        title_item = str(item.get("title") or "日程").strip() or "日程"
                        slug_item = clean_filename_part(title_item)
                        path_item = "src/content/schedules/{}-{}.md".format(schedule_filename(item, now), slug_item)
                        raw_files.append((path_item, md_item))
                    except Exception as e:
                        return event.plain_result(f"日程「{item.get('title', '?')}」生成失败：{e}，批量发布已中止。")
                commit_msg = f"blog: 通过 AstrBot 批量发布 {len(raw_files)} 条日程"
                ok, err = await self._commit_batch_md(raw_files, commit_msg, now)
                self._sessions.pop(user_id, None)
                self._last_published[user_id] = {
                    "time": now,
                    "paths": [f[0] for f in raw_files],
                    "kind": "schedule_batch",
                }
                if not ok:
                    return event.plain_result(f"批量日程发布失败：{err}")
                # 提交成功后统一调度提醒
                for item in items:
                    try:
                        date_val = item.get("date")
                        dt = date_val if isinstance(date_val, datetime) else None
                        if isinstance(date_val, str):
                            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                                try:
                                    dt = datetime.strptime(date_val.strip(), fmt)
                                    break
                                except ValueError:
                                    continue
                        if dt and not item.get("allDay", True):
                            all_day = item.get("allDay")
                            if all_day is None:
                                all_day = dt.hour == 0 and dt.minute == 0
                            if not all_day:
                                remind_before = item.get("remind_before", self._cfg("schedule_remind_before", 10))
                                try:
                                    remind_before = int(remind_before)
                                except Exception:
                                    remind_before = 10
                                remind_at = dt - timedelta(minutes=remind_before) if remind_before > 0 else dt
                                origin = getattr(event, "unified_msg_origin", "") or getattr(event, "session_id", "") or user_id
                                title_item = str(item.get("title") or "日程").strip() or "日程"
                                self._schedule_remind(user_id, title_item, remind_at, origin, remind_before)
                    except Exception:
                        pass
                return event.plain_result(f"批量发布成功 ✅ 共{len(raw_files)}条，已写入 schedules。")
            else:
                lat, lng = await self._geocode(
                    session.meta.get("province", "") + session.meta.get("city", "")
                )
                if lat is None:
                    return event.plain_result(
                        "高德地理编码失败，无法获取坐标，已中止发布。请检查地点名称。"
                    )
                md = build_place_md(
                    session.meta.get("province", ""),
                    session.meta.get("city", ""),
                    session.meta.get("experience", ""),
                    image_urls,
                    lat,
                    lng,
                    self._merge_tags(self._cfg("place_tags", ["旅游"]), session.meta.get("tags")),
                    now,
                )
                path = "src/content/life/places/{}.md".format(place_filename(now))
                link = "/life/places/{}".format(place_filename(now))
        except Exception as e:
            logger.error("BlogWriter 生成 markdown 失败: {}".format(e))
            return event.plain_result("生成内容失败：{}".format(e))

        # 3. GitHub 提交（带冲突后缀重试）
        ok, final_path, err = await self._commit_md(path, md, now)
        if not ok:
            return event.plain_result("GitHub 提交失败：{}".format(err))

        # 日程提醒：成功后若为 schedule 且含时间则调用 _schedule_remind
        if session.kind in ("schedule", "birthday", "anniversary"):
            try:
                date_val = session.meta.get("date")
                dt = None
                if isinstance(date_val, datetime):
                    dt = date_val
                elif isinstance(date_val, str):
                    ds = date_val.strip()
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                        try:
                            dt = datetime.strptime(ds, fmt)
                            break
                        except ValueError:
                            continue
                if dt is not None:
                    all_day = session.meta.get("allDay")
                    if all_day is None:
                        all_day = dt.hour == 0 and dt.minute == 0 and dt.second == 0
                    if not all_day:
                        remind_before = session.meta.get("remind_before")
                        if remind_before is None:
                            remind_before = self._cfg("schedule_remind_before", 10)
                        try:
                            remind_before = int(remind_before)
                        except Exception:
                            remind_before = 10
                        remind_at = dt - timedelta(minutes=remind_before) if remind_before > 0 else dt
                        title = str(session.meta.get("title") or "日程").strip() or "日程"
                        origin = getattr(event, "unified_msg_origin", "") or getattr(event, "session_id", "") or user_id
                        # AstrBot 不同版本可能用 session / unified_msg_origin
                        try:
                            if not origin:
                                origin = str(getattr(event, "unified_msg_origin", "") or getattr(event, "session", "") or user_id)
                        except Exception:
                            origin = user_id
                        self._schedule_remind(user_id, title, remind_at, origin, remind_before)
            except Exception as e:
                logger.warning("BlogWriter: 调度提醒异常: %s", e)

        self._sessions.pop(user_id, None)
        self._last_published[user_id] = {
            "time": now,
            "paths": [final_path],
            "kind": session.kind,
        }
        created_hint = "\n🎉 已新建笔记本「{}」（含 _index.json）".format(
            clean_filename_part(session.meta.get("note_dir") or "日常随笔", fallback="日常随笔")
        ) if session.kind == "note" and index_created else ""
        blog_base = (self._cfg("blog_base_url") or "https://imki.cn").rstrip("/")
        recall_hint = "\n（💡 如需撤回，可于 10 分钟内发送 /撤回）" if session.kind in ("bill", "moment", "note") else ""
        return event.plain_result(
            "发布成功 ✅\n\n文件：{}\n博客：{}{}{}".format(final_path, blog_base + link, created_hint, recall_hint)
        )

    # ---------- 图片/视频 ----------

    _IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic")
    _VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".webm")
    _MEDIA_EXTS = _IMAGE_EXTS + _VIDEO_EXTS

    @staticmethod
    def _media_size_limit(ref: str) -> int:
        """按扩展名选大小上限：视频 100MB，图片 20MB。"""
        return MAX_VIDEO_SIZE if ref.lower().split("?")[0].endswith((".mp4", ".mov", ".m4v", ".webm")) else MAX_IMAGE_SIZE

    def _extract_images(self, event: AstrMessageEvent, allow_video: bool = False) -> List[str]:
        """提取图片（allow_video 时含视频）。优先远程 URL，否则用本地文件路径
        （个人微信适配器会把图片/视频下载到 data/temp）。

        防御式匹配：不依赖组件具体类型，兼容 Image/Video 组件及带媒体特征字段的其他组件。
        """
        exts = self._MEDIA_EXTS if allow_video else self._IMAGE_EXTS
        urls = []
        try:
            for comp in event.get_messages():
                comp_type = str(getattr(comp, "type", "") or "").lower()
                is_image_type = isinstance(comp, Image) or comp_type in ("image", "img")
                is_video_type = allow_video and (
                    (Video is not None and isinstance(comp, Video)) or comp_type in ("video",)
                )
                is_media_type = is_image_type or is_video_type
                candidates = []
                for attr in ("url", "file", "path", "src"):
                    v = str(getattr(comp, attr, "") or "").strip()
                    if v:
                        candidates.append(v)
                if not candidates:
                    continue
                picked = candidates[0]
                if picked.startswith("http"):
                    if is_media_type or any(picked.lower().endswith(e) for e in exts):
                        urls.append(picked)
                        continue
                elif is_media_type or any(picked.lower().endswith(e) for e in exts):
                    urls.append(picked)
        except Exception as e:
            logger.warning("BlogWriter 提取图片失败: {}".format(e))
        logger.info("BlogWriter: 图片提取结果 %d 个引用: %s", len(urls), urls[:3])
        return urls
    async def _read_image_bytes(self, ref: str) -> Optional[bytes]:
        """从 URL 或本地路径读取图片字节。"""
        if ref.startswith(("http://", "https://")):
            return await self._download_http(ref)
        try:
            path = ref[len("file://") :] if ref.startswith("file://") else ref
            path = urllib.parse.unquote(path)
            p = Path(path)
            if not p.is_file():
                logger.warning("BlogWriter 本地图片不存在: {}".format(ref))
                return None
            if p.stat().st_size > self._media_size_limit(ref):
                logger.warning("BlogWriter 本地媒体超过大小上限，跳过: {}".format(ref))
                return None
            return p.read_bytes()
        except Exception as e:
            logger.warning("BlogWriter 读取本地图片失败: {} ({})".format(ref, e))
            return None

    async def _download_http(self, url: str, referer: str = "") -> Optional[bytes]:
        headers = {"Referer": referer} if referer else None
        for attempt in range(RETRY_COUNT + 1):
            try:
                resp = await self._get_client().get(url, headers=headers)
                if resp.status_code >= 400:
                    logger.warning("BlogWriter 下载图片 HTTP {}: {}".format(resp.status_code, url))
                    return None
                if len(resp.content) > self._media_size_limit(url):
                    logger.warning("BlogWriter 媒体超过大小上限，跳过: {}".format(url))
                    return None
                return resp.content
            except Exception as e:
                logger.warning("BlogWriter 下载图片失败(第{}次): {}".format(attempt + 1, e))
                if attempt < RETRY_COUNT:
                    await asyncio.sleep(RETRY_DELAYS[attempt])
        return None

    async def _upload_images(self, stored: List[Tuple[str, bytes]], folder: str = "") -> object:
        """stored: [(来源引用, 字节)]。并发上传，返回 List[str]（图床 URL）或 str（错误信息）。"""
        results: List[Optional[str]] = [None] * len(stored)
        failures: List[str] = []

        async def upload_one(index: int, ref: str, data: bytes) -> None:
            filename = ref.rsplit("/", 1)[-1].split("?")[0].split("#")[0] or "image.png"
            if "." not in filename:
                filename = "image.png"
            ok, value = await self._imgbed_upload(filename, data, folder)
            if ok:
                results[index] = value
            else:
                failures.append("{}（{}）".format(value, filename))

        tasks = [upload_one(i, ref, data) for i, (ref, data) in enumerate(stored)]
        await asyncio.gather(*tasks)
        if failures:
            return "；".join(failures[:3])
        return [r for r in results if r is not None]

    async def _imgbed_upload(self, filename: str, data: bytes, folder: str = "") -> Tuple[bool, str]:
        upload_url = (self._cfg("imgbed_upload_url") or "https://img.imki.cn/upload").strip()
        token = (self._cfg("imgbed_token") or "").strip()
        base_host = upload_base_host(upload_url)
        req_data = build_imgbed_upload(upload_url, filename, data)
        for attempt in range(RETRY_COUNT + 1):
            try:
                headers = dict(req_data["headers"])
                if token:
                    headers["Authorization"] = "Bearer " + token
                resp = await self._get_client().post(
                    build_upload_url(upload_url, folder),
                    content=req_data["body"],
                    headers=headers,
                )
                ok, value = parse_imgbed_response(resp.status_code, resp.text, base_host)
                if not ok and resp.status_code == 401:
                    return False, "图床认证失败（HTTP 401）：请检查图床 Token；也可在地址后加 ?authCode=上传认证码"
                return ok, value
            except Exception as e:
                logger.warning("BlogWriter 图床上传失败(第{}次): {}".format(attempt + 1, e))
                if attempt < RETRY_COUNT:
                    await asyncio.sleep(RETRY_DELAYS[attempt])
        return False, "图床上传网络错误"

    # ---------- 高德 ----------

    async def _geocode(self, address: str) -> Tuple[Optional[float], Optional[float]]:
        key = self._amap_key()
        if not key:
            logger.error("BlogWriter 未配置高德 Key（配置项 amap_key 或环境变量 AMAP_KEY）")
            return None, None
        url = build_amap_url(address, key)
        for attempt in range(RETRY_COUNT + 1):
            try:
                resp = await self._get_client().get(url)
                ok, coords = parse_amap_response(resp.status_code, resp.text)
                if ok:
                    return coords
                logger.warning("BlogWriter 高德解析失败: {}".format(resp.text[:120]))
                return None, None
            except Exception as e:
                logger.warning("BlogWriter 高德请求失败(第{}次): {}".format(attempt + 1, e))
                if attempt < RETRY_COUNT:
                    await asyncio.sleep(RETRY_DELAYS[attempt])
        return None, None

    # ---------- GitHub ----------

    async def _commit_md(self, path: str, md: str, now: datetime) -> Tuple[bool, str, str]:
        repo = self._cfg("github_repo") or "mengkuikun/Blog-2.0"
        branch = self._cfg("github_branch") or "main"
        token = (self._cfg("github_token") or "").strip()
        base_name = path.rsplit(".", 1)[0]
        for index in range(11):
            candidate = with_suffix(base_name, ".md", index)
            exists = await self._github_exists(repo, candidate, branch, token)
            if exists is None:
                return False, "", "GitHub 查询失败（网络或 Token 问题）"
            if exists:
                continue
            ok, err = await self._github_put(repo, candidate, md, token, branch)
            if not ok:
                if err == "CONFLICT":
                    continue  # 并发冲突，换后缀
                return False, "", err
            return True, candidate, ""
        return False, "", "文件名冲突过多，无法找到可用文件名"

    async def _commit_batch_md(
        self, files: List[Tuple[str, str]], message: str, now: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        """批量提交多个 Markdown 文件，整合为单次 Git Commit，触发单次 EdgeOne 构建部署。
        使用 GitHub Git Data API (Tree + Commit + Ref)。
        files 列表为 [(base_path, md_content), ...]
        """
        if not files:
            return True, ""
        repo = self._cfg("github_repo") or "mengkuikun/Blog-2.0"
        branch = self._cfg("github_branch") or "main"
        token = (self._cfg("github_token") or "").strip()

        # 1. 批量文件名冲突解决（支持批次内同名防重与远端防重）
        allocated_paths = set()
        resolved_files: List[Tuple[str, str]] = []
        for base_path, md_content in files:
            base_name = base_path.rsplit(".", 1)[0]
            assigned_path = None
            for index in range(11):
                candidate = with_suffix(base_name, ".md", index)
                if candidate in allocated_paths:
                    continue
                exists = await self._github_exists(repo, candidate, branch, token)
                if exists is None:
                    return False, "GitHub 查询失败（网络或 Token 问题）"
                if exists:
                    continue
                assigned_path = candidate
                allocated_paths.add(candidate)
                break
            if not assigned_path:
                return False, f"文件名冲突过多：{base_path}"
            resolved_files.append((assigned_path, md_content))

        # 2. 调用 GitHub Git Data API 完成单次 Commit
        headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        }
        client = self._get_client()

        for attempt in range(RETRY_COUNT + 1):
            try:
                # 获取分支最新 commit sha
                ref_url = github_ref_url(repo, branch)
                resp_ref = await client.get(ref_url, headers=headers)
                if resp_ref.status_code != 200:
                    logger.warning("BlogWriter 批量提交获取 ref 失败 HTTP %s: %s", resp_ref.status_code, resp_ref.text)
                    if attempt < RETRY_COUNT:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                    return False, f"获取分支引用失败 (HTTP {resp_ref.status_code})"
                ref_data = resp_ref.json()
                latest_commit_sha = ref_data.get("object", {}).get("sha")
                if not latest_commit_sha:
                    return False, "分支引用未包含 commit sha"

                # 获取该 commit 对应的 base_tree sha
                commit_url = github_commit_url(repo, latest_commit_sha)
                resp_commit = await client.get(commit_url, headers=headers)
                if resp_commit.status_code != 200:
                    logger.warning("BlogWriter 批量提交获取 commit 失败 HTTP %s: %s", resp_commit.status_code, resp_commit.text)
                    if attempt < RETRY_COUNT:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                    return False, f"获取父提交失败 (HTTP {resp_commit.status_code})"
                base_tree_sha = resp_commit.json().get("tree", {}).get("sha")
                if not base_tree_sha:
                    return False, "父提交未包含 tree sha"

                # 创建新 tree（包含批量所有文件变更）
                trees_url = github_trees_url(repo)
                tree_body = build_github_tree_body(resolved_files, base_tree=base_tree_sha)
                resp_tree = await client.post(trees_url, content=tree_body.encode("utf-8"), headers=headers)
                if resp_tree.status_code not in (200, 201):
                    logger.warning("BlogWriter 批量提交创建 tree 失败 HTTP %s: %s", resp_tree.status_code, resp_tree.text)
                    if attempt < RETRY_COUNT:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                    return False, f"创建 Git Tree 失败 (HTTP {resp_tree.status_code})"
                new_tree_sha = resp_tree.json().get("sha")
                if not new_tree_sha:
                    return False, "新 Tree 未返回 sha"

                # 创建新 commit
                commits_url = github_commits_url(repo)
                commit_body = build_github_commit_body(message, new_tree_sha, latest_commit_sha)
                resp_new_commit = await client.post(commits_url, content=commit_body.encode("utf-8"), headers=headers)
                if resp_new_commit.status_code not in (200, 201):
                    logger.warning("BlogWriter 批量提交创建 commit 失败 HTTP %s: %s", resp_new_commit.status_code, resp_new_commit.text)
                    if attempt < RETRY_COUNT:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                    return False, f"创建 Git Commit 失败 (HTTP {resp_new_commit.status_code})"
                new_commit_sha = resp_new_commit.json().get("sha")
                if not new_commit_sha:
                    return False, "新 Commit 未返回 sha"

                # 更新分支 ref (PATCH)
                refs_url = github_refs_url(repo, branch)
                ref_update_body = build_github_ref_update_body(new_commit_sha, force=False)
                resp_update = await client.patch(refs_url, content=ref_update_body.encode("utf-8"), headers=headers)
                if resp_update.status_code in (409, 422):
                    logger.warning("BlogWriter 批量提交更新 ref 并发冲突，第 %s 次重试", attempt + 1)
                    if attempt < RETRY_COUNT:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                    return False, "更新分支引用并发冲突"
                if resp_update.status_code not in (200, 201):
                    logger.warning("BlogWriter 批量提交更新 ref 失败 HTTP %s: %s", resp_update.status_code, resp_update.text)
                    if attempt < RETRY_COUNT:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                    return False, f"更新分支引用失败 (HTTP {resp_update.status_code})"

                return True, ""
            except Exception as e:
                logger.warning("BlogWriter 批量提交异常 (第%s次): %s", attempt + 1, e)
                if attempt < RETRY_COUNT:
                    await asyncio.sleep(RETRY_DELAYS[attempt])

        return False, "GitHub 批量提交网络错误"

    async def _commit_batch_delete(self, paths: List[str], message: str) -> Tuple[bool, str]:
        """批量删除 GitHub 上的文件，整合为单次 Git Commit，触发单次 EdgeOne 部署。"""
        if not paths:
            return True, ""
        repo = self._cfg("github_repo") or "mengkuikun/Blog-2.0"
        branch = self._cfg("github_branch") or "main"
        token = (self._cfg("github_token") or "").strip()
        if not token:
            return False, "未配置 github_token"

        headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        }
        client = self._get_client()

        for attempt in range(RETRY_COUNT + 1):
            try:
                # 获取分支最新 commit sha
                ref_url = github_ref_url(repo, branch)
                resp_ref = await client.get(ref_url, headers=headers)
                if resp_ref.status_code != 200:
                    logger.warning("BlogWriter 批量删除获取 ref 失败 HTTP %s: %s", resp_ref.status_code, resp_ref.text)
                    if attempt < RETRY_COUNT:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                    return False, f"获取分支引用失败 (HTTP {resp_ref.status_code})"
                ref_data = resp_ref.json()
                latest_commit_sha = ref_data.get("object", {}).get("sha")
                if not latest_commit_sha:
                    return False, "分支引用未包含 commit sha"

                # 获取该 commit 对应的 base_tree sha
                commit_url = github_commit_url(repo, latest_commit_sha)
                resp_commit = await client.get(commit_url, headers=headers)
                if resp_commit.status_code != 200:
                    logger.warning("BlogWriter 批量删除获取 commit 失败 HTTP %s: %s", resp_commit.status_code, resp_commit.text)
                    if attempt < RETRY_COUNT:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                    return False, f"获取父提交失败 (HTTP {resp_commit.status_code})"
                base_tree_sha = resp_commit.json().get("tree", {}).get("sha")
                if not base_tree_sha:
                    return False, "父提交未包含 tree sha"

                # 创建新 tree (sha: None 告知 Git 删除指定路径)
                trees_url = github_trees_url(repo)
                tree_body = build_github_delete_tree_body(paths, base_tree=base_tree_sha)
                resp_tree = await client.post(trees_url, content=tree_body.encode("utf-8"), headers=headers)
                if resp_tree.status_code not in (200, 201):
                    logger.warning("BlogWriter 批量删除创建 tree 失败 HTTP %s: %s", resp_tree.status_code, resp_tree.text)
                    if attempt < RETRY_COUNT:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                    return False, f"创建 Git Tree (删除) 失败 (HTTP {resp_tree.status_code})"
                new_tree_sha = resp_tree.json().get("sha")
                if not new_tree_sha:
                    return False, "新 Tree 未返回 sha"

                # 创建新 commit
                commits_url = github_commits_url(repo)
                commit_body = build_github_commit_body(message, new_tree_sha, latest_commit_sha)
                resp_new_commit = await client.post(commits_url, content=commit_body.encode("utf-8"), headers=headers)
                if resp_new_commit.status_code not in (200, 201):
                    logger.warning("BlogWriter 批量删除创建 commit 失败 HTTP %s: %s", resp_new_commit.status_code, resp_new_commit.text)
                    if attempt < RETRY_COUNT:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                    return False, f"创建 Git Commit 失败 (HTTP {resp_new_commit.status_code})"
                new_commit_sha = resp_new_commit.json().get("sha")
                if not new_commit_sha:
                    return False, "新 Commit 未返回 sha"

                # 更新分支 ref (PATCH)
                refs_url = github_refs_url(repo, branch)
                ref_update_body = build_github_ref_update_body(new_commit_sha, force=False)
                resp_update = await client.patch(refs_url, content=ref_update_body.encode("utf-8"), headers=headers)
                if resp_update.status_code in (409, 422):
                    logger.warning("BlogWriter 批量删除更新 ref 并发冲突，第 %s 次重试", attempt + 1)
                    if attempt < RETRY_COUNT:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                    return False, "更新分支引用并发冲突"
                if resp_update.status_code not in (200, 201):
                    logger.warning("BlogWriter 批量删除更新 ref 失败 HTTP %s: %s", resp_update.status_code, resp_update.text)
                    if attempt < RETRY_COUNT:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                    return False, f"更新分支引用失败 (HTTP {resp_update.status_code})"

                return True, ""
            except Exception as e:
                logger.warning("BlogWriter 批量删除异常 (第%s次): %s", attempt + 1, e)
                if attempt < RETRY_COUNT:
                    await asyncio.sleep(RETRY_DELAYS[attempt])
                    continue
                return False, f"批量删除异常: {e}"
        return False, "批量删除超出最大重试次数"


    async def _github_exists(self, repo: str, path: str, branch: str, token: str) -> Optional[bool]:
        url = github_base(repo, path, branch)
        headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        for attempt in range(RETRY_COUNT + 1):
            try:
                resp = await self._get_client().get(url, headers=headers)
                if resp.status_code == 200:
                    return True
                if resp.status_code == 404:
                    return False
                logger.warning("BlogWriter GitHub 查询 HTTP {}: {}".format(resp.status_code, path))
            except Exception as e:
                logger.warning("BlogWriter GitHub 查询失败(第{}次): {}".format(attempt + 1, e))
            if attempt < RETRY_COUNT:
                await asyncio.sleep(RETRY_DELAYS[attempt])
        return None

    async def _github_list_dir_index(self, dir_path: str, repo: str, branch: str, token: str) -> int:
        """列出目录文件名，计算下一个数字前缀编号（友链文件名 NN-name.md）。失败返回 1。"""
        import json as _json

        url = "https://api.github.com/repos/{}/contents/{}?ref={}".format(
            repo, urllib.parse.quote(dir_path), urllib.parse.quote(branch)
        )
        headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            resp = await self._get_client().get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning("BlogWriter: 列目录失败 HTTP %s: %s", resp.status_code, dir_path)
                return 1
            data = _json.loads(resp.text)
            names = [str(item.get("name", "")) for item in data if isinstance(item, dict)]
            return next_friend_index(names)
        except Exception as e:
            logger.warning("BlogWriter: 列目录异常: %s", e)
            return 1

    async def _github_file_content(self, repo: str, path: str, branch: str, token: str) -> Optional[str]:
        """读取仓库文件文本内容（Accept: raw）。失败返回 None。"""
        headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github.raw",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            resp = await self._get_client().get(github_base(repo, path, branch), headers=headers)
            if resp.status_code == 200:
                return resp.text
            logger.warning("BlogWriter 读取文件失败 HTTP %s: %s", resp.status_code, path)
        except Exception as e:
            logger.warning("BlogWriter 读取文件异常: %s (%s)", e, path)
        return None

    async def _album_index(self, repo: str, branch: str, token: str) -> Optional[Dict[str, object]]:
        """列出 src/content/album 目录并解析每个文件的 title/imgbedFolder。

        返回 {"titles": {title: folder}, "files": {文件名: folder},
              "entries": [(title, 文件名, folder), ...]}（entries 供向导一次性展示，避免二次拉取）；
        目录不存在（404）→ 空索引；网络失败 → None。
        """
        import json as _json

        url = "https://api.github.com/repos/{}/contents/src/content/album?ref={}".format(
            repo, urllib.parse.quote(branch)
        )
        headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            resp = await self._get_client().get(url, headers=headers)
            if resp.status_code == 404:
                return {"titles": {}, "files": {}, "entries": []}
            if resp.status_code != 200:
                logger.warning("BlogWriter: 相册目录列出失败 HTTP %s", resp.status_code)
                return None
            items = _json.loads(resp.text)
            titles: Dict[str, str] = {}
            files: Dict[str, str] = {}
            entries: List[Tuple[str, str, str]] = []
            for item in items:
                if not isinstance(item, dict) or item.get("type") != "file":
                    continue
                name = str(item.get("name") or "")
                if not name.lower().endswith((".md", ".mdx")):
                    continue
                content = await self._github_file_content(
                    repo, "src/content/album/" + name, branch, token
                )
                if content is None:
                    continue
                title, folder = parse_album_frontmatter(content)
                title = (title or name.rsplit(".", 1)[0]).strip()
                if title:
                    titles[title] = folder.strip()
                files[name] = folder.strip()
                entries.append((title, name, folder.strip()))
            return {"titles": titles, "files": files, "entries": entries}
        except Exception as e:
            logger.warning("BlogWriter: 相册目录解析异常: %s", e)
            return None

    async def _github_put(self, repo: str, path: str, md: str, token: str, branch: str) -> Tuple[bool, str]:
        body = build_github_put_body("blog: 通过 AstrBot 发布 {}".format(path), md.encode("utf-8"), branch)
        url = github_put_url(repo, path)
        headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        }
        for attempt in range(RETRY_COUNT + 1):
            try:
                resp = await self._get_client().put(url, content=body.encode("utf-8"), headers=headers)
                if resp.status_code in (409, 422):
                    return False, "CONFLICT"
                return parse_github_put_response(resp.status_code, resp.text)
            except Exception as e:
                logger.warning("BlogWriter GitHub 提交失败(第{}次): {}".format(attempt + 1, e))
                if attempt < RETRY_COUNT:
                    await asyncio.sleep(RETRY_DELAYS[attempt])
        return False, "GitHub 提交网络错误"

    # ---------- 微信媒体兜底下载（绕开适配器 aiohttp 的 CDN TLS 握手失败） ----------

    _WX_IMAGE_ITEM_TYPE = "2"
    _WX_VIDEO_ITEM_TYPE = "5"

    def _extract_wx_raw_media(self, event: AstrMessageEvent, allow_video: bool = False) -> List[Tuple[str, str, str, str]]:
        """从 event.message_obj.raw_message 提取 (encrypt_query_param, aeskey_hex, aes_key_b64, kind)。

        结构对齐 astrbot/core/platform/sources/weixin_oc/weixin_oc_adapter.py 的
        _resolve_inbound_media_component：item.type==2 为图片（image_item），
        type==5 为视频（video_item，只有 media.aes_key、无 aeskey 字段）。
        kind ∈ {"image", "video"}。
        """
        raw = getattr(getattr(event, "message_obj", None), "raw_message", None)
        if not isinstance(raw, dict):
            return []
        out = []
        for item in raw.get("item_list") or []:
            try:
                if not isinstance(item, dict):
                    continue
                itype = str(item.get("type"))
                if itype == self._WX_IMAGE_ITEM_TYPE:
                    key, kind = "image_item", "image"
                elif itype == self._WX_VIDEO_ITEM_TYPE and allow_video:
                    key, kind = "video_item", "video"
                else:
                    continue
                media_item = item.get(key) or {}
                media = media_item.get("media") or {}
                enc = str(media.get("encrypt_query_param") or "").strip()
                aes_hex = str(media_item.get("aeskey") or "").strip()
                aes_b64 = str(media.get("aes_key") or "").strip()
                if enc and (aes_hex or aes_b64):
                    out.append((enc, aes_hex, aes_b64, kind))
            except Exception as e:
                logger.warning("BlogWriter: 解析 raw_message 媒体项失败: %s", e)
        return out

    async def _download_wx_media(self, enc: str, aes_hex: str, aes_b64: str) -> Optional[bytes]:
        """curl 下载微信 CDN 加密媒体（curl 的 TLS 指纹可被微信 CDN 接受），再 AES-ECB 解密。

        已知现象：微信 CDN keep-alive 连接不主动关闭，curl 收满 Content-Length 后仍等待连接
        收尾而触发 --max-time 超时（returncode 28），但数据已完整。此时只要解密后的图片
        魔数校验通过，即视为成功。
        """
        import asyncio.subprocess

        import urllib.parse

        cdn = (self._cfg("wx_cdn_base_url") or "https://novac2c.cdn.weixin.qq.com/c2c").strip().rstrip("/")
        url = "{}/download?encrypted_query_param={}".format(cdn, urllib.parse.quote(enc))
        for attempt in range(RETRY_COUNT + 1):
            try:
                proc = await asyncio.subprocess.create_subprocess_exec(
                    "curl",
                    "-sS",
                    "--connect-timeout",
                    "8",
                    "--max-time",
                    "10",
                    "-H",
                    "Connection: close",
                    url,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode == 0 and stdout:
                    plain = self._decrypt_wx_media(stdout, aes_hex, aes_b64)
                    if plain is not None:
                        return plain
                elif stdout:
                    # 超时（28）但字节可能已完整：解密 + 魔数校验兜底
                    plain = self._decrypt_wx_media(stdout, aes_hex, aes_b64)
                    if plain is not None and self._has_image_magic(plain):
                        logger.info(
                            "BlogWriter: curl 超时但数据完整（%d 字节），魔数校验通过", len(plain)
                        )
                        return plain
                    logger.warning(
                        "BlogWriter: curl 下载微信媒体失败(第%d次): %s",
                        attempt + 1,
                        (stderr or b"").decode("utf-8", "replace")[:120],
                    )
                else:
                    logger.warning(
                        "BlogWriter: curl 下载微信媒体失败(第%d次): %s",
                        attempt + 1,
                        (stderr or b"").decode("utf-8", "replace")[:120],
                    )
                if attempt < RETRY_COUNT:
                    await asyncio.sleep(RETRY_DELAYS[attempt])
            except Exception as e:
                logger.warning("BlogWriter: curl 下载异常(第%d次): %s", attempt + 1, e)
                if attempt < RETRY_COUNT:
                    await asyncio.sleep(RETRY_DELAYS[attempt])
        return None

    @staticmethod
    def _has_image_magic(data: bytes) -> bool:
        """图片魔数校验：JPEG/PNG/GIF/WebP/BMP；顺带兼容 mp4（偏移 4 处 ftyp）。"""
        if not data:
            return False
        return any(
            data.startswith(m)
            for m in (b"\xff\xd8", b"\x89PNG", b"GIF8", b"RIFF", b"BM")
        ) or data[4:8] == b"ftyp"

    @staticmethod
    def _decrypt_wx_media(data: bytes, aes_hex: str, aes_b64: str) -> Optional[bytes]:
        """AES-ECB + PKCS7 解密，逻辑对齐 weixin_oc_client.parse_media_aes_key / pkcs7_unpad。"""
        try:
            from Crypto.Cipher import AES
        except ImportError:
            logger.error("BlogWriter: 缺少 pycryptodome（Crypto），无法解密微信媒体")
            return None
        try:
            if aes_hex:
                key = bytes.fromhex(aes_hex)
            else:
                padded = aes_b64.strip() + "=" * (-len(aes_b64.strip()) % 4)
                key = base64.b64decode(padded)
                if len(key) == 32:
                    key = bytes.fromhex(key.decode("ascii", errors="ignore"))
            if len(key) not in (16, 24, 32):
                logger.warning("BlogWriter: 微信媒体 AES key 长度异常: %d", len(key))
                return None
            plain = AES.new(key, AES.MODE_ECB).decrypt(data)
            pad_len = plain[-1] if plain else 0
            if 0 < pad_len <= 16 and plain[-pad_len:] == bytes([pad_len]) * pad_len:
                plain = plain[:-pad_len]
            return plain
        except Exception as e:
            logger.warning("BlogWriter: AES 解密失败: %s", e)
            return None

    # ---------- 向导分发 ----------

    async def _handle_wizard(self, event: AstrMessageEvent, user_id: str, raw: str):
        sess = self._sessions.get(user_id)
        if not sess or not getattr(sess, "wizard", None):
            return None
        step = sess.wizard.get("step", "")
        text = (raw or "").strip()
        # 空消息（微信心跳/系统事件）直接放行，不回复，避免刷屏
        if not text:
            return None

        # 通用取消
        if is_wizard_cancel(text):
            self._sessions.pop(user_id, None)
            return event.plain_result("已取消当前会话。")

        # ---- 笔记向导 ----
        if step == "note_pick_notebook":
            notebooks = sess.wizard.get("notebooks", [])
            n = len(notebooks)
            total = n + 1  # 含新建
            choice = parse_choice(text, total)
            if choice is not None:
                if choice == total:  # 新建
                    sess.wizard = {"step": "note_input_new_notebook", "notebooks": notebooks, "default_dir": sess.wizard.get("default_dir")}
                    return event.plain_result("请输入新笔记本名称（将作为文件夹名，非法字符会自动替换为 -）：")
                else:
                    picked = notebooks[choice - 1]
                    sess.meta["note_dir"] = picked
                    sess.wizard = {"step": "note_input_title", "note_dir": picked}
                    sess.touch()
                    return event.plain_result(f"已选笔记本「{picked}」。\n请输入笔记标题：")
            # 非数字：当作新建名直接处理（存清洗后的名字，防路径注入）
            if text and len(text) <= 30:
                chk = clean_filename_part(text, fallback="")
                if not chk:
                    return event.plain_result("名称无效，请重发（1-30字，避免特殊符号）。或回复数字选择。")
                if chk in notebooks:
                    sess.meta["note_dir"] = chk
                    sess.wizard = {"step": "note_input_title", "note_dir": chk}
                    sess.touch()
                    return event.plain_result(f"已选笔记本「{chk}」。\n请输入笔记标题：")
                sess.meta["note_dir"] = chk
                sess.wizard = {"step": "note_input_title", "note_dir": chk}
                sess.touch()
                return event.plain_result(f"已创建笔记本「{chk}」。\n请输入笔记标题：")
            return event.plain_result("请回复数字选择，或直接发新笔记本名称。\n" + format_choices("请选择笔记本：", notebooks, extra=["新建笔记本"], with_skip_cancel=False))

        if step == "note_input_new_notebook":
            chk = clean_filename_part(text, fallback="")
            if not chk:
                return event.plain_result("名称无效，请重发。")
            sess.meta["note_dir"] = chk
            sess.wizard = {"step": "note_input_title", "note_dir": chk}
            sess.touch()
            return event.plain_result(f"已选笔记本「{chk}」。\n请输入笔记标题：")

        if step == "note_input_title":
            if not text:
                return event.plain_result("标题不能为空，请重发笔记标题：")
            sess.meta["title"] = text.strip()
            sess.wizard = None
            sess.touch()
            return event.plain_result(
                f"笔记已创建：分类「{sess.meta['note_dir']}」标题「{text.strip()}」。\n\n接下来直接发正文（可多条，自动拼接），也可以发图片，发完说 /发布。"
            )

        # ---- 相册向导 ----
        if step == "album_pick":
            titles = sess.wizard.get("titles", [])
            display = sess.wizard.get("display", [])
            total = len(display) + 1
            choice = parse_choice(text, total)
            if choice is not None:
                if choice == total:  # 新建
                    sess.wizard = {"step": "album_input_new", "titles": titles, "display": display}
                    return event.plain_result("请输入新相册名称：")
                picked = titles[choice - 1]
                sess.meta["name"] = picked
                sess.wizard = None
                sess.touch()
                return event.plain_result(f"已选相册「{picked}」\n请直接发图片（可多发），发完说 /发布。")
            if text and len(text) <= 40:
                chk = clean_filename_part(text, fallback="")
                if chk:
                    sess.meta["name"] = chk
                    sess.wizard = None
                    sess.touch()
                    return event.plain_result(f"相册「{chk}」已创建。\n请直接发图片（可多发），发完说 /发布。")
            return event.plain_result("请回复数字选择，或直接发新相册名称。\n" + format_choices("请选择相册：", display, extra=["新建相册"], with_skip_cancel=False))

        if step == "album_input_new":
            chk = clean_filename_part(text, fallback="")
            if not chk:
                return event.plain_result("相册名无效，请重发。")
            sess.meta["name"] = chk
            sess.wizard = None
            sess.touch()
            return event.plain_result(f"相册「{chk}」已创建。\n请直接发图片（可多发），发完说 /发布。")

        # ---- 影视/书籍向导 ----
        if step == "media_need_cover":
            # 兼容旧路径：允许发 名称:/类型: 键值对修正标题/类型
            fields = parse_media_fields(text)
            if fields:
                if fields.get("title"):
                    sess.meta["title"] = fields["title"]
                if fields.get("subcategory"):
                    sess.meta["subcategory"] = fields["subcategory"]
                sess.touch()
                return event.plain_result("已修改：{}。请发封面图后继续。".format("，".join(f"{k}={v}" for k,v in fields.items())))
            return event.plain_result("请先发一张封面图（必须），发图后我会让你选类型。\n回复“取消”退出。")

        if step == "media_pick_category":
            choice = parse_choice(text, len(MEDIA_WIZARD_CATEGORIES))
            if choice is not None:
                label, val = MEDIA_WIZARD_CATEGORIES[choice - 1]
                if val == "game":
                    sess.meta["category"] = "game"
                    sess.meta.pop("subcategory", None)
                elif val in ("movie", "tv"):
                    sess.meta["category"] = "anime"
                    sess.meta["subcategory"] = val
                else:  # anime / documentary
                    sess.meta["category"] = "anime"
                    sess.meta["subcategory"] = val
                sess.wizard = {"step": "media_score"}
                sess.touch()
                return event.plain_result(f"已选类型「{label}」。\n请发评分 0-10（整数），或回复“跳过”：")
            if is_wizard_skip(text):
                sess.meta["subcategory"] = sess.meta.get("subcategory") or "movie"
                sess.wizard = {"step": "media_score"}
                sess.touch()
                return event.plain_result("已跳过类型（默认 电影）。\n请发评分 0-10，或回复“跳过”：")
            return event.plain_result("请回复数字选择类型：\n" + self._media_type_prompt())

        if step == "media_score":
            if is_wizard_skip(text):
                sess.meta["score"] = None
                sess.wizard = {"step": "media_tags"}
                sess.touch()
                return event.plain_result("已跳过评分。\n请发标签（#科幻 #冒险 形式，多标签空格分隔），或回复“跳过”：")
            score = parse_media_score(text)
            if score is not None:
                sess.meta["score"] = score
                sess.wizard = {"step": "media_tags"}
                sess.touch()
                return event.plain_result(f"已记录评分：{score}。\n请发标签（#科幻 形式），或回复“跳过”：")
            # 兼容纯数字
            if text.strip().isdigit():
                try:
                    v = max(0, min(10, int(text.strip())))
                    sess.meta["score"] = v
                    sess.wizard = {"step": "media_tags"}
                    sess.touch()
                    return event.plain_result(f"已记录评分：{v}。\n请发标签（#科幻 形式），或回复“跳过”：")
                except Exception:
                    pass
            return event.plain_result("评分格式不对，请发 0-10 的数字（如：8、评分 8），或回复“跳过”。")

        if step == "media_tags":
            if is_wizard_skip(text):
                sess.wizard = None
                sess.touch()
                return event.plain_result("已跳过标签。发 /发布 提交，或继续发影评文字。")
            clean, tags = extract_tags(text)
            if tags:
                existing = sess.meta.setdefault("tags", [])
                for t in tags:
                    if t not in existing:
                        existing.append(t)
            if clean:
                sess.add_text(clean)
            sess.wizard = None
            sess.touch()
            tag_hint = f"标签：{' '.join('#'+t for t in sess.meta.get('tags',[]))}" if sess.meta.get("tags") else "无标签"
            return event.plain_result(f"已记录，{tag_hint}。发 /发布 提交，或继续发影评。")

        # ---- 账单向导 ----
        if step == "bill_confirm_type":
            # 兼容修改：分类:xxx / 账户:xxx / 日期:xxx / 时间:xxx / 金额:xxx / 标题:xxx
            m_cat_early = re.match(r"^(?:分类|类别|category)\s*[:：]?\s*(\S{1,10})\s*$", text)
            m_acc_early = re.match(r"^(?:账户|账号|account)\s*[:：]?\s*(\S{1,10})\s*$", text)
            m_date_early = re.match(r"^(?:日期|date)\s*[:：]?\s*(.+)$", text)
            m_time_early = re.match(r"^(?:时间|时刻|time)\s*[:：]?\s*(.+)$", text)
            m_amt_early = re.match(r"^(?:金额|多少钱|amount)\s*[:：]?\s*(-?\d+(?:\.\d+)?)\s*(?:块钱|元钱|块|元)?$", text)
            m_title_early = re.match(r"^(?:标题|备注|名称|title)\s*[:：]?\s*(.+)$", text)
            if m_cat_early or m_acc_early or m_date_early or m_time_early or m_amt_early or m_title_early:
                if m_cat_early:
                    sess.meta["category"] = m_cat_early.group(1)
                elif m_acc_early:
                    sess.meta["account"] = m_acc_early.group(1)
                elif m_date_early:
                    sess.meta["date"] = _parse_bill_date(m_date_early.group(1).strip(), now_shanghai())
                elif m_time_early:
                    tm = _parse_bill_time(m_time_early.group(1).strip(), now_shanghai())
                    if tm:
                        sess.meta["time"] = tm
                elif m_amt_early:
                    val = float(m_amt_early.group(1))
                    if sess.meta.get("type") == "expense":
                        sess.meta["amount"] = -abs(val)
                    else:
                        sess.meta["amount"] = abs(val)
                elif m_title_early:
                    t = m_title_early.group(1).strip()
                    sess.meta["title"] = t
                    sess.meta["description"] = t
                sess.touch()
                d_val = sess.meta.get("date")
                ds_val = d_val.strftime("%Y-%m-%d") if isinstance(d_val, datetime) else str(d_val)[:10]
                if m_cat_early:
                    prefix = f"已修改分类：{sess.meta['category']}。"
                elif m_acc_early:
                    prefix = f"已修改账户：{sess.meta['account']}。"
                elif m_date_early:
                    prefix = f"已修改日期：{ds_val}。"
                elif m_time_early:
                    prefix = f"已修改时间：{sess.meta.get('time', '')}。"
                elif m_amt_early:
                    prefix = f"已修改金额：{sess.meta.get('amount')}。"
                elif m_title_early:
                    prefix = f"已修改标题：{sess.meta.get('title')}。"
                else:
                    prefix = "已更新账单信息。"
                return event.plain_result(
                    "{}当前账单：{} 金额{}，分类{}，账户{}。发 /发布 提交。".format(
                        prefix, sess.meta.get("title"), sess.meta.get("amount"), sess.meta.get("category"), sess.meta.get("account")
                    )
                )
            choice = parse_choice(text, 4)
            if choice is not None:
                if choice == 3:  # 直接发布
                    sess.wizard = None
                    sess.touch()
                    return event.plain_result(self._bill_confirm_text(sess))
                if choice == 4:  # 重说
                    sess.wizard = {"step": "bill_reinput"}
                    sess.touch()
                    return event.plain_result("请重新发送账单内容（如：午餐30 / 发工资5000），发“取消”退出。")
                mapping = {1: "expense", 2: "income"}
                picked = mapping.get(choice)
                if picked == "expense":
                    sess.meta["type"] = "expense"
                    sess.meta["amount"] = -abs(sess.meta.get("amount", 0))
                elif picked == "income":
                    sess.meta["type"] = "income"
                    sess.meta["amount"] = abs(sess.meta.get("amount", 0))
                # 后续步骤：已识别的字段直接跳过，只问缺失的
                nxt = self._bill_next_step(sess)
                if nxt is None:
                    sess.wizard = None
                    sess.touch()
                    return event.plain_result(self._bill_confirm_text(sess))
                sess.wizard = {"step": nxt}
                sess.touch()
                return event.plain_result(self._bill_step_prompt(nxt))
            return event.plain_result("请回复数字 1-4 选择：\n" + self._bill_type_prompt())

        if step == "bill_reinput":
            parsed, err = parse_bill(text)
            if parsed is None:
                return event.plain_result("账单解析失败：{}，请重发或发“取消”。".format(err))
            sess.meta.update(parsed)
            self._apply_bill_defaults(parsed)
            sess.touch()
            sess.wizard = {"step": "bill_confirm_type"}
            return event.plain_result(
                "已重新识别：{} 金额{}，分类{}，账户{}\n\n".format(
                    parsed.get("title"), parsed.get("amount"), parsed.get("category"), parsed.get("account"))
                + self._bill_type_prompt()
            )

        if step == "bill_pick_category":
            choice = parse_choice(text, len(BILL_CATEGORIES))
            if choice is not None:
                sess.meta["category"] = BILL_CATEGORIES[choice - 1]
            elif text and 1 <= len(text.strip()) <= 10:
                # 白名单外直接接受为自定义分类（如「水产」「鱼」）
                sess.meta["category"] = text.strip()
            else:
                return event.plain_result(
                    "请回复数字选常用分类，或直接发自定义分类名（1-10 字）：\n"
                    + format_choices("请选择分类：", BILL_CATEGORIES, with_skip_cancel=False)
                )
            nxt = self._bill_next_step(sess)
            if nxt is None:
                sess.wizard = None
                sess.touch()
                return event.plain_result(self._bill_confirm_text(sess))
            sess.wizard = {"step": nxt}
            sess.touch()
            return event.plain_result(self._bill_step_prompt(nxt))

        if step == "bill_pick_account":
            all_accounts = self._bill_accounts_all()
            choice = parse_choice(text, len(all_accounts))
            if choice is not None:
                sess.meta["account"] = all_accounts[choice - 1]
            elif text and 1 <= len(text.strip()) <= 10:
                sess.meta["account"] = text.strip()
            else:
                return event.plain_result("请回复数字选择账户，或直接发账户名：\n" + format_choices("请选择账户：", all_accounts, with_skip_cancel=False))
            sess.wizard = None
            sess.touch()
            return event.plain_result(self._bill_confirm_text(sess))

        # ---- 导航向导（分类=文件夹，2026-09-21 对齐博客） ----
        if step == "daohang_pick_category":
            folders = sess.wizard.get("folders", [])
            total = len(folders) + 1  # 含新建
            choice = parse_choice(text, total)
            if choice is not None:
                if choice == total:  # 新建分类
                    sess.wizard = {"step": "daohang_input_new_category", "folders": folders}
                    return event.plain_result("请输入新分类名（将作为文件夹名，如：摄影网站）：")
                picked = folders[choice - 1]
                sess.meta["category"] = picked
                sess.wizard = None
                sess.touch()
                return event.plain_result(
                    "已选分类「{}」。\n可继续发键值对：名称: xxx / 描述: xxx，可加 #标签\n发 /发布 提交，/取消 放弃。".format(picked)
                )
            if is_wizard_skip(text):
                default_cat = clean_filename_part(
                    self._cfg("daohang_default_category", "未分类") or "未分类", fallback="未分类"
                )
                sess.meta["category"] = default_cat
                sess.wizard = None
                sess.touch()
                return event.plain_result(
                    "已用默认分类「{}」。\n可继续发键值对：名称: xxx / 描述: xxx，可加 #标签\n发 /发布 提交，/取消 放弃。".format(default_cat)
                )
            if text and len(text) <= 20:
                # 直接回复分类名：命中现有文件夹（忽略大小写/空格差异）则用原名，否则作为新分类
                norm = re.sub(r"\s+", "", text).lower()
                matched = next((f for f in folders if re.sub(r"\s+", "", f).lower() == norm), "")
                picked = matched or clean_filename_part(text, fallback="")
                if picked:
                    sess.meta["category"] = picked
                    sess.wizard = None
                    sess.touch()
                    hint = "已选分类「{}」".format(picked) if matched else "已新建分类「{}」".format(picked)
                    return event.plain_result(
                        "{hint}。\n可继续发键值对：名称: xxx / 描述: xxx，可加 #标签\n发 /发布 提交，/取消 放弃。".format(hint=hint)
                    )
            return event.plain_result(
                "请回复数字选择分类，或直接发分类名：\n"
                + format_choices("请选择分类（文件夹）：", folders, extra=["新建分类"], with_skip_cancel=False)
            )

        if step == "daohang_input_new_category":
            chk = clean_filename_part(text, fallback="")
            if not chk:
                return event.plain_result("分类名无效，请重发（1-20 字，避免特殊符号）：")
            sess.meta["category"] = chk
            sess.wizard = None
            sess.touch()
            return event.plain_result(
                "已新建分类「{}」。\n可继续发键值对：名称: xxx / 描述: xxx，可加 #标签\n发 /发布 提交，/取消 放弃。".format(chk)
            )

        return None

    # ---------- 其他 ----------

    def _help_text(self) -> str:
        return (
            "📖 BlogWriter 使用手册\n"
            "\n"
            "———— ✍ 发内容 ————\n"
            "/动态 内容 #标签\n"
            "　可发图片、GIF、视频\n"
            "/笔记 [分类] 标题\n"
            "　空参会让你选笔记本/输标题\n"
            "/足迹 省 地点 体验\n"
            "　坐标自动获取，可发照片\n"
            "/友链\n"
            "　逐行发：名称/描述/链接/头像\n"
            "/相册 相册名\n"
            "　空参会列出相册让你选或新建\n"
            "\n"
            "———— 💰 记生活 ————\n"
            "/账单 午餐微信花了32\n"
            "　支持补记：/账单 昨天 午餐30 或 10-08 午餐30\n"
            "　确认类型后发布；分类账户已识别则免问\n"
            "/存账 绿茶3（或 /记一笔）\n"
            "　随手存入待发暂存箱，睡前发 /发布 一次性提交\n"
            "/查存账　查看待发暂存箱\n"
            "/清存账　清空待发暂存箱\n"
            "/撤回　发布后10分钟内一键回滚\n"
            "/日程 明天3点在A开会 每周\n"
            "　支持优先级、提前15分钟提醒\n"
            "/生日 我的农历8.24\n"
            "　可一句多人：我的8.24对象12.22\n"
            "/纪念日 结婚纪念日 农历5.20\n"
            "　格式：标题 日期 @人物\n"
            "/影视 侏罗纪世界\n"
            "　封面自动从 TMDB 获取\n"
            "　搜不到会让你选类型/评分/标签\n"
            "/书籍 认知觉醒\n"
            "　封面自己发一张，评分/标签/书评\n"
            "/导航 https://example.com\n"
            "　图标自动获取，向导选分类（文件夹），\n"
            "　随后发键值对：名称/描述，可加 #标签\n"
            "/转载 公众号文章链接\n"
            "　抓取正文图片转存图床，生成博客文章\n"
            "\n"
            "———— 🔧 管会话 ————\n"
            "/发布　提交当前会话\n"
            "/取消　放弃当前会话\n"
            "/状态　查看当前会话\n"
            "/提醒 列表　看待提醒\n"
            "/提醒 取消 标题　取消提醒\n"
            "\n"
            "发 /帮助 随时查看本手册"
        )

    async def terminate(self):
        self._sessions.clear()
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        # 官方规范：卸载/停用插件时必须清理后台线程，否则重载后调度器残留可能双发提醒
        if self._scheduler is not None:
            try:
                self._scheduler.shutdown(wait=False)
            except Exception as e:
                logger.warning("BlogWriter: 关闭提醒调度器失败: %s", e)
            self._scheduler = None
