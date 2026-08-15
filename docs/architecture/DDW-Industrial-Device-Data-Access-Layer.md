# DDW 工业设备数据接入层 — 架构设计文档

> **插件名**: `ddw-industrial-data-access`
> **版本**: v1.0.0
> **日期**: 2026-07-14
> **定位**: DDW AI Hub 的工业设备数据统一接入插件
> **技术约束**: Python + FastAPI · 单机部署(ECS 8GB / Mac mini M4) · 无重型依赖

---

## 一、设计背景与目标

### 1.1 业务场景

传统制造企业（CNC加工、光通信模块、食品医药等）的IT系统存在严重的**数据孤岛**问题：

- 生产设备用 Modbus/OPC-UA 采集数据
- IoT传感器走 MQTT 协议
- ERP/MES 系统用 REST API 或直连数据库
- 质检数据以 Excel/CSV 形式流转
- 各种数据格式不统一、采集频率各异、缺少标准化

**核心痛点**：企业要实现 AI 质量预测、设备预测性维护、智能排产等场景，首先需要打通设备数据层。但传统方案（Kafka + Flink + 时序数据库集群）对中小企业来说成本过高、运维困难。

### 1.2 设计目标

| 维度 | 目标 |
|:-----|:-----|
| **协议覆盖** | Modbus TCP/RTU、OPC-UA、MQTT、HTTP/REST、CSV/Excel、JDBC 六大协议 |
| **采集能力** | 秒级到小时级可配频率，断线重连 + 本地缓存兜底 |
| **轻量部署** | 单机 8GB RAM 即可运行，无需 Kafka/Flink/ES 集群 |
| **AI 增强** | LLM 辅助异常检测、数据清洗规则推荐、设备画像生成 |
| **DDW 生态** | 作为 DDW 插件接入平台，继承 PluginBase，走 DDW 事件总线 |

### 1.3 参考架构选型

| 参考项目 | Star | 核心借鉴点 | 许可证 |
|:---------|:----:|:-----------|:-------|
| Telegraf (influxdata) | 17707 | Input→Processor→Output 管线模型、插件化采集 | MIT |
| ThingsBoard Gateway | 2155 | 协议转换器、设备画像、边缘预处理 | Apache 2.0 |
| DG-IoT | 4826 | 物模型（Attribute/Event/Service）、行业模板 | Apache 2.0 |
| EMQX | 16506 | MQTT Broker、协议网关、高并发消息路由 | Apache 2.0 |

**许可证策略**：四大参考项目均为 MIT/Apache 2.0 许可证，**允许商业二次开发**。DDW 采用策略 A（直接复用核心设计模式），在 LICENSE 中保留 Third-Party Notice。

---

## 二、总体架构

### 2.1 架构全景图（文本）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        DDW AI Hub Platform                                  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │              ddw-industrial-data-access 插件                          │  │
│  │                                                                       │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │                    ① 协议适配层 (Protocol Adapters)              │  │  │
│  │  │                                                                 │  │  │
│  │  │  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌──────┐ ┌─────┐ ┌───┐ │  │  │
│  │  │  │ Modbus   │ │ OPC-UA   │ │ MQTT   │ │ HTTP │ │CSV/ │ │JDBC│ │  │  │
│  │  │  │TCP/RTU   │ │ Adapter  │ │Adapter │ │REST  │ │Excel│ │    │ │  │  │
│  │  │  │ Adapter  │ │          │ │        │ │      │ │     │ │    │ │  │  │
│  │  │  └────┬─────┘ └────┬─────┘ └───┬────┘ └──┬───┘ └──┬──┘ └─┬──┘ │  │  │
│  │  └───────┼─────────────┼──────────┼─────────┼────────┼──────┼────┘  │  │
│  │          │             │          │         │        │      │        │  │
│  │          └──────┬──────┴─────┬────┴────┬────┘    ┌───┘      │        │  │
│  │                 │            │         │         │          │        │  │
│  │  ┌──────────────▼────────────▼─────────▼─────────▼──────────▼─────┐  │  │
│  │  │              ② 数据采集管线 (Collection Pipeline)               │  │  │
│  │  │                                                                 │  │  │
│  │  │  ┌──────────┐   ┌──────────────┐   ┌────────────────────────┐  │  │  │
│  │  │  │  Input   │──▶│  Processor   │──▶│        Output          │  │  │  │
│  │  │  │ (采集)   │   │ (预处理)      │   │ (标准化输出)            │  │  │  │
│  │  │  └──────────┘   └──────────────┘   └────────────────────────┘  │  │  │
│  │  │   │ 协议解析      │ 边缘过滤/聚合       │ 写入存储/推送事件      │  │  │
│  │  │   │ 频率控制      │ 数值归一化          │                       │  │  │
│  │  │   │ 断线重连      │ 采样降频            │                       │  │  │
│  │  │   │ 本地缓存      │ 告警阈值检查         │                       │  │  │
│  │  │  └──────────┘   └──────────────┘   └────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  │                            │                                           │  │
│  │  ┌─────────────────────────▼───────────────────────────────────────┐  │  │
│  │  │              ③ 数据清洗标准化层 (Rule Engine)                    │  │  │
│  │  │                                                                 │  │  │
│  │  │  原始数据 ──▶ [清洗] ──▶ [标准化] ──▶ [质量检查] ──▶ [存储]    │  │  │
│  │  │                │           │            │                        │  │  │
│  │  │          去重/去噪    单位统一      缺失值检测                     │  │  │
│  │  │          时间戳对齐   字段映射      异常值标记                     │  │  │
│  │  │          编码转换     语义标准化     数据完整性评分                 │  │  │
│  │  │                                                                 │  │  │
│  │  │  ┌───────────────────────────────────────────────────────────┐  │  │  │
│  │  │  │  🤖 LLM 辅助层 (AI Enhancement)                          │  │  │  │
│  │  │  │  • 异常模式自动识别                                       │  │  │  │
│  │  │  │  • 清洗规则自动推荐                                       │  │  │  │
│  │  │  │  • 设备画像自动生成                                       │  │  │  │
│  │  │  └───────────────────────────────────────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  │                            │                                           │  │
│  │  ┌─────────────────────────▼───────────────────────────────────────┐  │  │
│  │  │              ④ 物模型层 (Thing Model)                           │  │  │
│  │  │                                                                 │  │  │
│  │  │  ┌─────────────────┐  ┌──────────────┐  ┌──────────────────┐  │  │  │
│  │  │  │ 设备画像         │  │ 属性模板      │  │ 行业模板          │  │  │  │
│  │  │  │ (Device Profile) │  │ (Attribute   │  │ (制造业/食品/     │  │  │  │
│  │  │  │                  │  │  Event/Svc)  │  │  医药/光通信)     │  │  │  │
│  │  │  └─────────────────┘  └──────────────┘  └──────────────────┘  │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  │                            │                                           │  │
│  │  ┌─────────────────────────▼───────────────────────────────────────┐  │  │
│  │  │              ⑤ 存储层 (Storage)                                 │  │  │
│  │  │                                                                 │  │  │
│  │  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │  │  │
│  │  │  │ SQLite        │  │ 文件存储      │  │ DDW Event Bus         │  │  │  │
│  │  │  │ (元数据/设备) │  │ (CSV备份)    │  │ (事件分发)           │  │  │  │
│  │  │  └──────────────┘  └──────────────┘  └──────────────────────┘  │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌─────────────────────┐  ┌──────────────────┐  ┌─────────────────────┐   │
│  │ ddw-esg-* 插件套件   │  │ ddw-llm-gateway  │  │ ddw-token-manager   │   │
│  │ (消费设备数据做ESG   │  │ (LLM调用网关)    │  │ (Token计量)         │   │
│  │  报告/合规评估)      │  │                  │  │                     │   │
│  └─────────────────────┘  └──────────────────┘  └─────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流向总览

