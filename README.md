# astrbot_plugin_nyaa_reminder

> Nyaa猫猫闹钟 —— 定时主动给 QQ 群聊或好友发送提醒消息。

通过 AstrBot 标准 WebUI 配置页管理定时任务，支持**一次性**和**每日**两种提醒模式。后台每 30 秒扫描到期任务，命中后通过 AstrBot 平台 API 主动推送消息，无需聊天触发。

## 兼容性

- 需要 AstrBot `>=4.0.0`。
- 需在 QQ 平台（aiocqhttp / NapCat）下使用；其他平台未经测试。

## 安装

本插件已发布至 AstrBot 插件市场，推荐通过 WebUI 一键安装：

1. 进入 AstrBot 管理面板（WebUI）。
2. 在左侧菜单栏点击 **插件**。
3. 进入 **插件市场**，搜索 `astrbot_plugin_nyaa_reminder` 或 `Nyaa猫猫闹钟`。
4. 点击 **安装** 并等待完成。
5. 安装后在已安装插件列表中找到本插件，进入配置页添加任务即可。

*(手动安装方式：将本仓库克隆至 AstrBot 的 `data/plugins/` 目录中，然后重启 AstrBot。)*

## 使用方式

1. 在 WebUI 插件管理页找到 **Nyaa猫猫闹钟**，点击进入配置。
2. 在任务列表中点击 **添加**，填写任务信息：
   - **启用此任务**：开关，默认开启。
   - **目标类型**：选择 `个人`（私聊）或 `群聊`。
   - **QQ号 或 群号**：填写目标 QQ 号或群号。
   - **提醒类型**：选择 `一次性` 或 `每日`（默认每日）。
   - **提醒时间**：
     - 一次性：填入 `YYYY-MM-DD HH:MM`，例如 `2026-07-15 09:00`。
     - 每日：填入 `HH:MM`，例如 `09:00`。
   - **消息内容**：填写要发送的提醒文本，支持换行。
3. 保存配置后，后台自动开始扫描。

## 配置项

| 配置 | 说明 |
| --- | --- |
| `tasks` | 任务列表，每项一条提醒 |

每条任务包含以下字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | 开关 | 是否启用此任务，可随时关闭/开启 |
| `target_type` | 下拉 | `个人` 或 `群聊` |
| `target_id` | 文本 | QQ 号 或 群号 |
| `reminder_type` | 下拉 | `一次性` 或 `每日`（默认每日） |
| `reminder_time` | 文本 | 一次性：`YYYY-MM-DD HH:MM`；每日：`HH:MM` |
| `message_content` | 多行文本 | 要发送的提醒消息内容，支持换行 |

## 行为说明

- **一次性任务**：到达指定时间的**那一分钟**内触发并发送消息，随后自动禁用（`enabled` 变为关闭）。如需再次触发，手动重新启用并修改时间即可。
- **每日任务**：每天到达指定时间的**那一分钟**内触发。同一任务同一天同一分钟只会触发一次（有防重复机制），不会因 30 秒扫描间隔而重复发送。
- 任务不填 QQ 号/群号、不填时间、或被禁用时，均会被跳过不触发。
- 发送失败（如平台未连接）会在 AstrBot 日志中记录 warning，不会导致插件崩溃。

> 注意：消息通过 AstrBot 平台 API 主动推送。如果目标会话不存在（如机器人未加该好友/未进该群），消息将发送失败。

## 工作原理

本插件**不自建定时器框架**，而是复用 AstrBot 插件生命周期：

```
initialize() → 启动 asyncio 后台循环（每 30 秒 sleep）
    ↓
_check_and_fire() → 遍历配置中所有任务
    ↓
时间匹配 → context.send_message(session, MessageChain) → 平台推送
    ↓
一次性任务 → enabled = False → save_config() 持久化
```

任务配置存储在 AstrBot 标准插件配置文件中（`data/config/astrbot_plugin_nyaa_reminder_config.json`），由 `_conf_schema.json` 驱动 WebUI 渲染，用户通过 WebUI 修改后 AstrBot 自动重载插件。

消息发送使用 `unified_msg_origin` 会话格式：`aiocqhttp:GroupMessage:{群号}` 或 `aiocqhttp:FriendMessage:{QQ号}`，通过 AstrBot 平台适配器路由到 NapCat/OneBot 执行。

## License

MIT
