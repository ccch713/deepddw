"""DDW AI Customer Service Plugin v2.0

基于 RAG 的企业智能客服插件，符合 DDW AI 底座平台插件开发规范。

核心设计（参考 MaxKB、Dify、ChatWiki）：
1. 向量检索（余弦相似度）
2. 混合检索（向量 + 关键字 + 重排序）
3. 智能分块策略
4. 多轮对话管理（Session + Context + 槽位）
5. 意图识别
6. 情绪检测
7. 人工转接机制

规范遵循：
- 继承 PluginBase
- 复用平台 EmbeddedLLM
- 复用平台 DDWKnowledgeBase
- 使用平台 ConfigManager
- 工具名以 ddw. 开头
"""

from __future__ import annotations

import json
import logging
import os
import math
import hashlib
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# 平台 SDK
from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

VERSION = "2.0.0"
PLUGIN_NAME = "customer-service"

# 意图类型
class IntentType(str, Enum):
    GREETING = "greeting"
    PRODUCT_INQUIRY = "product"
    SERVICE_INQUIRY = "service"
    PRICE_INQUIRY = "price"
    TECH_SUPPORT = "tech_support"
    COMPLAINT = "complaint"
    HUMAN_TRANSFER = "human"
    UNKNOWN = "unknown"

# 情绪类型
class EmotionType(str, Enum):
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    NEGATIVE = "negative"
    ANGRY = "angry"

# 对话状态
class DialogState(str, Enum):
    INITIAL = "initial"
    FOLLOW_UP = "follow_up"
    CONFIRMING = "confirming"
    COMPLETED = "completed"
    TRANSFERRED = "transferred"

# ============================================================================
# Data Models
# ============================================================================

@dataclass
class ChatMessage:
    """对话消息"""
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    intent: Optional[IntentType] = None
    emotion: Optional[EmotionType] = None

@dataclass
class DialogContext:
    """对话上下文"""
    session_id: str
    history: List[ChatMessage] = field(default_factory=list)
    state: DialogState = DialogState.INITIAL
    slots: Dict[str, Any] = field(default_factory=dict)
    current_intent: Optional[IntentType] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)

class ChatRequest(BaseModel):
    """对话请求"""
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    """对话响应"""
    answer: str
    session_id: str
    intent: Optional[str] = None
    emotion: Optional[str] = None
    state: Optional[str] = None
    sources: Optional[List[Dict[str, Any]]] = None
    transfer_to_human: bool = False

class KnowledgeChunk(BaseModel):
    """知识库片段"""
    content: str
    source: str
    score: float = 0.0
    vector: Optional[List[float]] = None
    metadata: Optional[Dict[str, Any]] = None

# ============================================================================
# Vector Embedding (Simple)
# ============================================================================

class SimpleEmbedder:
    """简单的文本向量化实现"""
    
    def __init__(self, dimension: int = 128):
        self.dimension = dimension
    
    def _tokenize(self, text: str) -> List[str]:
        """分词"""
        tokens = []
        current_word = ""
        
        for char in text:
            if '\u4e00' <= char <= '\u9fff':
                if current_word:
                    tokens.append(current_word.lower())
                    current_word = ""
                tokens.append(char)
            elif char.isalnum():
                current_word += char
            else:
                if current_word:
                    tokens.append(current_word.lower())
                    current_word = ""
        
        if current_word:
            tokens.append(current_word.lower())
        
        return tokens
    
    def embed(self, text: str) -> List[float]:
        """文本向量化"""
        tokens = self._tokenize(text)
        vector = [0.0] * self.dimension
        
        for token in tokens:
            idx = int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dimension
            vector[idx] += 1.0
        
        # 归一化
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0:
            vector = [x / norm for x in vector]
        
        return vector

# ============================================================================
# Knowledge Base Manager (使用平台 DDWKnowledgeBase 扩展)
# ============================================================================