```
                    ┌─────────────────────────┐
                    │     物理设备/系统         │
                    │ PLC · 传感器 · IoT设备    │
                    │ ERP/MES · Excel · 数据库   │
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │  协议适配层 (Adapter)     │
                    │  协议解析 → 原始消息      │
                    └──────────┬──────────────┘
                               │ 原始 DeviceData
                    ┌──────────▼──────────────┐
                    │  采集管线 (Pipeline)      │
                    │  频率控制 + 断线重连      │
                    │  + 本地缓存               │
                    └──────────┬──────────────┘
                               │ 采集后的 DeviceData
                    ┌──────────▼──────────────┐
                    │  边缘预处理 (Processor)   │
                    │  过滤 · 聚合 · 采样       │
                    │  告警阈值 · 数值归一化     │
                    └──────────┬──────────────┘
                               │ 预处理后的 DeviceData
                    ┌──────────▼──────────────┐
                    │  清洗标准化 (Rule Engine) │
                    │  去重 → 标准化 → 质量检查  │
                    │  [LLM辅助: 异常检测]      │
                    └──────────┬──────────────┘
                               │ 标准化的 DeviceData
                    ┌──────────▼──────────────┐
                    │  物模型映射 (Thing Model) │
                    │  Device Profile匹配      │
                    │  Attribute/Event/Service  │
                    └──────────┬──────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼─────┐ ┌───────▼───────┐ ┌──────▼──────┐
    │ SQLite 存储    │ │ CSV 文件备份  │ │ DDW 事件总线 │
    │ 设备+元数据    │ │ 原始数据归档  │ │ 下游插件消费 │
    └───────────────┘ └───────────────┘ └─────────────┘
```

---

## 三、模块详细设计

### 3.1 协议适配层 (Protocol Adapters)

#### 3.1.1 设计思路

参考 Telegraf 的 **Input Plugin** 模式和 ThingsBoard Gateway 的**协议转换器**模式，每个协议实现为一个独立的 Adapter 类，统一输出 `DeviceData` 标准消息。

#### 3.1.2 核心接口

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum
import time


class ProtocolType(str, Enum):
    """支持的协议类型"""
    MODBUS_TCP = "modbus_tcp"
    MODBUS_RTU = "modbus_rtu"
    OPC_UA = "opc_ua"
    MQTT = "mqtt"
    HTTP_REST = "http_rest"
    CSV_EXCEL = "csv_excel"
    JDBC = "jdbc"


@dataclass
class DeviceData:
    """
    统一设备数据消息格式
    参考 DG-IoT 的物模型数据格式 + ThingsBoard 的遥测数据结构
    """
    device_id: str                    # 设备唯一标识
    device_name: str                  # 设备名称
    timestamp: float                  # 采集时间戳 (Unix epoch)
    protocol: ProtocolType            # 数据来源协议
    source_endpoint: str              # 来源端点（如 "192.168.1.100:502"）

    # 物模型数据（参考 DG-IoT: Attribute + Event + Service）
    attributes: Dict[str, Any] = field(default_factory=dict)   # 静态属性
    telemetry: Dict[str, Any] = field(default_factory=dict)    # 实时遥测数据
    events: List[Dict[str, Any]] = field(default_factory=list) # 事件列表

    # 元数据
    quality_score: float = 1.0        # 数据质量评分 0-1
    raw_data: Optional[bytes] = None  # 原始数据（调试用）
    metadata: Dict[str, Any] = field(default_factory=dict)


class ProtocolAdapter(ABC):
    """
    协议适配器基类
    参考 Telegraf Input Plugin 的生命周期：
    init → start → gather → stop
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.connected = False
        self.last_error: Optional[str] = None
        self.retry_count = 0
        self.max_retries = config.get("max_retries", 3)
        self.retry_interval = config.get("retry_interval", 5.0)  # 秒

    @abstractmethod
    async def connect(self) -> bool:
        """建立连接"""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """断开连接"""
        ...

    @abstractmethod
    async def gather(self) -> List[DeviceData]:
        """
        采集一批数据（参考 Telegraf 的 gather() 方法）
        返回: 标准化的 DeviceData 列表
        """
        ...

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        return {
            "adapter": self.__class__.__name__,
            "connected": self.connected,
            "last_error": self.last_error,
            "retry_count": self.retry_count,
        }

    async def reconnect(self) -> bool:
        """断线重连逻辑"""
        while self.retry_count < self.max_retries:
            self.retry_count += 1
            try:
                await self.disconnect()
                if await self.connect():
                    self.retry_count = 0
                    self.last_error = None
                    return True
            except Exception as e:
                self.last_error = str(e)
                import asyncio
                await asyncio.sleep(self.retry_interval * self.retry_count)
        return False
```

#### 3.1.3 协议适配器实现清单

| Adapter | 依赖库 | 采集方式 | 关键配置 |
|:--------|:-------|:---------|:---------|
| **ModbusTCPAdapter** | `pymodbus` | 轮询读取 Holding/Input Registers | host, port, unit_id, register_map |
| **ModbusRTUAdapter** | `pymodbus` | 串口轮询 | port, baudrate, parity, register_map |
| **OPCUAAdapter** | `opcua` (asyncua) | 订阅 + 轮询 | endpoint_url, namespace, node_ids |
| **MQTTAdapter** | `paho-mqtt` | 订阅 topic | broker, port, topic_filter, qos |
| **HTTPRestAdapter** | `httpx` | 定时轮询 | url, method, headers, body_template |
| **CSVExcelAdapter** | `openpyxl` | 文件监听 + 解析 | file_path, sheet_name, column_map |
| **JDBCAdapter` | `sqlalchemy` | SQL 查询 | connection_string, query, interval |

#### 3.1.4 Modbus 适配器示例

```python
class ModbusTCPAdapter(ProtocolAdapter):
    """
    Modbus TCP 适配器
    用于采集 PLC、工业传感器等 Modbus 设备数据

    关键设计：
    - 寄存器映射表：将 Modbus 地址映射到物模型属性名
    - 字节序处理：支持 Big-Endian / Little-Endian / Mixed
    - 数据类型解析：int16/int32/float32/float64
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.host = config["host"]              # PLC IP
        self.port = config.get("port", 502)     # Modbus TCP 默认端口
        self.unit_id = config.get("unit_id", 1) # 站号
        self.register_map = config.get("register_map", [])
        # register_map 示例:
        # [
        #   {"name": "temperature", "address": 0, "type": "float32",
        #    "unit": "℃", "scale": 0.1},
        #   {"name": "pressure", "address": 2, "type": "float32",
        #    "unit": "MPa", "scale": 0.01},
        #   {"name": "speed", "address": 4, "type": "int16",
        #    "unit": "rpm", "scale": 1},
        # ]

    async def connect(self) -> bool:
        """建立 Modbus TCP 连接"""
        from pymodbus.client import AsyncModbusTcpClient
        self.client = AsyncModbusTcpClient(
            host=self.host, port=self.port
        )
        connected = await self.client.connect()
        self.connected = connected
        if connected:
            self.retry_count = 0
        return connected

    async def disconnect(self) -> None:
        if hasattr(self, 'client') and self.client:
            self.client.close()
        self.connected = False

    async def gather(self) -> List[DeviceData]:
        """采集所有寄存器映射配置的数据"""
        if not self.connected:
            raise ConnectionError("Modbus 连接未建立")

        telemetry = {}
        for reg in self.register_map:
            result = await self.client.read_holding_registers(
                address=reg["address"],
                count=self._type_to_count(reg["type"]),
                unit=self.unit_id,
            )
            if not result.isError():
                value = self._decode_registers(
                    result.registers, reg["type"]
                )
                # 应用缩放因子
                if "scale" in reg:
                    value = value * reg["scale"]
                telemetry[reg["name"]] = {
                    "value": value,
                    "unit": reg.get("unit", ""),
                }

        return [DeviceData(
            device_id=f"modbus_{self.host}_{self.unit_id}",
            device_name=self.config.get("device_name", f"PLC@{self.host}"),
            timestamp=time.time(),
            protocol=ProtocolType.MODBUS_TCP,
            source_endpoint=f"{self.host}:{self.port}",
            telemetry=telemetry,
        )]

    def _type_to_count(self, data_type: str) -> int:
        """数据类型 → 寄存器数量"""
        return {"int16": 1, "int32": 2, "float32": 2, "float64": 4}.get(data_type, 1)

    def _decode_registers(self, registers: list, data_type: str):
        """寄存器值 → Python 数值"""
        from pymodbus.payload import BinaryPayloadDecoder
        from pymodbus.constants import Endian
        decoder = BinaryPayloadDecoder.fromRegisters(
            registers, byteorder=Endian.BIG, wordorder=Endian.BIG
        )
        type_map = {
            "int16": decoder.decode_16bit_uint,
            "int32": decoder.decode_32bit_uint,
            "float32": decoder.decode_32bit_float,
            "float64": decoder.decode_64bit_float,
        }
        return type_map[data_type]()
