from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
import astrbot.api.message_components as Comp
from astrbot.api import logger

import asyncio
import re
import base64
from io import BytesIO
from typing import Optional, List, Tuple, Dict
import os
import tempfile

import validators
import dns.resolver
from mcstatus import JavaServer, BedrockServer
from PIL import Image, ImageDraw, ImageFont


@register("astrbot_minecraft_motd", "ChuranNeko", "Minecraft 服务器 MOTD 状态图", "1.7.0")
class MinecraftMOTDPlugin(Star):
    """
    Minecraft 服务器 MOTD 插件
    """
    def __init__(self, context: Context):
        super().__init__(context)

    def _parse_command(self, message_str: str) -> Dict:
        """
        解析 MOTD 命令，支持选项参数
        
        支持格式:
        /motd <server_address>[:<port>] [-je|-be|-srv]
        /motd [-je|-be|-srv] <server_address>[:<port>]
        
        返回:
        {
            'address': str,           # 服务器地址
            'port': int or None,      # 端口号
            'mode': str,             # 'java', 'bedrock', 'srv', 'auto'
            'valid': bool            # 是否有效
        }
        """
        
        # 去除开头的 motd 命令
        if message_str.strip() == "motd":
            return {'valid': False, 'error': 'no_params'}
        
        if message_str.startswith("motd "):
            content = message_str[len("motd "):].strip()
        else:
            return {'valid': False, 'error': 'invalid_command'}
        
        if not content:
            return {'valid': False, 'error': 'no_params'}
        
        # 分词解析
        parts = content.split()
        
        # 查找选项参数
        mode = 'auto'  # 默认为自动模式
        server_part = None
        
        # 支持选项在前面或后面
        for part in parts:
            if part == '-je':
                mode = 'java'
            elif part == '-be':
                mode = 'bedrock'
            elif part == '-srv':
                mode = 'srv'
            else:
                if server_part is None:
                    server_part = part
        
        if not server_part:
            return {'valid': False, 'error': 'no_server'}
        
        # 解析服务器地址和端口
        ipv6_pattern = r"^\[?([0-9a-fA-F:]+)\]?(?::(\d+))?$"
        ipv4_domain_pattern = r"^([a-zA-Z0-9\.\-_]+)(?::(\d+))?$"
        
        # 先尝试 IPv6 格式
        match = re.match(ipv6_pattern, server_part)
        if not match:
            # 再尝试 IPv4 或域名格式
            match = re.match(ipv4_domain_pattern, server_part)
        
        if not match:
            return {'valid': False, 'error': 'invalid_format'}
        
        address = match.group(1)
        port = int(match.group(2)) if match.group(2) else None
        
        return {
            'valid': True,
            'address': address,
            'port': port,
            'mode': mode
        }

    @filter.command("motd")
    async def handle_motd(self, event: AstrMessageEvent):
        """
        处理 MOTD 命令，探测 Minecraft 服务器状态
        
        支持格式:
        /motd <server_address>[:<port>] [-je|-be|-srv]
        /motd [-je|-be|-srv] <server_address>[:<port>]
        
        选项说明:
        -je: 仅探测 Java 版服务器
        -be: 仅探测基岩版服务器
        -srv: 仅查询 SRV 记录
        无选项: 自动模式，竞速探测所有方式
        """
        
        # 解析命令
        message_str = event.message_str.strip()
        logger.info(f"收到 MOTD 请求，消息长度: {len(message_str)}")
        
        parsed = self._parse_command(message_str)
        
        if not parsed['valid']:
            error_type = parsed.get('error', 'unknown')
            if error_type in ['no_params', 'no_server']:
                usage = (
                    "用法:\n"
                    "/motd <server_address>[:<port>] [选项]\n"
                    "\n"
                    "选项:\n"
                    "-je: 仅探测 Java 版服务器\n"
                    "-be: 仅探测基岩版服务器\n"
                    "-srv: 仅查询 SRV 记录\n"
                    "\n"
                    "示例:\n"
                    "/motd mc.hypixel.net         # 自动模式\n"
                    "/motd mc.hypixel.net -je     # 仅 Java 版\n"
                    "/motd -be mc.hypixel.net:19132  # 仅基岩版\n"
                    "/motd -srv mc.hypixel.net    # 仅 SRV 记录"
                )
            else:
                usage = "参数格式错误，请使用 /motd <server_address>[:<port>] [选项]"
            
            yield event.plain_result(usage)
            return

        address = parsed['address']
        port = parsed['port']
        mode = parsed['mode']
        
        logger.info(f"解析结果: 地址={address}, 端口={port}, 模式={mode}")

        # 验证地址格式
        if not self._validate_address(address):
            logger.info(f"地址验证失败: {address}")
            yield event.plain_result("服务器地址无效")
            return

        # 根据模式执行不同的探测策略
        status_infos = await self._execute_probe_strategy(address, port, mode)
        
        if not status_infos:
            yield event.plain_result("当前服务器不在线，或者当前服务器信息输入错误，请检查服务器与端口后重试")
            return

        # 处理探测结果
        for status_info in status_infos:
            # 渲染图片和文本
            img_bytes, status_text = await self._render_status_card(status_info)
            file_path = self._save_temp_image(img_bytes)

            logger.info(f"发送 Minecraft MOTD 本地渲染图片: {file_path}")

            # 异步清理临时文件
            asyncio.create_task(self._cleanup_file(file_path))

            # 图片和文字一并发送
            yield event.chain_result([Comp.Image(file_path), Comp.Plain(status_text)])
        return

    async def initialize(self):
        logger.info("MinecraftMOTDPlugin 已初始化")
    
    def _validate_address(self, address: str) -> bool:
        """验证服务器地址格式"""
        if not address:
            return False
        
        # 检查是否为有效的 IPv4 地址
        try:
            if validators.ip_address.ipv4(address, cidr=False):
                return True
        except:
            pass
        
        # 检查是否为有效的 IPv6 地址  
        try:
            if validators.ip_address.ipv6(address, cidr=False):
                return True
        except:
            pass
        
        # 检查是否为有效的域名
        try:
            if validators.domain(address):
                return True
        except:
            pass
        
        # 简单的域名格式检查：包含点且不包含非法字符
        if '.' in address and not any(char in address for char in [' ', '/', '\\', '?', '#']):
            return True
        
        return False

    async def _resolve_srv_record(self, domain: str, timeout_sec: float = 5.0) -> Optional[Tuple[str, int]]:
        """
        解析 Minecraft Java 版 SRV 记录
        
        Args:
            domain: 要查询的域名
            timeout_sec: 超时时间
            
        Returns:
            (实际服务器地址, 端口) 或 None
        """
        try:
            logger.info(f"开始 SRV 记录查询: {domain}")
            
            # 查询 _minecraft._tcp.domain 的 SRV 记录
            srv_name = f"_minecraft._tcp.{domain}"
            
            # 设置超时
            resolver = dns.resolver.Resolver()
            resolver.timeout = timeout_sec
            resolver.lifetime = timeout_sec
            
            # 执行 SRV 查询
            answers = resolver.resolve(srv_name, 'SRV')
            
            if answers:
                # 选择优先级最高（数值最小）的记录
                srv_record = min(answers, key=lambda x: x.priority)
                
                # 获取目标主机和端口
                target_host = str(srv_record.target).rstrip('.')
                target_port = srv_record.port
                
                logger.info(f"SRV 记录解析成功: {domain} -> {target_host}:{target_port}")
                return (target_host, target_port)
            
        except dns.resolver.NXDOMAIN:
            logger.info(f"SRV 记录不存在: {domain}")
        except dns.resolver.NoAnswer:
            logger.info(f"SRV 记录无答案: {domain}")
        except dns.resolver.Timeout:
            logger.warning(f"SRV 记录查询超时: {domain}")
        except Exception as e:
            logger.warning(f"SRV 记录查询失败: {domain} - {type(e).__name__}: {e}")
        
        return None

    async def _execute_probe_strategy(self, address: str, port: Optional[int], mode: str) -> List[dict]:
        """
        根据模式执行不同的探测策略
        
        Args:
            address: 服务器地址
            port: 端口号
            mode: 探测模式 ('java', 'bedrock', 'srv', 'auto')
            
        Returns:
            成功探测的服务器信息列表
        """
        timeout_sec = 5.0
        
        if mode == 'java':
            # 仅探测 Java 版
            default_port = port or 25565
            result = await self._probe_java(address, default_port, timeout_sec)
            return [result] if result else []
            
        elif mode == 'bedrock':
            # 仅探测基岩版
            default_port = port or 19132
            result = await self._probe_bedrock(address, default_port, timeout_sec)
            return [result] if result else []
            
        elif mode == 'srv':
            # 仅查询 SRV 记录
            if port:
                logger.warning("SRV 模式忽略指定的端口号")
            
            srv_result = await self._resolve_srv_record(address, timeout_sec)
            if srv_result:
                srv_host, srv_port = srv_result
                result = await self._probe_java(srv_host, srv_port, timeout_sec)
                if result:
                    # 标记这是通过 SRV 记录找到的
                    result['srv_resolved'] = True
                    result['original_domain'] = address
                return [result] if result else []
            return []
            
        elif mode == 'auto':
            # 自动模式：竞速探测所有方式
            return await self._auto_race_probe(address, port, timeout_sec)
        
        return []

    async def _auto_race_probe(self, address: str, port: Optional[int], timeout_sec: float) -> List[dict]:
        """
        自动模式的竞速探测：同时尝试 Java、Bedrock 和 SRV，返回最先成功的结果
        
        Args:
            address: 服务器地址
            port: 端口号
            timeout_sec: 超时时间
            
        Returns:
            成功探测的服务器信息列表
        """
        tasks = []
        
        if port is None:
            # 未指定端口：并行探测 Java(25565) 和 Bedrock(19132)，以及 SRV
            tasks.append(self._probe_java(address, 25565, timeout_sec))
            tasks.append(self._probe_bedrock(address, 19132, timeout_sec))
            
            # 只有域名才查询 SRV 记录（IP 地址没有 SRV）
            if not validators.ip_address.ipv4(address, cidr=False) and not validators.ip_address.ipv6(address, cidr=False):
                tasks.append(self._probe_via_srv(address, timeout_sec))
        else:
            # 指定端口：并行探测 Java 和 Bedrock
            tasks.append(self._probe_java(address, port, timeout_sec))
            tasks.append(self._probe_bedrock(address, port, timeout_sec))
        
        # 并行执行所有任务，收集所有成功的结果
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 过滤成功的结果
        valid_results = []
        for result in results:
            if isinstance(result, dict) and result is not None:
                valid_results.append(result)
        
        return valid_results

    async def _probe_via_srv(self, domain: str, timeout_sec: float) -> Optional[dict]:
        """通过 SRV 记录探测 Java 服务器"""
        srv_result = await self._resolve_srv_record(domain, timeout_sec)
        if srv_result:
            srv_host, srv_port = srv_result
            result = await self._probe_java(srv_host, srv_port, timeout_sec)
            if result:
                result['srv_resolved'] = True
                result['original_domain'] = domain
            return result
        return None

    async def terminate(self):
        logger.info("MinecraftMOTDPlugin 已停止")

    async def _probe_java(self, host: str, port: int, timeout_sec: float = 5.0) -> Optional[dict]:
        """
        探测 Java 版服务器
        
        Args:
            host: 服务器地址
            port: 端口号
            timeout_sec: 超时时间
            
        Returns:
            服务器信息或 None
        """
        try:
            logger.info(f"开始 Java 探测: {host}:{port}")
            
            # 创建服务器对象
            server = JavaServer.lookup(f"{host}:{port}")
            logger.info(f"JavaServer.lookup 成功: {host}:{port}")
            
            # 获取服务器状态（先尝试异步，失败后尝试同步）
            try:
                status = await asyncio.wait_for(server.async_status(), timeout=timeout_sec)
                logger.info(f"Java 异步探测成功: {host}:{port}")
            except Exception as async_error:
                logger.info(f"Java 异步探测失败，尝试同步: {async_error}")
                # 备选方案：使用同步方法
                status = await asyncio.get_event_loop().run_in_executor(None, server.status)
                logger.info(f"Java 同步探测成功: {host}:{port}")
            # 解析 Java 返回
            version_name = getattr(status.version, "name", "")
            protocol = getattr(status.version, "protocol", None)
            players_online = getattr(status.players, "online", 0)
            players_max = getattr(status.players, "max", 0)
            sample_names: List[str] = []
            sample = getattr(status.players, "sample", None)
            if sample:
                try:
                    sample_names = [getattr(p, "name", "") for p in sample if getattr(p, "name", None)]
                except Exception:
                    sample_names = []

            # MOTD 兼容处理
            motd_text = None
            desc = getattr(status, "description", None)
            if isinstance(desc, str):
                motd_text = desc
            else:
                # mcstatus 可能返回 Description 对象或 dict
                try:
                    motd_text = getattr(desc, "clean", None) or str(desc)
                except Exception:
                    motd_text = str(desc) if desc is not None else ""

            favicon_data_uri = getattr(status, "favicon", None)

            return {
                "edition": "Java",
                "host": host,
                "port": port,
                "online": True,
                "latency_ms": round(getattr(status, "latency", 0)),
                "protocol": protocol,
                "version_name": version_name,
                "players_online": players_online,
                "players_max": players_max,
                "player_names": sample_names,
                "motd": motd_text or "",
                "favicon_data_uri": favicon_data_uri,
            }
        except asyncio.TimeoutError:
            logger.warning(f"Java 探测超时: {host}:{port} (超时 {timeout_sec}s)")
            return None
        except ConnectionError as e:
            logger.warning(f"Java 连接错误: {host}:{port} - {e}")
            return None
        except Exception as e:
            logger.warning(f"Java 探测失败: {host}:{port} - {type(e).__name__}: {e}")
            return None

    async def _probe_bedrock(self, host: str, port: int, timeout_sec: float = 5.0) -> Optional[dict]:
        """
        探测 Bedrock 版服务器
        
        Args:
            host: 服务器地址
            port: 端口号
            timeout_sec: 超时时间
            
        Returns:
            服务器信息或 None
        """
        try:
            logger.info(f"开始 Bedrock 探测: {host}:{port}")
            
            # 创建服务器对象
            server = BedrockServer.lookup(f"{host}:{port}")
            logger.info(f"BedrockServer.lookup 成功: {host}:{port}")
            
            # 获取服务器状态（先尝试异步，失败后尝试同步）
            try:
                status = await asyncio.wait_for(server.async_status(), timeout=timeout_sec)
                logger.info(f"Bedrock 异步探测成功: {host}:{port}")
            except Exception as async_error:
                logger.info(f"Bedrock 异步探测失败，尝试同步: {async_error}")
                # 备选方案：使用同步方法
                status = await asyncio.get_event_loop().run_in_executor(None, server.status)
                logger.info(f"Bedrock 同步探测成功: {host}:{port}")

            # Bedrock 字段兼容（根据 mcstatus 命令行输出修正）
            version_raw = getattr(status, "version", None)
            protocol = None
            
            if version_raw:
                # 如果 version 是对象，尝试获取 name 和 protocol 属性
                if hasattr(version_raw, 'name'):
                    version_name = getattr(version_raw, 'name', '')
                else:
                    version_name = str(version_raw)
                    
                # 获取协议号
                if hasattr(version_raw, 'protocol'):
                    protocol = getattr(version_raw, 'protocol', None)
            else:
                # 备选方案
                version_name = getattr(status, "version_brand", "")
            
            # 直接解析 players 字符串（首选方式）
            players_online = 0
            players_max = 0

            if hasattr(status, 'players'):
                # 转为字符串形式，兼容原始格式
                players_str = str(getattr(status, 'players', ''))
                logger.info(f"Bedrock players 原始值: '{players_str}'")

                # 使用正则表达式解析 BedrockStatusPlayers(online=5, max=33) 格式
                match = re.search(r'online=(\d+).*?max=(\d+)', players_str)
                if match:
                    try:
                        players_online = int(match.group(1))
                        players_max = int(match.group(2))
                    except (ValueError, AttributeError) as e:
                        logger.warning(f"Bedrock 玩家数量解析失败: {e}")

            logger.info(f"Bedrock 玩家数量解析结果: online={players_online}, max={players_max}")
            
            # 处理 Bedrock MOTD（优先使用 map_name 字段，它包含真正的服务器名称）
            motd_text = ""
            
            # 首先尝试 map_name 字段（基岩版服务器的真实名称通常在这里）
            map_name = getattr(status, "map_name", "")
            if map_name and map_name.strip():
                motd_text = map_name.strip()
                logger.info(f"Bedrock MOTD 来源: map_name = '{motd_text}'")
            
            # 如果 map_name 为空，再尝试 motd 字段
            if not motd_text:
                motd_raw = getattr(status, "motd", None)
                if motd_raw:
                    if hasattr(motd_raw, 'raw'):
                        motd_text = getattr(motd_raw, 'raw', str(motd_raw))
                    elif hasattr(motd_raw, 'clean'):
                        motd_text = getattr(motd_raw, 'clean', str(motd_raw))
                    else:
                        motd_text = str(motd_raw)
                    logger.info(f"Bedrock MOTD 来源: motd.raw = '{motd_text}'")
            
            # 如果还是为空，尝试 description 字段
            if not motd_text:
                desc = getattr(status, "description", None)
                if desc:
                    if hasattr(desc, 'clean'):
                        motd_text = getattr(desc, 'clean', str(desc))
                    else:
                        motd_text = str(desc)
                    logger.info(f"Bedrock MOTD 来源: description = '{motd_text}'")
            
            # 最后尝试 level_name 字段
            if not motd_text:
                motd_text = getattr(status, "level_name", "")
                if motd_text:
                    logger.info(f"Bedrock MOTD 来源: level_name = '{motd_text}'")
            
            # 记录最终 MOTD 获取结果
            logger.info(f"Bedrock MOTD 最终解析: '{motd_text}'")

            return {
                "edition": "BE基岩版",
                "host": host,
                "port": port,
                "online": True,
                "latency_ms": round(getattr(status, "latency", 0)),
                "protocol": protocol,
                "version_name": version_name or "",
                "players_online": players_online,
                "players_max": players_max,
                "player_names": [],
                "motd": motd_text or "",
                "favicon_data_uri": None,
            }
        except asyncio.TimeoutError:
            logger.warning(f"Bedrock 探测超时: {host}:{port} (超时 {timeout_sec}s)")
            return None
        except ConnectionError as e:
            logger.warning(f"Bedrock 连接错误: {host}:{port} - {e}")
            return None
        except Exception as e:
            logger.warning(f"Bedrock 探测失败: {host}:{port} - {type(e).__name__}: {e}")
            return None

    def _load_font(self, size: int) -> ImageFont.ImageFont:
        """
        加载 Minecraft 字体
        
        Args:
            size: 字体大小
            
        Returns:
            字体对象
        """
        # 优先使用插件自带的 Minecraft 字体
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        minecraft_font = os.path.join(plugin_dir, "font", "Minecraft_AE.ttf")
        
        try:
            if os.path.exists(minecraft_font):
                return ImageFont.truetype(minecraft_font, size)
        except Exception as e:
            logger.info(f"加载 Minecraft 字体失败: {e}")
        
        # 备选方案：使用默认字体
        try:
            return ImageFont.load_default()
        except Exception:
            return ImageFont.load_default()

    async def _render_status_card(self, info: dict) -> Tuple[bytes, str]:
        """渲染服务器状态卡片"""
        # 准备画布
        width, height = 900, 300
        bg_color = (28, 30, 34)
        fg_primary = (235, 235, 235)
        fg_secondary = (170, 170, 170)
        accent = (88, 166, 255)

        image = Image.new("RGBA", (width, height), bg_color)
        draw = ImageDraw.Draw(image)

        # 字体
        font_title = self._load_font(28)
        font_body = self._load_font(20)
        font_small = self._load_font(16)

        padding = 20
        x = padding
        y = padding

        # 服务器图标处理
        icon_loaded = self._load_server_icon(image, info, x, y)
        x_text = x + 96 + 16 if icon_loaded else x

        # 渲染内容
        self._render_content(draw, info, x_text, y, font_title, font_body, font_small, 
                           fg_primary, fg_secondary, accent, width, padding)

        # 导出字节
        buf = BytesIO()
        image.save(buf, format="PNG", optimize=True)
        img_bytes = buf.getvalue()

        # 文本摘要（优化格式）
        motd = self._clean_motd_text(info.get("motd", "") or "")
        
        # 处理过长的 MOTD，限制显示长度
        if len(motd) > 100:
            motd = motd[:97] + "..."
        
        # 根据版本类型选择标题
        if info['edition'] == 'Java':
            title = "MC Java服务器状态查询"
        else:
            title = "MC 基岩版服务器状态查询"
        
        # 处理玩家示例列表
        player_info = f"{info['players_online']}/{info['players_max']}"
        if info.get('player_names'):
            sample_players = ", ".join(info['player_names'][:3])  # 只显示前3个玩家
            if len(info['player_names']) > 3:
                sample_players += f" 等{len(info['player_names'])}人"
            player_info += f" ({sample_players})"
        
        status_text = (
            f"{title}\n"
            f"✅️状态: 在线\n"
            f"📋描述: {motd}\n"
            f"💳协议版本: {info.get('protocol', '-') or '-'}\n"
            f"🧰游戏版本: {info.get('version_name', '-') or '-'}\n"
            f"📡延迟: {info['latency_ms']} ms\n"
            f"👧玩家在线: {player_info}"
        )

        return img_bytes, status_text

    def _load_server_icon(self, image: Image.Image, info: dict, x: int, y: int) -> bool:
        """加载服务器图标，返回是否成功"""
        # 尝试加载服务器 favicon
        if info.get("favicon_data_uri"):
            try:
                data_uri: str = info["favicon_data_uri"]
                if data_uri.startswith("data:"):
                    b64 = data_uri.split(",", 1)[1]
                else:
                    b64 = data_uri
                icon = Image.open(BytesIO(base64.b64decode(b64))).convert("RGBA")
                icon = icon.resize((96, 96))
                image.paste(icon, (x, y), icon)
                return True
            except Exception as e:
                logger.info(f"加载服务器 favicon 失败: {e}")
        
        # 如果没有 favicon，尝试加载默认 Minecraft logo
        try:
            # 尝试从网络加载默认 logo
            import requests
            
            default_logo_url = "https://patchwiki.biligame.com/images/mc/5/53/smk9nesqj6bkd5qyd718xxhocic6et0.png"
            response = requests.get(default_logo_url, timeout=10)
            if response.status_code == 200:
                default_icon = Image.open(BytesIO(response.content)).convert("RGBA")
                default_icon = default_icon.resize((96, 96))
                image.paste(default_icon, (x, y), default_icon)
                logger.info("使用默认 Minecraft logo")
                return True
        except Exception as e:
            logger.info(f"加载默认 logo 失败: {e}")
        
        return False

    def _render_content(self, draw: ImageDraw.ImageDraw, info: dict, x_text: int, y: int,
                      font_title: ImageFont.ImageFont, font_body: ImageFont.ImageFont, 
                      font_small: ImageFont.ImageFont, fg_primary: tuple, fg_secondary: tuple, 
                      accent: tuple, width: int, padding: int):
        """渲染内容区域"""
        # 标题行：host:port 与 Edition 徽标
        # 如果是通过 SRV 记录解析的，显示原始域名
        if info.get('srv_resolved') and info.get('original_domain'):
            title = f"{info['original_domain']}"
        else:
            title = f"{info['host']}:{info['port']}"
        draw.text((x_text, y), title, font=font_title, fill=fg_primary)

        edition_badge = f"{info['edition']}"
        badge_w, badge_h = draw.textbbox((0, 0), edition_badge, font=font_small)[2:]
        badge_x = x_text
        badge_y = y + 34
        # 徽标背景
        draw.rounded_rectangle([badge_x, badge_y, badge_x + badge_w + 12, badge_y + badge_h + 8], radius=6, fill=accent)
        draw.text((badge_x + 6, badge_y + 4), edition_badge, font=font_small, fill=(255, 255, 255))

        # 第二行：延迟 / 协议 / 版本
        y_info = badge_y + badge_h + 20
        line2 = f"延迟: {info['latency_ms']} ms    协议: {info.get('protocol', '-') or '-'}    版本: {info.get('version_name', '-') or '-'}"
        draw.text((x_text, y_info), line2, font=font_body, fill=fg_secondary)

        # 第三行：在线人数
        y_players = y_info + 28
        players_line = f"在线: {info['players_online']} / {info['players_max']}"
        draw.text((x_text, y_players), players_line, font=font_body, fill=fg_secondary)

        # 玩家示例列表（Java 有 sample）
        if info.get("player_names"):
            sample_text = ", ".join(info["player_names"][:10])
            draw.text((x_text, y_players + 26), f"在线玩家: {sample_text}", font=font_small, fill=fg_secondary)

        # MOTD 描述（多行，先清洗颜色码与换行）
        motd = self._clean_motd_text(info.get("motd", "") or "")
        y_motd = y_players + 60
        max_width = width - x_text - padding
        for line in self._wrap_text(draw, motd, font_body, max_width):
            draw.text((x_text, y_motd), line, font=font_body, fill=fg_primary)
            y_motd += 26

    def _wrap_text(self, draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
        """
        按指定宽度折行文本
        
        Args:
            draw: PIL 绘图对象
            text: 要折行的文本
            font: 字体对象
            max_width: 最大宽度
            
        Returns:
            折行后的文本列表
        """
        if not text:
            return []
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        result_lines: List[str] = []
        for paragraph in text.split("\n"):
            if paragraph == "":
                # 保留空行
                result_lines.append("")
                continue
            current_line = ""
            for ch in paragraph:
                test_line = current_line + ch
                # 仅测量单行文本宽度，避免包含换行符
                if draw.textlength(test_line, font=font) <= max_width:
                    current_line = test_line
                else:
                    if current_line:
                        result_lines.append(current_line)
                    current_line = ch
            if current_line:
                result_lines.append(current_line)
        return result_lines

    def _clean_motd_text(self, text) -> str:
        """
        清理 MOTD 文本，去除 Minecraft 颜色码
        
        Args:
            text: 原始 MOTD 文本（可能是字符串或 Motd 对象）
            
        Returns:
            清理后的文本
        """
        if not text:
            return ""
        
        # 处理 mcstatus 返回的 Motd 对象
        if hasattr(text, 'clean'):
            # 如果是 Motd 对象，使用 clean 属性
            text = getattr(text, 'clean', str(text))
        elif hasattr(text, 'raw'):
            # 如果有 raw 属性，使用 raw 数据
            text = getattr(text, 'raw', str(text))
        elif not isinstance(text, str):
            # 其他情况直接转为字符串
            text = str(text)
        
        # 统一换行
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # 去除 Minecraft 颜色码（例如 §a、§l、§x§R§R§G§G§B§B 等，按配对清理）
        try:
            return re.sub(r"§.", "", text)
        except Exception:
            return text

    def _save_temp_image(self, img_bytes: bytes) -> str:
        """保存临时图片文件"""
        try:
            with tempfile.NamedTemporaryFile(prefix="motd_", suffix=".png", delete=False) as tmp:
                tmp.write(img_bytes)
                tmp.flush()
                return tmp.name
        except Exception as e:
            logger.error(f"保存临时图片失败: {e}")
            raise

    async def _cleanup_file(self, path: str, delay_sec: float = 60.0):
        """异步清理临时文件"""
        try:
            await asyncio.sleep(delay_sec)
            if os.path.exists(path):
                os.remove(path)
                logger.info(f"临时文件已清理: {os.path.basename(path)}")
        except Exception as e:
            logger.warning(f"临时文件清理失败 {os.path.basename(path)}: {e}")