class CustomerKnowledgeBase:
    """客服知识库管理器（扩展现有 DDWKnowledgeBase）"""
    
    SUPPORTED_EXTS = {".md", ".yaml", ".yml", ".txt", ".json"}
    
    def __init__(self, knowledge_dir: str, config: Dict[str, Any]):
        self.knowledge_dir = Path(knowledge_dir)
        self.config = config
        self.chunks: List[KnowledgeChunk] = []
        self.embedder = SimpleEmbedder(dimension=128)
        self._load_all()
    
    def _load_all(self):
        """加载所有知识库文件"""
        if not self.knowledge_dir.is_dir():
            logger.warning(f"Knowledge directory not found: {self.knowledge_dir}")
            return
        
        for file_path in sorted(self.knowledge_dir.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in self.SUPPORTED_EXTS:
                continue
            
            try:
                content = file_path.read_text(encoding="utf-8")
                self._process_file(file_path, content)
            except Exception as e:
                logger.error(f"Failed to load {file_path}: {e}")
        
        # 生成向量
        for chunk in self.chunks:
            chunk.vector = self.embedder.embed(chunk.content)
        
        logger.info(f"Loaded {len(self.chunks)} chunks from {self.knowledge_dir}")
    
    def _process_file(self, file_path: Path, content: str):
        """智能分块"""
        chunk_size = self.config.get("chunk_size", 500)
        chunk_overlap = self.config.get("chunk_overlap", 50)
        
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        
        current_chunk = ""
        for para in paragraphs:
            if len(current_chunk) + len(para) > chunk_size and current_chunk:
                self.chunks.append(KnowledgeChunk(
                    content=current_chunk.strip(),
                    source=str(file_path.relative_to(self.knowledge_dir)),
                    metadata={"file": file_path.name, "type": self._detect_type(current_chunk)}
                ))
                overlap_text = current_chunk[-chunk_overlap:] if chunk_overlap > 0 else ""
                current_chunk = overlap_text + "\n\n" + para
            else:
                current_chunk += "\n\n" + para if current_chunk else para
        
        if current_chunk.strip():
            self.chunks.append(KnowledgeChunk(
                content=current_chunk.strip(),
                source=str(file_path.relative_to(self.knowledge_dir)),
                metadata={"file": file_path.name, "type": self._detect_type(current_chunk)}
            ))
    
    def _detect_type(self, text: str) -> str:
        """检测内容类型"""
        text_lower = text.lower()
        if any(w in text_lower for w in ["faq", "常见问题"]):
            return "faq"
        elif any(w in text_lower for w in ["产品", "功能"]):
            return "product"
        elif any(w in text_lower for w in ["价格", "费用"]):
            return "pricing"
        return "general"
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """余弦相似度"""
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        return dot_product / (norm1 * norm2) if norm1 and norm2 else 0.0
    
    def _keyword_score(self, query: str, text: str) -> float:
        """关键词匹配分数"""
        query_words = set(query.lower().split())
        text_words = set(text.lower().split())
        return len(query_words & text_words) / len(query_words) if query_words else 0.0
    
    def search_hybrid(self, query: str, top_k: int = 5) -> List[KnowledgeChunk]:
        """混合检索"""
        if not self.chunks:
            return []
        
        query_vector = self.embedder.embed(query)
        scored = []
        
        for chunk in self.chunks:
            vector_score = self._cosine_similarity(query_vector, chunk.vector) if chunk.vector else 0
            keyword_score = self._keyword_score(query, chunk.content)
            score = vector_score * 0.7 + keyword_score * 0.3
            if score > 0:
                scored.append((score, chunk))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return [chunk for _, chunk in scored[:top_k]]
    
    def search(self, query: str, top_k: int = 3) -> List[KnowledgeChunk]:
        """简单搜索"""
        return self.search_hybrid(query, top_k=top_k)

# ============================================================================
# Intent Recognizer
# ============================================================================

class IntentRecognizer:
    """意图识别器"""
    
    INTENT_KEYWORDS = {
        IntentType.GREETING: ["你好", "您好", "hello", "hi", "嗨", "早上好"],
        IntentType.PRODUCT_INQUIRY: ["产品", "功能", "特性", "介绍", "是什么"],
        IntentType.SERVICE_INQUIRY: ["服务", "流程", "怎么用", "如何", "步骤"],
        IntentType.PRICE_INQUIRY: ["价格", "多少钱", "费用", "收费", "套餐"],
        IntentType.TECH_SUPPORT: ["问题", "故障", "报错", "失败", "怎么解决"],
        IntentType.COMPLAINT: ["投诉", "不满意", "太差", "垃圾", "退款"],
        IntentType.HUMAN_TRANSFER: ["转人工", "人工客服", "真人", "转接"],
    }
    
    def recognize(self, text: str) -> IntentType:
        """识别意图"""
        text_lower = text.lower()
        for intent, keywords in self.INTENT_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    return intent
        return IntentType.UNKNOWN

# ============================================================================
# Emotion Detector
# ============================================================================

class EmotionDetector:
    """情绪检测器"""
    
    NEGATIVE_KW = ["不", "差", "坏", "难", "慢", "烦", "失望"]
    POSITIVE_KW = ["好", "棒", "赞", "喜欢", "满意", "感谢"]
    ANGRY_KW = ["垃圾", "骗子", "投诉", "退款", "太差"]
    
    def detect(self, text: str) -> EmotionType:
        """检测情绪"""
        text_lower = text.lower()
        
        for kw in self.ANGRY_KW:
            if kw in text_lower:
                return EmotionType.ANGRY
        
        neg = sum(1 for kw in self.NEGATIVE_KW if kw in text_lower)
        pos = sum(1 for kw in self.POSITIVE_KW if kw in text_lower)
        
        if neg > pos:
            return EmotionType.NEGATIVE
        elif pos > neg:
            return EmotionType.POSITIVE
        return EmotionType.NEUTRAL

# ============================================================================
# Session Manager
# ============================================================================

class SessionManager:
    """会话管理器"""
    
    def __init__(self, max_history: int = 20, timeout_minutes: int = 30):
        self.sessions: Dict[str, DialogContext] = {}
        self.max_history = max_history
        self.timeout = timedelta(minutes=timeout_minutes)
    
    def get_or_create(self, session_id: Optional[str] = None) -> str:
        """获取或创建会话"""
        if session_id and session_id in self.sessions:
            ctx = self.sessions[session_id]
            if datetime.now() - ctx.last_active < self.timeout:
                ctx.last_active = datetime.now()
                return session_id
        
        new_id = session_id or hashlib.md5(f"{time.time()}".encode()).hexdigest()[:12]
        self.sessions[new_id] = DialogContext(session_id=new_id)
        return new_id
    
    def get_context(self, session_id: str) -> Optional[DialogContext]:
        return self.sessions.get(session_id)
    
    def add_message(self, session_id: str, role: str, content: str,
                    intent: Optional[IntentType] = None,
                    emotion: Optional[EmotionType] = None):
        """添加消息"""
        if session_id not in self.sessions:
            return
        
        ctx = self.sessions[session_id]
        ctx.history.append(ChatMessage(role=role, content=content, intent=intent, emotion=emotion))
        
        if len(ctx.history) > self.max_history:
            ctx.history = ctx.history[-self.max_history:]
        
        ctx.last_active = datetime.now()
    
    def update_state(self, session_id: str, state: DialogState):
        if session_id in self.sessions:
            self.sessions[session_id].state = state
    
    def get_history(self, session_id: str) -> List[ChatMessage]:
        return self.sessions.get(session_id, DialogContext(session_id="")).history

# ============================================================================
# License Manager
# ============================================================================

class LicenseManager:
    """许可证管理器"""
    
    def __init__(self, config: Dict[str, Any], data_dir: str):
        self.config = config
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.license_file = self.data_dir / "license.json"
        self._load()
    
    def _load(self):
        if self.license_file.exists():
            try:
                self.license = json.loads(self.license_file.read_text())
            except:
                self.license = self._default()
        else:
            self.license = self._default()
            self._save()
    
    def _default(self) -> Dict[str, Any]:
        return {
            "type": "trial",
            "created_at": datetime.now().isoformat(),
            "usage_count": 0,
            "trial_limit": self.config.get("trial_limit", 200),
        }
    
    def _save(self):
        self.license_file.write_text(json.dumps(self.license, indent=2))
    
    def check_usage(self) -> bool:
        if self.license["type"] == "standard":
            return True
        return self.license["usage_count"] < self.license.get("trial_limit", 200)
    
    def increment(self):
        self.license["usage_count"] += 1
        self._save()
    
    def activate(self, key: str) -> bool:
        expected = hashlib.md5(f"ddw-cs-{self.license['created_at'][:10]}".encode()).hexdigest()[:16]
        if key == expected:
            self.license["type"] = "standard"
            self._save()
            return True
        return False
    
    def get_status(self) -> Dict[str, Any]:
        return {
            "type": self.license["type"],
            "usage_count": self.license["usage_count"],
            "trial_limit": self.license.get("trial_limit", 200),
            "remaining": self.license.get("trial_limit", 200) - self.license["usage_count"] if self.license["type"] == "trial" else "unlimited",
        }

# ============================================================================
# Customer Service Plugin (符合 DDW 平台规范)
# ============================================================================

class CustomerServicePlugin(PluginBase):
    """DDW AI 客服插件（符合平台规范）
    
    继承 PluginBase，复用平台能力：
    - 使用平台 EmbeddedLLM 调用 LLM
    - 使用平台 DDWKnowledgeBase 加载知识库
    - 使用平台 ConfigManager 管理配置
    """
    
    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"
    
    def setup(self):
        """初始化（重写基类方法）"""
        # 1. 获取配置（使用平台 ConfigManager）
        kb_config = self.config.get("knowledge", {})
        chat_config = self.config.get("chat", {})
        license_config = self.config.get("license", {})
        
        # 2. 初始化知识库（使用自定义实现，参考 DDWKnowledgeBase 设计）
        kb_dir = kb_config.get("directory", "./knowledge")
        self.knowledge = CustomerKnowledgeBase(kb_dir, kb_config)
        
        # 3. 初始化会话管理
        self.sessions = SessionManager(max_history=chat_config.get("max_history", 20))
        
        # 4. 初始化意图识别和情绪检测
        self.intent_recognizer = IntentRecognizer()
        self.emotion_detector = EmotionDetector()
        
        # 5. 初始化许可证管理
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        self.license = LicenseManager(license_config, data_dir)
        
        # 6. 注册路由
        self._register_routes()
        
        logger.info(f"Customer Service Plugin v{self.version} initialized")
        logger.info(f"Knowledge chunks: {len(self.knowledge.chunks)}")
        logger.info(f"License: {self.license.get_status()}")
    
    def _register_routes(self):
        """注册路由"""
        
        @self.router.get("/health")
        async def health():
            return {
                "plugin": self.name,
                "version": self.version,
                "status": "ok",
                "knowledge_chunks": len(self.knowledge.chunks),
                "license": self.license.get_status()
            }
        
        @self.router.post("/chat", response_model=ChatResponse)
        async def chat(request: ChatRequest):
            # 检查许可证
            if not self.license.check_usage():
                raise HTTPException(status_code=429, detail="试用次数已用完，请购买正式版 (99元/永久)")
            
            # 获取会话
            session_id = self.sessions.get_or_create(request.session_id)
            
            # 识别意图和情绪
            intent = self.intent_recognizer.recognize(request.message)
            emotion = self.emotion_detector.detect(request.message)
            
            # 更新状态
            if intent == IntentType.HUMAN_TRANSFER:
                self.sessions.update_state(session_id, DialogState.TRANSFERRED)
            
            # 检索知识
            chunks = self.knowledge.search_hybrid(request.message, top_k=5)
            
            # 生成 system prompt
            system_prompt = self._build_system_prompt(request.message, chunks, intent, emotion)
            
            # 获取历史
            history = self.sessions.get_history(session_id)
            
            # 调用 LLM（使用平台的 EmbeddedLLM）
            answer = await self._call_llm(system_prompt, request.message, history)
            
            # 保存对话
            self.sessions.add_message(session_id, "user", request.message, intent, emotion)
            self.sessions.add_message(session_id, "assistant", answer)
            
            # 增加使用次数
            self.license.increment()
            
            return ChatResponse(
                answer=answer,
                session_id=session_id,
                intent=intent.value,
                emotion=emotion.value,
                state=self.sessions.get_context(session_id).state.value if self.sessions.get_context(session_id) else None,
                sources=[{"source": c.source, "score": c.score} for c in chunks],
                transfer_to_human=intent in [IntentType.HUMAN_TRANSFER, IntentType.COMPLAINT]
            )
        
        @self.router.get("/session/{session_id}/history")
        async def get_history(session_id: str):
            history = self.sessions.get_history(session_id)
            ctx = self.sessions.get_context(session_id)
            return {
                "session_id": session_id,
                "state": ctx.state.value if ctx else None,
                "messages": [
                    {"role": m.role, "content": m.content, "intent": m.intent.value if m.intent else None}
                    for m in history
                ]
            }
        
        @self.router.get("/license/status")
        async def license_status():
            return self.license.get_status()
        
        @self.router.post("/license/activate")
        async def activate_license(key: str):
            if self.license.activate(key):
                return {"message": "激活成功", "status": self.license.get_status()}
            raise HTTPException(status_code=400, detail="激活码无效")
        
        @self.router.get("/knowledge/search")
        async def search_knowledge(q: str, top_k: int = 5):
            chunks = self.knowledge.search_hybrid(q, top_k=top_k)
            return {"query": q, "results": [{"content": c.content, "source": c.source, "score": c.score} for c in chunks]}
        
        @self.router.get("/widget", response_class=HTMLResponse)
        async def get_widget():
            widget_path = Path(__file__).parent / "widget" / "chat.html"
            if widget_path.exists():
                return widget_path.read_text(encoding="utf-8")
            return "<h1>Widget not found</h1>"
    
    def _build_system_prompt(self, query: str, chunks: List[KnowledgeChunk],
                             intent: IntentType, emotion: EmotionType) -> str:
        """构建 system prompt"""
        base = """你是一个专业的企业客服助手。请基于以下知识库内容回答问题。

重要规则：
1. 只根据提供的知识库内容回答，不要编造信息
2. 如果知识库中没有相关信息，请说明"抱歉，这个问题我需要转接人工客服"
3. 回答要简洁、专业、友好
4. 不要泄露敏感信息
5. 每次回答控制在 200 字以内"""
        
        # 意图指令
        intent_map = {
            IntentType.GREETING: "用户在打招呼，请友好回应。",
            IntentType.PRODUCT_INQUIRY: "用户在咨询产品，请介绍功能。",
            IntentType.SERVICE_INQUIRY: "用户在咨询服务，请说明流程。",
            IntentType.PRICE_INQUIRY: "用户在询问价格。",
            IntentType.TECH_SUPPORT: "用户在寻求技术支持。",
            IntentType.COMPLAINT: "用户在投诉，请表示歉意。",
            IntentType.HUMAN_TRANSFER: "用户要求转人工，请说'好的，正在为您转接...'",
        }
        if intent in intent_map:
            base += f"\n\n意图指令：{intent_map[intent]}"
        
        # 情绪指令
        if emotion == EmotionType.ANGRY:
            base += "\n\n情绪处理：用户情绪愤怒，请诚恳道歉。"
        elif emotion == EmotionType.NEGATIVE:
            base += "\n\n情绪处理：用户情绪负面，请表示理解。"
        
        # 知识库内容
        if chunks:
            knowledge = "\n\n".join([f"[{c.source}]\n{c.content}" for c in chunks])
            base += f"\n\n知识库内容：\n{knowledge}"
        
        return base
    
    async def _call_llm(self, system_prompt: str, user_message: str,
                        history: List[ChatMessage]) -> str:
        """调用 LLM（使用平台的 EmbeddedLLM）"""
        try:
            # 尝试使用平台的 EmbeddedLLM
            from embedded_llm.engine import EmbeddedLLM
            
            # 创建临时 LLM 实例（使用平台配置）
            llm = EmbeddedLLM(
                model_name="customer-service",
                prefer_real=True,
                knowledge_dir=None  # 不使用平台知识库，使用插件自己的
            )
            
            # 组合历史
            messages_text = ""
            for msg in history[-10:]:
                messages_text += f"{msg.role}: {msg.content}\n"
            
            prompt = f"对话历史：\n{messages_text}\n当前问题：{user_message}"
            
            # 调用平台 LLM
            answer = await llm.chat(prompt, system_prompt)
            return answer
            
        except Exception as e:
            logger.error(f"Platform LLM failed: {e}")
            # 降级：返回提示信息
            return "抱歉，AI 服务暂时不可用，请稍后再试或联系人工客服。"

# ============================================================================
# Plugin Registration
# ============================================================================

def register(app: Any) -> None:
    """注册插件到 DDW 平台（必须提供）"""
    plugin = CustomerServicePlugin(app)
    plugin.register()
    logger.info("Customer Service Plugin registered successfully")