```

#### 3.1.5 OPC-UA 适配器要点

```python
class OPCUAAdapter(ProtocolAdapter):
    """
    OPC-UA 适配器
    参考 ThingsBoard Gateway 的 OPC-UA 设备配置方式

    关键设计：
    - 节点订阅模式（Subscription）：设备数据变化时主动推送
    - 轮询模式：按配置频率定期读取
    - 地址空间浏览：自动发现设备节点

    典型场景：现代CNC机床、工业机器人、智能仪表
    """

    async def connect(self) -> bool:
        from asyncua import Client
        self.client = Client(url=self.config["endpoint_url"])
        # 如需认证
        if "username" in self.config:
            self.client.set_user(self.config["username"])
            self.client.set_password(self.config["password"])
        await self.client.connect()
        self.connected = True
        return True

    async def gather(self) -> List[DeviceData]:
        """读取所有配置的节点值"""
        telemetry = {}
        for node_cfg in self.config.get("nodes", []):
            node = self.client.get_node(node_cfg["node_id"])
            value = await node.read_value()
            telemetry[node_cfg["name"]] = {
                "value": value,
                "unit": node_cfg.get("unit", ""),
            }

        return [DeviceData(
            device_id=self.config.get("device_id", "opcua_default"),
            device_name=self.config.get("device_name", "OPC-UA Device"),
            timestamp=time.time(),
            protocol=ProtocolType.OPC_UA,
            source_endpoint=self.config["endpoint_url"],
            telemetry=telemetry,
        )]
```

---

### 3.2 数据采集管线 (Collection Pipeline)

#### 3.2.1 管线模型设计

参考 Telegraf 的 **Input → Processor → Output** 三段式管线，但做了轻量化改造：

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ Adapter  │────▶│ Collector│────▶│ Processor│────▶│ Output   │
│ (协议适配) │     │ (采集调度) │     │ (预处理)  │     │ (标准化  │
│          │     │          │     │          │     │  输出)   │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
```

#### 3.2.2 采集调度器 (Collector)

```python
import asyncio
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class CollectorConfig:
    """单个采集任务配置"""
    adapter_name: str                   # 对应的 Adapter 名称
    interval_seconds: float = 5.0       # 采集间隔（秒）
    enabled: bool = True
    max_batch_size: int = 100           # 最大批量
    cache_ttl_seconds: int = 300        # 本地缓存有效期
    edge_processors: List[str] = None   # 边缘预处理步骤

    def __post_init__(self):
        if self.edge_processors is None:
            self.edge_processors = []


class Collector:
    """
    采集调度器 — 管理多个 Adapter 的采集任务

    核心职责：
    1. 按配置频率触发各 Adapter 的 gather()
    2. 管理断线重连（Adapter 异常时自动重试）
    3. 本地数据缓存（网络异常时数据不丢失）
    4. 数据流转到 Processor 层

    参考 Telegraf Agent 的 gather + flush 机制
    """

    def __init__(self) -> None:
        self._adapters: Dict[str, ProtocolAdapter] = {}
        self._configs: Dict[str, CollectorConfig] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._cache: Dict[str, List[DeviceData]] = {}
        self._running = False
        self._pipeline_callback = None  # 下游 Processor 回调

    def register_adapter(
        self, name: str, adapter: ProtocolAdapter, config: CollectorConfig
    ) -> None:
        """注册一个协议适配器"""
        self._adapters[name] = adapter
        self._configs[name] = config
        self._cache[name] = []

    def set_pipeline_callback(self, callback) -> None:
        """设置管线下游回调（连接到 Processor 层）"""
        self._pipeline_callback = callback

    async def start(self) -> None:
        """启动所有采集任务"""
        self._running = True
        for name, config in self._configs.items():
            if config.enabled:
                task = asyncio.create_task(
                    self._collection_loop(name, config)
                )
                self._tasks[name] = task

    async def stop(self) -> None:
        """停止所有采集任务"""
        self._running = False
        for task in self._tasks.values():
            task.cancel()
        # 断开所有适配器
        for adapter in self._adapters.values():
            try:
                await adapter.disconnect()
            except Exception:
                pass

    async def _collection_loop(
        self, name: str, config: CollectorConfig
    ) -> None:
        """单个适配器的采集循环"""
        adapter = self._adapters[name]

        # 首次连接
        if not adapter.connected:
            await adapter.connect()

        while self._running:
            try:
                if not adapter.connected:
                    await adapter.reconnect()

                data_list = await adapter.gather()

                # 边缘预处理
                for processor_name in config.edge_processors:
                    processor = get_edge_processor(processor_name)
                    if processor:
                        data_list = await processor.process(data_list)

                # 缓存 + 下发
                self._cache[name].extend(data_list)
                if len(self._cache[name]) >= config.max_batch_size:
                    batch = self._cache[name][:config.max_batch_size]
                    self._cache[name] = self._cache[name][config.max_batch_size:]
                    await self._dispatch(batch)

            except ConnectionError:
                await adapter.reconnect()
            except Exception as e:
                logger.error(f"采集任务 {name} 异常: {e}")
                adapter.last_error = str(e)

            await asyncio.sleep(config.interval_seconds)

    async def _dispatch(self, data_list: List[DeviceData]) -> None:
        """将采集到的数据分发到下游"""
        if self._pipeline_callback:
            await self._pipeline_callback(data_list)
```

#### 3.2.3 采集频率配置

| 级别 | 间隔 | 典型场景 | 预估数据量/天 |
|:-----|:-----|:---------|:-------------|
| **秒级** | 1-10s | CNC主轴温度、振动监测 | ~10万条/设备 |
| **分钟级** | 30-300s | 环境温湿度、能耗统计 | ~3000条/设备 |
| **小时级** | 3600s+ | 水质检测、库存盘点 | ~24条/设备 |
| **手动触发** | on_demand | 质检数据录入、Excel导入 | 按需 |

#### 3.2.4 断线重连 + 数据缓存

```
正常连接 ──── 采集正常 ──── 缓存空
    │                         │
    │ 连接断开                 │
    ▼                         │
重连状态 ◀── 重试 (3次) ──▶ 超过重试 → 暂停采集
    │                         │
    │ 重连成功                 │
    ▼                         │
发送缓存数据 ──────────────▶ 清空缓存
    │                         │
    │ 重连失败 (max_retries)   │
    ▼                         │
本地缓存写入 ──▶ 等待下次重试间隔
    │
    │ 缓存满 (默认10000条)
    │
    ▼
最旧数据丢弃 (FIFO)
```

---

### 3.3 边缘预处理 (Edge Processors)

参考 ThingsBoard Gateway 的边缘计算能力，在数据进入清洗层之前做轻量预处理：

