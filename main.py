"""Nyaa猫猫闹钟 —— 定时主动给 QQ 群聊或好友发送提醒消息。

原理：
- 所有提醒任务以列表形式存储在插件配置中（`_conf_schema.json` → WebUI 渲染）。
- 后台 asyncio 循环每 30 秒扫描一次任务列表，匹配当前时间。
- 命中后通过 AstrBot 标准 API `context.send_message()` 主动推送消息。
- 一次性任务触发后自动禁用；每日任务按 HH:MM 每日触发。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional, Set

from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.all import MessageChain

__author__ = "NyaaCaster"
__signature__ = "Nyaa be with you."

# --------------------------------------------------------------------------- #
# 注册
# --------------------------------------------------------------------------- #

@register(
    "astrbot_plugin_nyaa_reminder",
    "NyaaCaster",
    "定时主动给QQ群聊或者QQ号发送消息。在 WebUI 插件配置页添加任务，支持一次性/每日提醒。",
    "1.0.0",
    "https://github.com/NyaaCaster/astrbot_plugin_nyaa_reminder",
)
class NyaaReminderPlugin(Star):
    def __init__(self, context: Context, config: Optional[dict] = None):
        super().__init__(context)
        self.config = config or {}
        self._config_key = "astrbot_plugin_nyaa_reminder"
        # 后台扫描任务
        self._scan_task: Optional[asyncio.Task] = None
        # 防重复：记录已触发的每日任务 "target_id|HH:MM|YYYY-MM-DD"
        self._fired_daily: Set[str] = set()
        # Platform ID，在 initialize() 中动态获取
        self._platform_id: str = "aiocqhttp"

    # ------------------------------------------------------------------- #
    # 生命周期
    # ------------------------------------------------------------------- #

    async def initialize(self) -> None:
        # 动态获取 aiocqhttp 平台的实际 ID（meta().id 与 meta().name 不同）
        for p in self.context.platform_manager.platform_insts:
            if p.meta().name == "aiocqhttp":
                self._platform_id = p.meta().id
                break
        logger.info(
            f"[nyaa_reminder] 猫猫闹钟已启动，platform_id={self._platform_id}"
        )
        self._scan_task = asyncio.create_task(self._scan_loop())

    async def terminate(self) -> None:
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
            self._scan_task = None
        logger.info("[nyaa_reminder] 猫猫闹钟已停止。")

    # ------------------------------------------------------------------- #
    # 后台扫描循环
    # ------------------------------------------------------------------- #

    async def _scan_loop(self) -> None:
        """每 30 秒检查一次任务列表，匹配时间并触发提醒。"""
        while True:
            try:
                await asyncio.sleep(30)
                await self._check_and_fire()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[nyaa_reminder] 扫描提醒任务时发生异常")

    # ------------------------------------------------------------------- #
    # 时间匹配 & 触发
    # ------------------------------------------------------------------- #

    async def _check_and_fire(self) -> None:
        now = datetime.now()
        tasks: list = self.config.get(self._config_key, [])
        if not tasks:
            return

        changed = False

        for i, task in enumerate(tasks):
            if not isinstance(task, dict):
                continue
            if not task.get("enabled", True):
                continue

            target_id = str(task.get("target_id", "")).strip()
            if not target_id:
                continue

            reminder_type = task.get("reminder_type", "每日")
            time_str = str(task.get("reminder_time", "")).strip()
            if not time_str:
                continue

            if reminder_type == "一次性":
                if self._match_once(now, time_str):
                    await self._send_reminder(task)
                    # 触发后禁用
                    tasks[i] = dict(task)
                    tasks[i]["enabled"] = False
                    changed = True
                    logger.info(
                        f"[nyaa_reminder] 一次性提醒已触发并禁用: "
                        f"target={target_id} time={time_str}"
                    )
            else:
                # 每日
                if self._match_daily(now, time_str):
                    fire_key = f"{target_id}|{time_str}|{now.strftime('%Y-%m-%d')}"
                    if fire_key not in self._fired_daily:
                        self._fired_daily.add(fire_key)
                        await self._send_reminder(task)
                        logger.info(
                            f"[nyaa_reminder] 每日提醒已触发: "
                            f"target={target_id} time={time_str}"
                        )

        # 每天午夜清空防重复记录
        if now.hour == 0 and now.minute < 1:
            self._fired_daily.clear()

        if changed:
            self.config[self._config_key] = tasks
            try:
                self.config.save_config()
            except Exception:
                logger.exception("[nyaa_reminder] 保存配置失败")

    # ------------------------------------------------------------------- #
    # 时间解析辅助
    # ------------------------------------------------------------------- #

    @staticmethod
    def _match_once(now: datetime, time_str: str) -> bool:
        """检查当前时间是否匹配一次性任务的 YYYY-MM-DD HH:MM。"""
        try:
            target = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
            return (
                now.year == target.year
                and now.month == target.month
                and now.day == target.day
                and now.hour == target.hour
                and now.minute == target.minute
            )
        except ValueError:
            logger.warning(f"[nyaa_reminder] 无效的一次性时间格式: {time_str!r}")
            return False

    @staticmethod
    def _match_daily(now: datetime, time_str: str) -> bool:
        """检查当前时间是否匹配每日任务的 HH:MM。"""
        try:
            target = datetime.strptime(time_str, "%H:%M")
            return now.hour == target.hour and now.minute == target.minute
        except ValueError:
            logger.warning(f"[nyaa_reminder] 无效的每日时间格式: {time_str!r}")
            return False

    # ------------------------------------------------------------------- #
    # 消息发送
    # ------------------------------------------------------------------- #

    async def _send_reminder(self, task: dict) -> bool:
        """通过 AstrBot 平台 API 主动发送提醒消息。"""
        target_type = task.get("target_type", "群聊")
        target_id = str(task.get("target_id", "")).strip()
        message_content = task.get("message_content", "") or "（空消息）"

        # 构造 unified_msg_origin 格式: platform_id:MessageType:session_id
        message_type = "GroupMessage" if target_type == "群聊" else "FriendMessage"
        session_str = f"{self._platform_id}:{message_type}:{target_id}"

        chain = MessageChain().message(message_content)
        ok = await self.context.send_message(session_str, chain)
        if ok:
            logger.info(
                f"[nyaa_reminder] 提醒已发送: "
                f"type={target_type} target={target_id}"
            )
        else:
            logger.warning(
                f"[nyaa_reminder] 提醒发送失败（未找到匹配平台）: "
                f"session={session_str}"
            )
        return ok
