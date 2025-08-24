# AstrBot Minecraft MOTD

![Python Versions](https://img.shields.io/badge/python-3.8%20%7C%203.9%20%7C%203.10-blue)
![License](https://img.shields.io/github/license/ChuranNeko/astrbot_plugin_Minecraft_motd)
![Version](https://img.shields.io/badge/version-1.7.0-green)

## 🌟 功能简介

本插件为 **AstrBot** 提供 `/motd` 命令，可在本地主动探测指定 **Minecraft Java** 或 **Bedrock** 服务器（无需外部 HTTP API），获取状态信息（MOTD、在线状态、玩家人数、服务器图标等），并在本地渲染状态图片发送到聊天中。

### ✨ 主要特性

* **多版本支持**：Java 版 & 基岩版
* **智能探测模式**：
  - **自动模式**：竞速探测 Java、Bedrock 和 SRV 记录，返回最先成功的结果
  - **指定模式**：可强制指定探测 Java 版(`-je`)、基岩版(`-be`)或仅查询 SRV 记录(`-srv`)
* **SRV 记录支持**：自动解析 `_minecraft._tcp.domain` SRV 记录
* **高级网络支持**：支持 IPv4、IPv6、域名解析
* **本地渲染**：美观的状态卡片，支持服务器图标显示
* **异步并发**：高性能的并发探测，提升响应速度

---

## 📦 依赖说明

运行此插件需要以下依赖（已包含在 `requirements.txt` 中）：

```txt
validators>=0.35.0
mcstatus>=11.0.0
Pillow>=10.3.0
requests>=2.25.0
dnspython>=2.3.0
```

---

**字体文件**：插件包含 `font/Minecraft_AE.ttf` 字体文件，确保跨平台兼容性和 Minecraft 主题一致性。

---

## 📋 使用方法

### 命令格式

```bash
/motd <server_address>[:<port>] [选项]
/motd [选项] <server_address>[:<port>]
```

#### 参数说明

* `server_address`：服务器地址，支持 IPv4、IPv6、域名
* `port`：端口号（可选）
* 选项参数：
  - `-je`：仅探测 Java 版服务器
  - `-be`：仅探测基岩版服务器 
  - `-srv`：仅查询 SRV 记录
  - 无选项：自动模式（推荐）

#### 探测策略

* **自动模式**（默认）：并行竞速探测，返回最先成功的结果
  - 未指定端口：同时探测 Java(25565) + Bedrock(19132) + SRV 记录
  - 指定端口：同时探测该端口的 Java 和 Bedrock
* **指定模式**：按选项强制探测特定版本
* **SRV 模式**：解析 `_minecraft._tcp.domain` 记录后探测 Java 版

### 地址格式支持

* **IPv4**：`192.168.1.1`、`mc.example.com`
* **IPv6**：`2001:db8::1`、`[::1]:25565`、`[2001:db8::1]:19132`
* **域名**：`mc.hypixel.net`、`play.example.com`

### 使用示例

```bash
# 自动模式（推荐）- 竞速探测所有方式
/motd mc.hypixel.net
/motd play.example.com:25565

# 强制探测 Java 版
/motd mc.hypixel.net -je
/motd -je play.example.com:25565

# 强制探测基岩版
/motd -be mc.example.net:19132
/motd mc.example.net:19132 -be

# 仅查询 SRV 记录
/motd -srv mc.hypixel.net
/motd play.example.com -srv

# IPv6 地址支持
/motd [2001:db8::1]:25565
/motd [::1]:19132 -be
```

> 💡 **智能提示**：插件采用本地探测技术，支持异步并发查询。自动模式会智能选择最佳连接方式，提供最快的响应体验。

---

## 🔧 安装指南

### 方法一：插件市场安装（推荐）

在 **AstrBot 插件市场** 搜索 **AstrBot_Minecraft_MOTD** 并一键安装。

### 方法二：手动安装

```bash
cd AstrBot/data/plugins
git clone https://github.com/ChuranNeko/astrbot_plugin_minecraft_motd.git
cd astrbot_plugin_minecraft_motd
pip install -r requirements.txt
```

---

## 📋 返回信息详情

插件返回的状态卡片包含以下信息：

### 🎨 可视化状态卡片
* **服务器图标**：优先显示服务器 favicon，无则显示默认 Minecraft logo
* **版本徽标**：Java 版 / BE基岩版 标识
* **状态指示器**：在线/离线状态可视化
* **性能指标**：延迟、协议版本、游戏版本
* **玩家信息**：当前在线人数、最大人数
* **玩家列表**：在线玩家示例（Java版支持）
* **服务器描述**：MOTD 文本，支持多行显示

### 📱 文本摘要
包含完整的服务器状态文本摘要，适合快速查看：
* ✅ 在线状态
* 📋 服务器描述
* 💳 协议版本
* 🧰 游戏版本
* 📡 网络延迟
* 👧 玩家在线情况

---

## 🚀 技术特性

### 🎥 高性能网络处理
* **异步并发**：采用 Python asyncio 实现高并发探测
* **智能超时**：5秒自适应超时机制，避免无效等待
* **网络容错**：异步优先，同步备用，确保连接成功率

### 🔍 DNS 解析增强
* **SRV 记录支持**：自动解析 `_minecraft._tcp.domain` 记录
* **多协议兼容**：支持 IPv4、IPv6 双栈网络
* **域名验证**：严格的地址格式验证，防止输入错误

### 🎨 视觉体验优化
* **原生字体**：内置 Minecraft 官方字体，保持风格一致
* **自动图标**：智能获取服务器 favicon，失败时使用默认 logo
* **响应式布局**：自适应文本折行，支持多行 MOTD 显示
* **颜色码清理**：自动去除 Minecraft 颜色码，保持文本清洁

---

## 📄 许可证

本项目采用 **MIT** 许可证 - 详情请参阅 [LICENSE](LICENSE)。

---

## 🙏 致敬

* [AstrBot](https://github.com/AstrBotDevs/AstrBot) — 高性能聊天机器人框架