```python
from abc import ABC, abstractmethod


class EdgeProcessor(ABC):
    """边缘预处理基类"""

    @abstractmethod
    async def process(self, data_list: List[DeviceData]) -> List[DeviceData]:
        """处理一批数据，返回处理后的数据"""
        ...


class FilterProcessor(EdgeProcessor):
    """过滤器：丢弃不符合条件的数据"""

    def __init__(self, rules: List[Dict[str, Any]]) -> None:
        self.rules = rules
        # rules 示例: [{"field": "telemetry.temperature.value", "op": ">", "value": -50}]

    async def process(self, data_list: List[DeviceData]) -> List[DeviceData]:
        result = []
        for data in data_list:
            if self._matches_all_rules(data):
                result.append(data)
        return result

    def _matches_all_rules(self, data: DeviceData) -> bool:
        for rule in self.rules:
            value = self._extract_field(data, rule["field"])
            if not self._evaluate(value, rule["op"], rule["value"]):
                return False
        return True


class AggregationProcessor(EdgeProcessor):
    """聚合器：对时间窗口内的数据做均值/最大/最小/计数"""

    def __init__(self, window_seconds: int = 60, operations: List[str] = None) -> None:
        self.window_seconds = window_seconds
        self.operations = operations or ["avg", "max", "min"]
        self._buffer: List[DeviceData] = []

    async def process(self, data_list: List[DeviceData]) -> List[DeviceData]:
        self._buffer.extend(data_list)
        if not self._buffer:
            return []

        now = time.time()
        window_start = now - self.window_seconds
        window_data = [d for d in self._buffer if d.timestamp >= window_start]
        self._buffer = window_data

        if len(window_data) < 2:
            return data_list  # 数据不够，直接透传

        # 按设备分组聚合
        from collections import defaultdict
        grouped = defaultdict(list)
        for d in window_data:
            grouped[d.device_id].append(d)

        result = []
        for device_id, records in grouped.items():
            aggregated_telemetry = {}
            for key in records[0].telemetry:
                values = [
                    r.telemetry[key]["value"]
                    for r in records
                    if key in r.telemetry and isinstance(r.telemetry[key]["value"], (int, float))
                ]
                if values:
                    aggregated_telemetry[key] = {
                        "avg": sum(values) / len(values),
                        "max": max(values),
                        "min": min(values),
                        "count": len(values),
                    }

            result.append(DeviceData(
                device_id=device_id,
                device_name=records[0].device_name,
                timestamp=now,
                protocol=records[0].protocol,
                source_endpoint=records[0].source_endpoint,
                telemetry=aggregated_telemetry,
                metadata={"aggregated": True, "sample_count": len(records)},
            ))
        return result


class AlarmThresholdProcessor(EdgeProcessor):
    """告警阈值检查器：超过阈值时标记告警"""

    def __init__(self, thresholds: Dict[str, Dict[str, float]] = None) -> None:
        self.thresholds = thresholds or {}
        # thresholds 示例:
        # {"temperature": {"high": 80.0, "critical": 95.0},
        #  "vibration": {"high": 10.0, "critical": 15.0}}

    async def process(self, data_list: List[DeviceData]) -> List[DeviceData]:
        for data in data_list:
            for key, value_info in data.telemetry.items():
                if key in self.thresholds and isinstance(value_info.get("value"), (int, float)):
                    val = value_info["value"]
                    th = self.thresholds[key]
                    if val >= th.get("critical", float('inf')):
                        value_info["alarm_level"] = "critical"
                    elif val >= th.get("high", float('inf')):
                        value_info["alarm_level"] = "high"
                    else:
                        value_info["alarm_level"] = "normal"
        return data_list
```

---

### 3.4 数据清洗标准化层 (Rule Engine)

参考 ThingsBoard 的 **Rule Chain** 链式处理模式，但简化为 Python 链式处理器：

#### 3.4.1 清洗管线

```
原始数据 → [去重] → [时间戳对齐] → [编码转换] → [单位标准化]
         → [缺失值处理] → [异常值检测] → [质量评分] → 标准化数据
```

#### 3.4.2 核心实现

```python
class DataCleaner:
    """
    数据清洗引擎
    参考 ThingsBoard Rule Engine 的链式处理模式
    """

    def __init__(self):
        self._steps: List[Callable] = []

    def add_step(self, step_fn) -> 'DataCleaner':
        """添加清洗步骤（链式调用）"""
        self._steps.append(step_fn)
        return self

    async def clean(self, data_list: List[DeviceData]) -> List[DeviceData]:
        """执行完整清洗管线"""
        result = data_list
        for step in self._steps:
            result = await step(result)
        return result


# ── 内置清洗步骤 ──────────────────────────────────────────────

async def dedup_step(data_list: List[DeviceData]) -> List[DeviceData]:
    """去重：同一设备同一时间戳的数据只保留最新一条"""
    seen = {}
    for data in data_list:
        key = f"{data.device_id}_{data.timestamp}"
        seen[key] = data
    return list(seen.values())


async def timestamp_align_step(data_list: List[DeviceData]) -> List[DeviceData]:
    """时间戳对齐：统一为 UTC 时间，精度到毫秒"""
    for data in data_list:
        data.timestamp = round(data.timestamp * 1000) / 1000  # 毫秒精度
    return data_list


async def unit_standardize_step(mapping: Dict[str, str]) -> Callable:
    """单位标准化工厂函数"""
    # mapping: {"temperature_℃": "temperature_°C", "pressure_MPa": "pressure_Pa"}

    async def _step(data_list: List[DeviceData]) -> List[DeviceData]:
        for data in data_list:
            new_telemetry = {}
            for key, value_info in data.telemetry.items():
                std_key = mapping.get(key, key)
                new_telemetry[std_key] = value_info
            data.telemetry = new_telemetry
        return data_list
    return _step


async def missing_value_step(
    strategy: str = "interpolate"
) -> Callable:
    """缺失值处理工厂函数

    strategy:
    - "drop": 丢弃有缺失值的记录
    - "fill_zero": 用 0 填充
    - "fill_last": 用上一个有效值填充
    - "interpolate": 线性插值
    """

    async def _step(data_list: List[DeviceData]) -> List[DeviceData]:
        if strategy == "drop":
            return [
                d for d in data_list
                if all(
                    v.get("value") is not None
                    for v in d.telemetry.values()
                )
            ]
        # 其他策略类似实现...
        return data_list
    return _step


async def quality_score_step(
    thresholds: Dict[str, Dict[str, float]] = None
) -> Callable:
    """数据质量评分工厂函数

    评分维度：
    - 完整性：字段缺失率
    - 时效性：时间戳延迟
    - 合理性：数值是否在正常范围
    """

    async def _step(data_list: List[DeviceData]) -> List[DeviceData]:
        for data in data_list:
            scores = []

            # 完整性评分
            expected_fields = thresholds.get("expected_fields", []) if thresholds else []
            if expected_fields:
                present = sum(1 for f in expected_fields if f in data.telemetry)
                scores.append(present / len(expected_fields))

            # 时效性评分（1分钟内 = 1.0，1小时外 = 0.5）
            delay = time.time() - data.timestamp
            if delay < 60:
                scores.append(1.0)
            elif delay < 3600:
                scores.append(0.8)
            else:
                scores.append(0.5)

            # 合理性评分（值在阈值范围内）
            if thresholds:
                for key, value_info in data.telemetry.items():
                    if key in thresholds and isinstance(value_info.get("value"), (int, float)):
                        range_ = thresholds[key]
                        val = value_info["value"]
                        if range_.get("min", float('-inf')) <= val <= range_.get("max", float('inf')):
                            scores.append(1.0)
                        else:
                            scores.append(0.3)

            data.quality_score = sum(scores) / len(scores) if scores else 1.0
        return data_list
    return _step
```

#### 3.4.3 LLM 辅助数据清洗

通过 DDW LLM Gateway 调用 AI 能力（不直接配置 LLM Provider）：

```python
class LLMDataAssistant:
    """
    LLM 辅助数据清洗
    通过 DDW Gateway 统一调用 LLM，不自行管理 Provider
    """

    def __init__(self, ddw_gateway_url: str) -> None:
        self.gateway_url = ddw_gateway_url

    async def detect_anomalies(
        self, data_list: List[DeviceData]
    ) -> List[Dict[str, Any]]:
        """
        用 LLM 识别数据异常模式
        输入：最近 N 条设备数据
        输出：异常描述 + 建议的清洗规则
        """
        # 构造 prompt
        data_summary = self._summarize_for_llm(data_list)
        prompt = f"""分析以下工业设备数据，识别异常模式：

{data_summary}

请返回 JSON 格式：
{{
  "anomalies": [
    {{
      "device_id": "...",
      "metric": "...",
      "anomaly_type": "spike|drop|drift|stuck|gap",
      "description": "异常描述",
      "severity": "low|medium|high|critical",
      "suggested_rule": "建议的清洗规则"
    }}
  ],
  "recommendations": ["整体建议1", "整体建议2"]
}}"""

        # 调用 DDW LLM Gateway
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.gateway_url}/api/v1/llm/generate",
                json={"prompt": prompt, "max_tokens": 2000}
            )
            return response.json()

    async def recommend_cleaning_rules(
        self, data_description: str
    ) -> List[Dict[str, Any]]:
        """
        根据数据描述，让 LLM 推荐清洗规则
        """
        prompt = f"""为以下工业设备数据推荐清洗规则：

数据描述：{data_description}

请返回推荐的清洗步骤列表（JSON 数组），每步包含：
- step_name: 步骤名称
- function: 使用的函数（dedup/timestamp_align/unit_standardize/missing_value/quality_score/filter）
- config: 函数配置参数
- reason: 推荐理由"""

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.gateway_url}/api/v1/llm/generate",
                json={"prompt": prompt, "max_tokens": 3000}
            )
            return response.json()

    def _summarize_for_llm(self, data_list: List[DeviceData]) -> str:
        """将设备数据摘要化为 LLM 可读格式"""
        summary_lines = []
        for data in data_list[:50]:  # 最多 50 条
            telemetry_str = ", ".join(
                f"{k}={v.get('value', 'N/A')}"
                for k, v in data.telemetry.items()
            )
            summary_lines.append(
                f"[{data.device_name}] {telemetry_str} "
                f"(quality={data.quality_score:.2f})"
            )
        return "\n".join(summary_lines)
```

