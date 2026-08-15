"""
渠道类型枚举 — One API 51 种渠道类型完整映射

映射源: One API model/channeltype/channeltype.go
每个渠道类型有对应的 base_url 默认值和 adapter_type 标识。

映射规则:
- 原生 OpenAI 兼容: 直接使用 openai SDK（adapter_type="openai"）
- 私有 API: 需要适配器转换（adapter_type="custom"）
- 开源框架: 本地部署渠道（adapter_type="local"）
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


@dataclass(frozen=True)
class ChannelTypeInfo:
    """渠道类型详细信息"""
    value: int
    name: str
    display_name: str
    base_url: str
    adapter_type: str  # "openai" | "custom" | "local"


class ChannelType(IntEnum):
    """
    One API 51 种渠道类型 → DDW 映射

    映射规则:
    - 原生 OpenAI 兼容: 直接使用 openai SDK
    - 私有 API: 需要适配器转换
    - 开源框架: 本地部署渠道
    """
    # ── 云端 LLM（OpenAI 兼容）──
    OPENAI = 1                    # OpenAI GPT 系列
    AZURE = 3                     # Azure OpenAI
    ANTHROPIC = 8                 # Claude 系列
    BAIDU = 14                    # 百度文心一言
    ZHIPU = 15                    # 智谱 GLM
    DEEPSEEK = 24                 # DeepSeek V4 Pro
    MINIMAX = 25                  # MiniMax M3
    MISTRAL = 28                  # Mistral AI
    GROQ = 29                     # Groq
    TOGETHER = 30                 # Together AI
    OPENROUTER = 31               # OpenRouter
    DASHSCOPE = 42                # 阿里通义千问
    VOLCENGINE = 43               # 字节豆包
    SILICONFLOW = 48              # 硅基流动

    # ── 国内云厂商 ──
    TENCENT = 23                  # 腾讯混元
    HUNYUAN = 44                  # 混元独立
    XUNFEI = 16                   # 讯飞星火
    BAICHUAN = 26                 # 百川
    SENSETIME = 34                # 商汤
    YI = 38                       # 零一万物

    # ── 海外厂商 ──
    AI21 = 2                      # AI21 Labs
    COHERE = 4                    # Cohere
    PERPLEXITY = 5                # Perplexity
    GEMINI = 6                    # Google Gemini
    CLAUDE = 8                    # Anthropic Claude (alias)
    BAI_LLM = 9                   # 百川 (旧)
    TENCENT_HUNYUAN = 12          # 腾讯混元 (旧)
    JIEBAO = 17                   # 介宝
    UNICORN = 18                  # 独角兽
    MINIMAX_2 = 19                # MiniMax (旧)
    CLOVA = 20                    # Naver CLOVA
    GROQ_2 = 21                   # Groq (旧)
    OPENAI_SYNTAX = 22            # OpenAI 语法
    BAIDU_2 = 27                  # 百度 (旧)
    MISTRAL_2 = 32                # Mistral (旧)
    AZURE_2 = 33                  # Azure (旧)
    DEEPINFRA = 35                # DeepInfra
    NEMOTRON_ULTRA = 36           # NVIDIA Nemotron
    NVIDIA = 37                   # NVIDIA
    ZERO_ONE = 39                 # 零一万物
    BEDROCK = 40                  # AWS Bedrock
    CLOUDFLARE = 41               # Cloudflare Workers AI
    PPIO = 49                     # PPIO
    CHINA_MOBIL = 50              # 中国移动
    VOLCENGINE_2 = 51             # 火山引擎 (旧)
    XAI = 52                      # xAI (Grok)
    SILI = 53                     # 硅基流动 (旧)
    ZENMUSIC = 54                 # ZenMusic
    MIMO = 55                     # 小米 MiMo
    CHUTE = 56                    # Chute

    # ── 开源框架 ──
    OLLAMA = 11                   # Ollama 本地
    VLLM = 45                     # vLLM
    LLAMACPP = 46                 # llama.cpp
    OPENCODE = 47                 # OpenCode

    # ── 自定义 ──
    CUSTOM = 100                  # 自定义渠道


# ── 渠道类型元数据注册表 ──
# 每个类型对应 base_url 默认值和 adapter_type
CHANNEL_TYPE_REGISTRY: dict[int, ChannelTypeInfo] = {
    # 云端 LLM（OpenAI 兼容）
    ChannelType.OPENAI: ChannelTypeInfo(
        value=1, name="openai", display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        adapter_type="openai"
    ),
    ChannelType.AZURE: ChannelTypeInfo(
        value=3, name="azure", display_name="Azure OpenAI",
        base_url="https://your-resource.openai.azure.com",
        adapter_type="openai"
    ),
    ChannelType.ANTHROPIC: ChannelTypeInfo(
        value=8, name="anthropic", display_name="Anthropic",
        base_url="https://api.anthropic.com",
        adapter_type="custom"
    ),
    ChannelType.BAIDU: ChannelTypeInfo(
        value=14, name="baidu", display_name="百度文心一言",
        base_url="https://aip.baidubce.com",
        adapter_type="custom"
    ),
    ChannelType.ZHIPU: ChannelTypeInfo(
        value=15, name="zhipu", display_name="智谱 GLM",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        adapter_type="openai"
    ),
    ChannelType.DEEPSEEK: ChannelTypeInfo(
        value=24, name="deepseek", display_name="DeepSeek",
        base_url="https://api.deepseek.com",
        adapter_type="openai"
    ),
    ChannelType.MINIMAX: ChannelTypeInfo(
        value=25, name="minimax", display_name="MiniMax",
        base_url="https://api.minimax.chat",
        adapter_type="openai"
    ),
    ChannelType.MISTRAL: ChannelTypeInfo(
        value=28, name="mistral", display_name="Mistral AI",
        base_url="https://api.mistral.ai/v1",
        adapter_type="openai"
    ),
    ChannelType.GROQ: ChannelTypeInfo(
        value=29, name="groq", display_name="Groq",
        base_url="https://api.groq.com/openai/v1",
        adapter_type="openai"
    ),
    ChannelType.TOGETHER: ChannelTypeInfo(
        value=30, name="together", display_name="Together AI",
        base_url="https://api.together.xyz/v1",
        adapter_type="openai"
    ),
    ChannelType.OPENROUTER: ChannelTypeInfo(
        value=31, name="openrouter", display_name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        adapter_type="openai"
    ),
    ChannelType.DASHSCOPE: ChannelTypeInfo(
        value=42, name="dashscope", display_name="阿里通义千问",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        adapter_type="openai"
    ),
    ChannelType.VOLCENGINE: ChannelTypeInfo(
        value=43, name="volcengine", display_name="字节豆包",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        adapter_type="openai"
    ),
    ChannelType.SILICONFLOW: ChannelTypeInfo(
        value=48, name="siliconflow", display_name="硅基流动",
        base_url="https://api.siliconflow.cn/v1",
        adapter_type="openai"
    ),

    # 国内云厂商
    ChannelType.TENCENT: ChannelTypeInfo(
        value=23, name="tencent", display_name="腾讯混元",
        base_url="https://hunyuan.tencentcloudapi.com",
        adapter_type="custom"
    ),
    ChannelType.HUNYUAN: ChannelTypeInfo(
        value=44, name="hunyuan", display_name="混元",
        base_url="https://api.hunyuan.cloud.tencent.com/v1",
        adapter_type="openai"
    ),
    ChannelType.XUNFEI: ChannelTypeInfo(
        value=16, name="xunfei", display_name="讯飞星火",
        base_url="https://spark-api-open.xf-yun.com/v1",
        adapter_type="openai"
    ),
    ChannelType.BAICHUAN: ChannelTypeInfo(
        value=26, name="baichuan", display_name="百川",
        base_url="https://api.baichuan-ai.com/v1",
        adapter_type="openai"
    ),
    ChannelType.SENSETIME: ChannelTypeInfo(
        value=34, name="sensetime", display_name="商汤",
        base_url="https://api.sensetime.com/v1",
        adapter_type="openai"
    ),
    ChannelType.YI: ChannelTypeInfo(
        value=38, name="yi", display_name="零一万物",
        base_url="https://api.lingyiwanwu.com/v1",
        adapter_type="openai"
    ),

    # 海外厂商
    ChannelType.AI21: ChannelTypeInfo(
        value=2, name="ai21", display_name="AI21 Labs",
        base_url="https://api.ai21.com/v1",
        adapter_type="openai"
    ),
    ChannelType.COHERE: ChannelTypeInfo(
        value=4, name="cohere", display_name="Cohere",
        base_url="https://api.cohere.com/v2",
        adapter_type="custom"
    ),
    ChannelType.PERPLEXITY: ChannelTypeInfo(
        value=5, name="perplexity", display_name="Perplexity",
        base_url="https://api.perplexity.ai",
        adapter_type="openai"
    ),
    ChannelType.GEMINI: ChannelTypeInfo(
        value=6, name="gemini", display_name="Google Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        adapter_type="custom"
    ),
    ChannelType.DEEPINFRA: ChannelTypeInfo(
        value=35, name="deepinfra", display_name="DeepInfra",
        base_url="https://api.deepinfra.com/v1/openai",
        adapter_type="openai"
    ),
    ChannelType.BEDROCK: ChannelTypeInfo(
        value=40, name="bedrock", display_name="AWS Bedrock",
        base_url="https://bedrock-runtime.us-east-1.amazonaws.com",
        adapter_type="custom"
    ),
    ChannelType.CLOUDFLARE: ChannelTypeInfo(
        value=41, name="cloudflare", display_name="Cloudflare Workers AI",
        base_url="https://api.cloudflare.com/client/v4/accounts",
        adapter_type="custom"
    ),
    ChannelType.XAI: ChannelTypeInfo(
        value=52, name="xai", display_name="xAI (Grok)",
        base_url="https://api.x.ai/v1",
        adapter_type="openai"
    ),
    ChannelType.PPIO: ChannelTypeInfo(
        value=49, name="ppio", display_name="PPIO",
        base_url="https://api.ppio.com/v1",
        adapter_type="openai"
    ),
    ChannelType.MIMO: ChannelTypeInfo(
        value=55, name="mimo", display_name="小米 MiMo",
        base_url="https://api.mimo.ai/v1",
        adapter_type="openai"
    ),
    ChannelType.CHUTE: ChannelTypeInfo(
        value=56, name="chute", display_name="Chute",
        base_url="https://api.chute.ai/v1",
        adapter_type="openai"
    ),

    # 开源框架
    ChannelType.OLLAMA: ChannelTypeInfo(
        value=11, name="ollama", display_name="Ollama",
        base_url="http://localhost:11434",
        adapter_type="local"
    ),
    ChannelType.VLLM: ChannelTypeInfo(
        value=45, name="vllm", display_name="vLLM",
        base_url="http://localhost:8000/v1",
        adapter_type="openai"
    ),
    ChannelType.LLAMACPP: ChannelTypeInfo(
        value=46, name="llamacpp", display_name="llama.cpp",
        base_url="http://localhost:8080/v1",
        adapter_type="openai"
    ),
    ChannelType.OPENCODE: ChannelTypeInfo(
        value=47, name="opencode", display_name="OpenCode",
        base_url="http://localhost:3000/v1",
        adapter_type="openai"
    ),

    # 自定义
    ChannelType.CUSTOM: ChannelTypeInfo(
        value=100, name="custom", display_name="自定义",
        base_url="",
        adapter_type="openai"
    ),
}


def get_channel_type_info(channel_type: int) -> ChannelTypeInfo | None:
    """根据渠道类型值获取元数据"""
    return CHANNEL_TYPE_REGISTRY.get(channel_type)


def get_default_base_url(channel_type: int) -> str:
    """根据渠道类型获取默认 base_url"""
    info = CHANNEL_TYPE_REGISTRY.get(channel_type)
    return info.base_url if info else ""


def get_adapter_type(channel_type: int) -> str:
    """根据渠道类型获取适配器类型"""
    info = CHANNEL_TYPE_REGISTRY.get(channel_type)
    return info.adapter_type if info else "openai"


def list_all_channel_types() -> list[ChannelTypeInfo]:
    """列出所有已注册的渠道类型"""
    return list(CHANNEL_TYPE_REGISTRY.values())
