from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
import astrbot.api.message_components as Comp
from astrbot.api import logger

from json import loads
import asyncio
import re

from httpx import AsyncClient
import validators


@register("astrbot_minecraft_motd", "初然", "Minecraft 服务器 MOTD 状态图", "1.0.1")
class MinecraftMOTDPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("motd")
    async def motd_command(self, event: AstrMessageEvent, addr: str = None):

        if addr is None:
            usage = (
                "用法:\n"
                "/motd <server_ip>[:<port>]\n"
                "示例:\n"
                "/motd play.example.com:25565\n"
                "port 可省略，默认 25565（Java 版）"
            )
            yield event.plain_result(usage)
            return

        match = re.match(r"^([\w\.-]+)(?::(\d+))?$", addr)
        if not match:
            yield event.plain_result("参数格式错误，请使用 /motd <server_ip>[:<port>]")
            return

        ip = match.group(1)
        port = int(match.group(2)) if match.group(2) else 25565

        # 对输入的ip做预检查
        if (not validators.ip_address.ipv4(ip, cidr=False) and
                not validators.ip_address.ipv6(ip, cidr=False) and
                not validators.domain(ip, consider_tld=False)):
            logger.info(f"预检查{ip}无效")
            yield event.plain_result("服务器地址无效")
            return

        je_base_url = "https://api.mcstatus.io/v2/status/java/"
        be_base_url = "https://api.mcstatus.io/v2/status/bedrock/"
        je_img_base_url = "https://api.mcstatus.io/v2/widget/java/"
        be_img_base_url = "https://api.mcstatus.io/v2/widget/bedrock/"

        async with AsyncClient(timeout=10) as client:
            be_info, je_info = await asyncio.gather(client.get(be_base_url + ip), client.get(je_base_url + ip))

            be_info = be_info.text
            je_info = je_info.text
        if be_info == "Invalid address value":  # 这里如果地址无效je和be的接口都会返回Invalid address value，故只判断be
            yield event.plain_result("服务器地址无效")
            return
        be_info = loads(be_info)
        je_info = loads(je_info)

        # 组装图片 URL
        # dark=true, rounded=true, transparent=false, timeout=5 默认参数
        if je_info["online"]:
            img_url = f"{je_img_base_url}{ip}:{port}?dark=true&rounded=true&transparent=false&timeout=5"
        elif be_info["online"]:
            img_url = f"{be_img_base_url}{ip}:{port}?dark=true&rounded=true&transparent=false&timeout=5"
        else:
            yield event.plain_result("当前服务器不在线，或者当前服务器信息输入错误，请检查当前服务器以及端口是否正确，随后重新发送")
            return

        logger.info(f"发送 Minecraft MOTD 图片: {img_url}")

        chain = [
            Comp.Image(img_url),
        ]
        yield event.chain_result(chain)
        return

    async def initialize(self):
        logger.info("MinecraftMOTDPlugin 已初始化")

    async def terminate(self):
        logger.info("MinecraftMOTDPlugin 已停止")