---

### 3.5 物模型层 (Thing Model)

参考 DG-IoT 的物模型定义（Attribute + Event + Service），以及 ThingsBoard 的 Device Profile 概念。

#### 3.5.1 核心数据模型

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class PropertyType(str, Enum):
    """属性值类型"""
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    BOOLEAN = "boolean"
    JSON = "json"


class EventType(str, Enum):
    """事件类型"""
    DEVICE_ONLINE = "device_online"
    DEVICE_OFFLINE = "device_offline"
    ALARM = "alarm"
    ALERT = "alert"
    CUSTOM = "custom"


@dataclass
class PropertyDefinition:
    """
    属性定义（参考 DG-IoT Attribute）
    描述设备的一个可读/可写属性
    """
    name: str                              # 属性名（英文，如 temperature）
    display_name: str                      # 显示名（中文，如 温度）
    property_type: PropertyType            # 值类型
    access_mode: str = "read"              # read / readwrite
    unit: str = ""                         # 单位（℃, MPa, rpm）
    min_value: Optional[float] = None      # 最小值
    max_value: Optional[float] = None      # 最大值
    description: str = ""
    default_value: Any = None
    scale_factor: float = 1.0              # 缩放因子
    alarm_thresholds: Dict[str, float] = field(default_factory=dict)
    # alarm_thresholds: {"high": 80.0, "critical": 95.0}


@dataclass
class EventDefinition:
    """
    事件定义（参考 DG-IoT Event）
    描述设备可以发出的事件
    """
    name: str                              # 事件名
    display_name: str
    event_type: EventType
    severity: str = "info"                 # info / warning / error / critical
    description: str = ""
    payload_schema: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ServiceDefinition:
    """
    服务定义（参考 DG-IoT Service）
    描述设备可以执行的远程命令
    """
    name: str
    display_name: str
    input_params: Dict[str, PropertyDefinition] = field(default_factory=dict)
    output_params: Dict[str, PropertyDefinition] = field(default_factory=dict)
    description: str = ""


@dataclass
class DeviceProfile:
    """
    设备画像模板（参考 ThingsBoard Device Profile）
    定义一类设备的物模型
    """
    id: str                                # 模板ID（如 cnc_machine, optical_transceiver）
    name: str                              # 模板名称
    category: str                          # 行业分类
    description: str = ""
    version: str = "1.0.0"

    # 物模型三要素
    attributes: List[PropertyDefinition] = field(default_factory=list)
    telemetry: List[PropertyDefinition] = field(default_factory=list)
    events: List[EventDefinition] = field(default_factory=list)
    services: List[ServiceDefinition] = field(default_factory=list)

    # 采集配置
    default_polling_interval: float = 5.0  # 默认采集间隔（秒）
    protocols_supported: List[str] = field(default_factory=list)  # 支持的协议
```

#### 3.5.2 行业模板库

```python
# ── 制造业 (CNC/机加工) ──────────────────────────────────────────────

CNC_MACHINE_PROFILE = DeviceProfile(
    id="cnc_machine",
    name="CNC数控机床",
    category="制造业",
    description="CNC数控加工中心设备画像，覆盖主轴、进给轴、刀库等核心参数",
    protocols_supported=["modbus_tcp", "opc_ua", "mqtt"],
    telemetry=[
        PropertyDefinition(
            name="spindle_speed", display_name="主轴转速",
            property_type=PropertyType.FLOAT, unit="rpm",
            min_value=0, max_value=20000,
            alarm_thresholds={"high": 15000, "critical": 18000},
        ),
        PropertyDefinition(
            name="spindle_temperature", display_name="主轴温度",
            property_type=PropertyType.FLOAT, unit="℃",
            min_value=0, max_value=150,
            alarm_thresholds={"high": 80, "critical": 95},
        ),
        PropertyDefinition(
            name="feed_rate", display_name="进给速率",
            property_type=PropertyType.FLOAT, unit="mm/min",
        ),
        PropertyDefinition(
            name="vibration_x", display_name="X轴振动",
            property_type=PropertyType.FLOAT, unit="mm/s",
            alarm_thresholds={"high": 8.0, "critical": 12.0},
        ),
        PropertyDefinition(
            name="vibration_y", display_name="Y轴振动",
            property_type=PropertyType.FLOAT, unit="mm/s",
            alarm_thresholds={"high": 8.0, "critical": 12.0},
        ),
        PropertyDefinition(
            name="power_consumption", display_name="功率消耗",
            property_type=PropertyType.FLOAT, unit="kW",
        ),
        PropertyDefinition(
            name="tool_life", display_name="刀具寿命",
            property_type=PropertyType.INT, unit="hours",
        ),
    ],
    attributes=[
        PropertyDefinition(
            name="manufacturer", display_name="制造商",
            property_type=PropertyType.STRING, access_mode="read",
        ),
        PropertyDefinition(
            name="model", display_name="型号",
            property_type=PropertyType.STRING, access_mode="read",
        ),
        PropertyDefinition(
            name="max_spindle_speed", display_name="最大主轴转速",
            property_type=PropertyType.FLOAT, unit="rpm",
            access_mode="read",
        ),
    ],
    events=[
        EventDefinition(
            name="spindle_overheat", display_name="主轴过热",
            event_type=EventType.ALARM, severity="critical",
        ),
        EventDefinition(
            name="tool_break", display_name="刀具断裂",
            event_type=EventType.ALARM, severity="critical",
        ),
        EventDefinition(
            name="maintenance_due", display_name="保养到期",
            event_type=EventType.ALERT, severity="warning",
        ),
    ],
    services=[
        ServiceDefinition(
            name="emergency_stop", display_name="紧急停止",
            input_params={},
        ),
        ServiceDefinition(
            name="set_spindle_speed", display_name="设置主轴转速",
            input_params={
                "speed": PropertyDefinition(
                    name="speed", display_name="目标转速",
                    property_type=PropertyType.FLOAT, unit="rpm",
                )
            },
        ),
    ],
)

# ── 光通信 ────────────────────────────────────────────────────────

OPTICAL_MODULE_PROFILE = DeviceProfile(
    id="optical_module",
    name="光通信模块",
    category="光通信",
    description="光模块/光收发器设备画像，覆盖光功率、温度、电压等核心参数",
    protocols_supported=["modbus_tcp", "i2c", "mqtt"],
    telemetry=[
        PropertyDefinition(
            name="tx_optical_power", display_name="发送光功率",
            property_type=PropertyType.FLOAT, unit="dBm",
            min_value=-10, max_value=5,
        ),
        PropertyDefinition(
            name="rx_optical_power", display_name="接收光功率",
            property_type=PropertyType.FLOAT, unit="dBm",
            min_value=-30, max_value=0,
        ),
        PropertyDefinition(
            name="bias_current", display_name="偏置电流",
            property_type=PropertyType.FLOAT, unit="mA",
        ),
        PropertyDefinition(
            name="temperature", display_name="模块温度",
            property_type=PropertyType.FLOAT, unit="℃",
            min_value=-40, max_value=85,
            alarm_thresholds={"high": 70, "critical": 80},
        ),
        PropertyDefinition(
            name="voltage", display_name="工作电压",
            property_type=PropertyType.FLOAT, unit="V",
        ),
        PropertyDefinition(
            name="bit_error_rate", display_name="误码率",
            property_type=PropertyType.STRING, unit="BER",
        ),
    ],
)

# ── 食品 ──────────────────────────────────────────────────────────

FOOD_PRODUCTION_PROFILE = DeviceProfile(
    id="food_production",
    name="食品生产线",
    category="食品",
    description="食品生产加工设备画像，覆盖温湿度、压力、流量等工艺参数",
    protocols_supported=["modbus_tcp", "modbus_rtu", "mqtt"],
    telemetry=[
        PropertyDefinition(
            name="temperature", display_name="加工温度",
            property_type=PropertyType.FLOAT, unit="℃",
        ),
        PropertyDefinition(
            name="humidity", display_name="环境湿度",
            property_type=PropertyType.FLOAT, unit="%RH",
        ),
        PropertyDefinition(
            name="pressure", display_name="罐内压力",
            property_type=PropertyType.FLOAT, unit="MPa",
        ),
        PropertyDefinition(
            name="flow_rate", display_name="物料流量",
            property_type=PropertyType.FLOAT, unit="L/min",
        ),
        PropertyDefinition(
            name="ph_value", display_name="pH值",
            property_type=PropertyType.FLOAT, unit="pH",
            min_value=0, max_value=14,
        ),
    ],
)

# ── 医药 ──────────────────────────────────────────────────────────

PHARMA_PROFILE = DeviceProfile(
    id="pharma_production",
    name="医药生产设备",
    category="医药",
    description="GMP医药生产环境设备画像，覆盖洁净区环境+工艺参数",
    protocols_supported=["modbus_tcp", "opc_ua", "mqtt"],
    telemetry=[
        PropertyDefinition(
            name="room_temperature", display_name="洁净室温度",
            property_type=PropertyType.FLOAT, unit="℃",
            alarm_thresholds={"high": 26, "critical": 28},
        ),
        PropertyDefinition(
            name="room_humidity", display_name="洁净室湿度",
            property_type=PropertyType.FLOAT, unit="%RH",
            alarm_thresholds={"high": 65, "critical": 70},
        ),
        PropertyDefinition(
            name="particle_count", display_name="粒子数",
            property_type=PropertyType.INT, unit="个/m³",
        ),
        PropertyDefinition(
            name="differential_pressure", display_name="压差",
            property_type=PropertyType.FLOAT, unit="Pa",
        ),
        PropertyDefinition(
            name="batch_temperature", display_name="批次温度",
            property_type=PropertyType.FLOAT, unit="℃",
        ),
    ],
)
```

---

### 3.6 存储层

轻量存储方案，不引入 InfluxDB/TDengine 等时序数据库：

```python
from sqlalchemy import (
    Column, Float, Integer, String, Text, DateTime, JSON, Boolean,
    create_engine, Index,
)
from sqlalchemy.orm import DeclarativeBase, Session
import datetime


class Base(DeclarativeBase):
    pass


class Device(Base):
    """设备注册表"""
    __tablename__ = "devices"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    profile_id = Column(String(64), nullable=False)       # 关联 DeviceProfile
    protocol = Column(String(32), nullable=False)
    endpoint = Column(String(256), nullable=False)         # 连接端点
    config = Column(JSON, default={})                      # 协议配置
    tags = Column(JSON, default=[])                        # 自定义标签
    is_online = Column(Boolean, default=False)
    last_seen_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        Index("idx_device_profile", "profile_id"),
        Index("idx_device_protocol", "protocol"),
    )


class DeviceDataRecord(Base):
    """
    设备数据记录
    用 SQLite 存储，配合 WAL 模式支持高并发写入
    """
    __tablename__ = "device_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(64), nullable=False)
    timestamp = Column(Float, nullable=False)             # Unix epoch
    telemetry = Column(JSON, nullable=False)              # 遥测数据
    attributes = Column(JSON, default={})                 # 属性数据
    quality_score = Column(Float, default=1.0)
    protocol = Column(String(32))
    metadata = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        Index("idx_data_device_time", "device_id", "timestamp"),
        Index("idx_data_timestamp", "timestamp"),
    )


class CleaningRule(Base):
    """
    清洗规则配置
    支持 LLM 自动推荐 + 手动配置
    """
    __tablename__ = "cleaning_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    device_profile_id = Column(String(64), nullable=False)
    steps = Column(JSON, nullable=False)                  # 清洗步骤列表
    enabled = Column(Boolean, default=True)
    source = Column(String(32), default="manual")        # manual / llm_recommended
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow,
                        onupdate=datetime.datetime.utcnow)
```

**存储策略**：

| 数据类型 | 存储位置 | 保留策略 |
|:---------|:---------|:---------|
| 设备元数据 | SQLite `devices` 表 | 长期保留 |
| 实时遥测数据 | SQLite `device_data` 表 | 默认 90 天，可配 |
| 原始数据备份 | CSV 文件（`data/raw/{device_id}/{YYYY-MM-DD}.csv`） | 30 天 |
| 清洗规则 | SQLite `cleaning_rules` 表 | 长期保留 |
| 统计聚合数据 | SQLite（按小时/天聚合） | 365 天 |

**性能优化**：
- SQLite 使用 WAL 模式（`PRAGMA journal_mode=WAL`）
- 批量写入使用 `executemany` + 事务
- 大数据量时按月分表（`device_data_202607`）
- 异步写入队列：采集线程不阻塞写入

---

### 3.7 插件注册与 DDW 集成

#### 3.7.1 插件主类

```python
"""
DDW 工业设备数据接入插件
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class IndustrialDataAccessPlugin(PluginBase):
    """工业设备数据接入层插件"""

    name = "ddw-industrial-data-access"
    version = "1.0.0"
    router_prefix = "/api/v1/plugins/industrial-data"

    def setup(self) -> None:
        """初始化：注册路由 + 启动采集引擎"""
        from .collector import Collector
        from .rule_engine import DataCleaner
        from .storage import DeviceDataStore
        from .thing_model import ThingModelManager
        from .llm_assistant import LLMDataAssistant

        # 初始化各子系统
        self.collector = Collector()
        self.cleaner = DataCleaner()
        self.store = DeviceDataStore()
        self.thing_model = ThingModelManager()
        self.llm_assistant = LLMDataAssistant(
            self.config.get("ddw_gateway_url", "http://localhost:8000")
        )

        # 管线连接：Collector → Cleaner → Store
        self.collector.set_pipeline_callback(self._pipeline_handler)

        # 注册路由
        self._register_routes()

    async def _pipeline_handler(self, data_list):
        """管线回调：清洗 → 标准化 → 存储"""
        cleaned = await self.cleaner.clean(data_list)
        await self.store.batch_insert(cleaned)
        # 发布到 DDW 事件总线
        for data in cleaned:
            self._publish_event("device.data.received", {
                "device_id": data.device_id,
                "telemetry": data.telemetry,
                "quality_score": data.quality_score,
            })

    def _register_routes(self) -> None:
        """注册 API 路由"""
        from fastapi import HTTPException, Query
        from pydantic import BaseModel
        from typing import Optional

        @self.router.get("/health")
        async def health():
            return {"plugin": self.name, "status": "ok"}

        @self.router.get("/devices")
        async def list_devices(
            profile_id: Optional[str] = Query(None),
            protocol: Optional[str] = Query(None),
        ):
            return await self.store.list_devices(
                profile_id=profile_id, protocol=protocol
            )

        @self.router.post("/devices")
        async def register_device(body: dict):
            return await self.store.create_device(body)

        @self.router.get("/devices/{device_id}/data")
        async def get_device_data(
            device_id: str,
            start: float = Query(..., description="开始时间戳"),
            end: float = Query(..., description="结束时间戳"),
            limit: int = Query(1000, le=10000),
        ):
            return await self.store.query_data(device_id, start, end, limit)

        @self.router.get("/devices/{device_id}/latest")
        async def get_latest_data(device_id: str):
            return await self.store.get_latest(device_id)

        @self.router.get("/profiles")
        async def list_profiles():
            return self.thing_model.list_profiles()

        @self.router.get("/profiles/{profile_id}")
        async def get_profile(profile_id: str):
            profile = self.thing_model.get_profile(profile_id)
            if not profile:
                raise HTTPException(404, f"Profile '{profile_id}' not found")
            return profile

        @self.router.post("/collectors/start")
        async def start_collector(body: dict):
            adapter_name = body.get("adapter_name")
            await self.collector.start_adapter(adapter_name)
            return {"status": "started", "adapter": adapter_name}

        @self.router.post("/collectors/stop")
        async def stop_collector(body: dict):
            adapter_name = body.get("adapter_name")
            await self.collector.stop_adapter(adapter_name)
            return {"status": "stopped", "adapter": adapter_name}

        @self.router.get("/collectors/status")
        async def collector_status():
            return await self.collector.get_all_status()

        @self.router.post("/cleaning-rules")
        async def create_cleaning_rule(body: dict):
            return await self.store.create_cleaning_rule(body)

        @self.router.get("/cleaning-rules")
        async def list_cleaning_rules(
            profile_id: Optional[str] = Query(None),
        ):
            return await self.store.list_cleaning_rules(profile_id)

        @self.router.post("/ai/detect-anomalies")
        async def detect_anomalies(body: dict):
            device_id = body.get("device_id")
            data = await self.store.get_recent(device_id, limit=100)
            return await self.llm_assistant.detect_anomalies(data)

        @self.router.post("/ai/recommend-rules")
        async def recommend_rules(body: dict):
            return await self.llm_assistant.recommend_cleaning_rules(
                body.get("data_description", "")
            )

    def tool_annotations(self) -> dict[str, dict]:
        return {
            "health": {"readOnly": True},
            "list_devices": {"readOnly": True},
            "get_device_data": {"readOnly": True},
            "get_latest_data": {"readOnly": True},
            "profiles": {"readOnly": True},
            "collector_status": {"readOnly": True},
            "list_cleaning_rules": {"readOnly": True},
            "register_device": {"readOnly": False},
            "start_collector": {"readOnly": False},
            "stop_collector": {"readOnly": False},
            "create_cleaning_rule": {"readOnly": False},
            "detect_anomalies": {"readOnly": True},
            "recommend_rules": {"readOnly": True},
        }


# ── 轻量模式注册入口 ────────────────────────────────────────────

def register(app) -> None:
    """Register this plugin's router with the FastAPI application."""
    plugin = IndustrialDataAccessPlugin(app)
    plugin.register()
    logger.info("ddw-industrial-data-access plugin registered")
```

#### 3.7.2 manifest.yaml

```yaml
name: ddw-industrial-data-access
version: 1.0.0
description: >
  工业设备数据统一接入层 — 支持 Modbus/OPC-UA/MQTT/HTTP/CSV/JDBC 六大协议，
  参考 Telegraf 管线模型 + ThingsBoard 边缘计算 + DG-IoT 物模型。
  轻量部署，单机 8GB RAM 即可运行。
engine: ">=0.1.0"
dependencies:
  plugins: {}
events:
  produces:
    - device.data.received
    - device.online
    - device.offline
    - device.alarm
  consumes: []
isolation: inline
permissions:
  - devices.read
  - devices.write
  - data.read
  - data.write
startup_tier: background  # 后台启动，不阻塞平台
config:
  ddw_gateway_url: "http://localhost:8000"
  storage:
    db_path: "data/industrial.db"
    retention_days: 90
  cache:
    max_buffer_size: 10000
    flush_interval: 60
```

#### 3.7.3 目录结构

```
ddw-industrial-data-access/
├── manifest.yaml
├── __init__.py              # 桥接入口 + register(app)
├── main.py                  # IndustrialDataAccessPlugin 主类
├── adapters/                # 协议适配器
│   ├── __init__.py
│   ├── base.py              # ProtocolAdapter 基类
│   ├── modbus_tcp.py        # Modbus TCP 适配器
│   ├── modbus_rtu.py        # Modbus RTU 适配器
│   ├── opc_ua.py            # OPC-UA 适配器
│   ├── mqtt_adapter.py      # MQTT 适配器
│   ├── http_rest.py         # HTTP/REST 适配器
│   ├── csv_excel.py         # CSV/Excel 适配器
│   └── jdbc.py              # JDBC 适配器
├── collector/               # 采集管线
│   ├── __init__.py
│   ├── pipeline.py          # Collector 调度器
│   ├── edge_processors.py   # 边缘预处理器
│   └── cache.py             # 本地缓存管理
├── rule_engine/             # 清洗标准化
│   ├── __init__.py
│   ├── cleaner.py           # DataCleaner 链式引擎
│   ├── steps.py             # 内置清洗步骤
│   └── llm_assistant.py     # LLM 辅助清洗
├── thing_model/             # 物模型
│   ├── __init__.py
│   ├── profiles.py          # DeviceProfile 模型
│   ├── templates/           # 行业模板
│   │   ├── manufacturing.py # 制造业模板
│   │   ├── food.py          # 食品模板
│   │   ├── pharma.py        # 医药模板
│   │   └── optical.py       # 光通信模板
│   └── manager.py           # 物模型管理器
├── storage/                 # 存储层
│   ├── __init__.py
│   ├── models.py            # SQLAlchemy ORM
│   ├── store.py             # DeviceDataStore
│   └── migrations.py        # 数据库迁移
├── requirements.txt
├── README.md
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_adapter_base.py
    ├── test_modbus_adapter.py
    ├── test_collector.py
    ├── test_cleaner.py
    ├── test_thing_model.py
    └── test_api.py
```

---

## 四、API 接口规格

### 4.1 REST API 端点清单

| 方法 | 路径 | 描述 | 请求体/参数 |
|:-----|:-----|:-----|:------------|
| `GET` | `/health` | 健康检查 | — |
| `GET` | `/devices` | 设备列表 | `?profile_id=&protocol=` |
| `POST` | `/devices` | 注册设备 | `{name, profile_id, protocol, endpoint, config}` |
| `GET` | `/devices/{id}` | 设备详情 | — |
| `PUT` | `/devices/{id}` | 更新设备 | `{name, config, tags}` |
| `DELETE` | `/devices/{id}` | 删除设备 | — |
| `GET` | `/devices/{id}/data` | 查询历史数据 | `?start=&end=&limit=1000` |
| `GET` | `/devices/{id}/latest` | 最新数据 | — |
| `GET` | `/profiles` | 设备画像模板列表 | — |
| `GET` | `/profiles/{id}` | 画像模板详情 | — |
| `POST` | `/profiles` | 创建画像模板 | 完整 DeviceProfile |
| `GET` | `/collectors/status` | 采集器状态 | — |
| `POST` | `/collectors/start` | 启动采集 | `{adapter_name}` |
| `POST` | `/collectors/stop` | 停止采集 | `{adapter_name}` |
| `POST` | `/cleaning-rules` | 创建清洗规则 | `{name, profile_id, steps[]}` |
| `GET` | `/cleaning-rules` | 清洗规则列表 | `?profile_id=` |
| `PUT` | `/cleaning-rules/{id}` | 更新规则 | `{steps[], enabled}` |
| `DELETE` | `/cleaning-rules/{id}` | 删除规则 | — |
| `POST` | `/ai/detect-anomalies` | AI异常检测 | `{device_id}` |
| `POST` | `/ai/recommend-rules` | AI推荐清洗规则 | `{data_description}` |
| `GET` | `/stats/summary` | 数据统计概览 | `?device_id=&period=` |

### 4.2 关键 API 示例

#### 注册设备

```http
POST /api/v1/plugins/industrial-data/devices
Content-Type: application/json

{
  "name": "CNC加工中心#3",
  "profile_id": "cnc_machine",
  "protocol": "modbus_tcp",
  "endpoint": "192.168.1.100:502",
  "config": {
    "unit_id": 1,
    "register_map": [
      {"name": "spindle_speed", "address": 0, "type": "int16", "unit": "rpm"},
      {"name": "spindle_temperature", "address": 1, "type": "float32",
       "unit": "℃", "scale": 0.1}
    ]
  },
  "tags": {"area": "车间A", "line": "产线1"}
}
```

#### 查询设备数据

```http
GET /api/v1/plugins/industrial-data/devices/cnc_192.168.1.100_1/data
    ?start=1720944000
    &end=1720947600
    &limit=500

Response:
{
  "device_id": "cnc_192.168.1.100_1",
  "total": 487,
  "data": [
    {
      "timestamp": 1720944000.000,
      "telemetry": {
        "spindle_speed": {"value": 8500, "unit": "rpm"},
        "spindle_temperature": {"value": 62.3, "unit": "℃"}
      },
      "quality_score": 0.98
    },
    ...
  ]
}
```

#### AI 异常检测

```http
POST /api/v1/plugins/industrial-data/ai/detect-anomalies
Content-Type: application/json

{
  "device_id": "cnc_192.168.1.100_1"
}

Response:
{
  "anomalies": [
    {
      "device_id": "cnc_192.168.1.100_1",
      "metric": "spindle_temperature",
      "anomaly_type": "drift",
      "description": "主轴温度在过去2小时内缓慢上升5.2℃，可能存在冷却液不足",
      "severity": "medium",
      "suggested_rule": "添加滑动窗口均值偏移检测（窗口30分钟，偏移阈值3℃）"
    }
  ],
  "recommendations": [
    "建议检查冷却液液位",
    "建议将温度告警阈值从80℃调整为75℃以提前预警"
  ]
}
```

---

## 五、技术约束与依赖

### 5.1 依赖清单

```txt
# requirements.txt

# 核心框架
fastapi>=0.104.0
pydantic>=2.0

# 协议适配器（按需安装）
pymodbus>=3.5.0           # Modbus TCP/RTU
asyncua>=0.9.9             # OPC-UA
paho-mqtt>=1.6.0           # MQTT
httpx>=0.25.0              # HTTP/REST
openpyxl>=3.1.0            # Excel
sqlalchemy>=2.0.0          # JDBC + ORM

# 存储（SQLite 内置，无需额外依赖）

# 工具
pyyaml>=6.0                # 配置解析
```

### 5.2 资源消耗评估

| 维度 | 评估值 | 说明 |
|:-----|:-------|:-----|
| **基础内存** | ~80 MB | 插件加载 + SQLite + 路由注册 |
| **运行时内存** | ~150 MB | 单次采集 100 台设备 |
| **峰值内存** | ~300 MB | 并发采集 + 清洗缓冲 |
| **CPU 常态** | < 5% | 轮询采集 + 写入 SQLite |
| **CPU 峰值** | ~15% | 批量清洗 + LLM 调用 |
| **磁盘** | ~500 MB/月 | 按 100 台设备，秒级采集 |
| **网络** | < 1 Mbps | Modbus/MQTT 局域网采集 |
| **LLM Token** | ~1000/次 | 异常检测/规则推荐（低频调用） |
| **评级** | **轻量级** | 基础 < 100MB / 无外部服务依赖 |

### 5.3 部署方案

#### 单机部署（Mac mini M4 / ECS 8GB）

```
Mac mini M4 (开发/测试):
├── DDW AI Hub Core (FastAPI)
├── ddw-industrial-data-access (本插件)
├── SQLite (本地文件)
└── 设备网络 (Modbus/MQTT 局域网)

ECS 8GB (生产):
├── DDW AI Hub Core (FastAPI + Caddy 反代)
├── ddw-industrial-data-access (本插件)
├── SQLite + WAL 模式
└── 设备网络 (VPN/专线连接工厂局域网)
```

#### 部署步骤

```bash
# 1. 安装协议适配器依赖（按需）
pip install pymodbus asyncua paho-mqtt httpx openpyxl

# 2. 配置设备接入
# 编辑 manifest.yaml 中的 config 部分

# 3. 重启 DDW Core
systemctl restart ddw-core

# 4. 通过 API 注册设备
curl -X POST http://localhost:8000/api/v1/plugins/industrial-data/devices \
  -H "Content-Type: application/json" \
  -d '{"name": "CNC#1", "profile_id": "cnc_machine",
       "protocol": "modbus_tcp", "endpoint": "192.168.1.100:502",
       "config": {"unit_id": 1, "register_map": [...]}}'

# 5. 启动采集
curl -X POST http://localhost:8000/api/v1/plugins/industrial-data/collectors/start \
  -H "Content-Type: application/json" \
  -d '{"adapter_name": "modbus_cnc_1"}'
```

---

## 六、与其他 DDW 插件的协作

### 6.1 事件驱动集成

```
ddw-industrial-data-access
    │
    ├── 发布: device.data.received → ddw-esg-* (消费数据生成ESG报告)
    ├── 发布: device.alarm → ddw-smart-cs (告警通知)
    └── 发布: device.offline → ddw-smart-cs (设备离线通知)

ddw-llm-gateway
    └── 提供: LLM 推理服务 ← ddw-industrial-data-access (AI异常检测)

ddw-token-manager
    └── 计量: LLM Token 消耗 ← ddw-industrial-data-access (AI清洗规则)
```

### 6.2 典型协作场景

**场景：光模块工厂 AI 质量预测**

```
1. ddw-industrial-data-access
   → Modbus TCP 采集光模块温度/光功率/电流
   → 每 5 秒采集，边缘预处理聚合为 1 分钟均值
   → 清洗标准化后存入 SQLite

2. ddw-llm-gateway
   → 接收 device.data.received 事件
   → 用 DeepSeek 分析光功率衰减趋势
   → 预测光模块寿命

3. ddw-smart-cs
   → 接收 device.alarm 事件
   → 通过钉钉/微信推送告警给维护人员

4. ddw-esg-report
   → 消费设备能耗数据
   → 计算碳排放指标
   → 生成 ESG 合规报告
```

---

## 七、风险与缓解

| 风险 | 影响 | 缓解措施 |
|:-----|:-----|:---------|
| SQLite 写入瓶颈 | 高频采集(>100台设备秒级)时写入延迟 | WAL 模式 + 异步写入队列 + 按小时聚合 |
| 协议适配器兼容性 | 不同厂家 PLC 的 Modbus 实现差异 | 寄存器映射表可配 + 自定义字节序 |
| 断网时数据丢失 | 工厂网络不稳定 | 本地缓存 10000 条 + CSV 备份 |
| LLM 调用成本 | AI清洗规则推荐消耗Token | 仅低频调用（设备注册时推荐一次） |
| 内存占用 | 边缘缓存堆积 | 缓冲区上限 10000 条 + FIFO 淘汰 |
| 安全风险 | 工厂内网设备暴露 | 仅支持局域网连接 + API 鉴权 |

---

## 八、实施路线图

| 阶段 | 内容 | 预估工时 |
|:-----|:-----|:---------|
| **Phase 1** | 核心框架 + Modbus TCP 适配器 + SQLite 存储 | 5 天 |
| **Phase 2** | MQTT + OPC-UA 适配器 + 边缘预处理器 | 4 天 |
| **Phase 3** | 清洗标准化引擎 + 物模型管理 | 3 天 |
| **Phase 4** | HTTP/REST + CSV/Excel + JDBC 适配器 | 3 天 |
| **Phase 5** | LLM 辅助清洗 + 行业模板 | 2 天 |
| **Phase 6** | API 完善 + 测试 + 文档 | 3 天 |
| **合计** | | **20 人天** |

---

## 九、总结

本文档设计了一个**轻量级、可扩展的工业设备数据接入层**，核心特点：

1. **六大协议全覆盖**：Modbus TCP/RTU、OPC-UA、MQTT、HTTP/REST、CSV/Excel、JDBC
2. **Telegraf 管线模型**：Input → Processor → Output，插件化适配器架构
3. **ThingsBoard 边缘计算**：轻量预处理器（过滤/聚合/告警），不依赖重型流引擎
4. **DG-IoT 物模型**：Attribute + Event + Service 三要素，行业模板覆盖制造业/食品/医药/光通信
5. **AI 增强**：LLM 辅助异常检测和清洗规则推荐，通过 DDW Gateway 统一调用
6. **极致轻量**：SQLite 存储，单机 8GB 可运行，无 Kafka/Flink/ES 等重型依赖
7. **DDW 原生集成**：继承 PluginBase，事件总线对接，可与 ESG/智能客服等插件协作
