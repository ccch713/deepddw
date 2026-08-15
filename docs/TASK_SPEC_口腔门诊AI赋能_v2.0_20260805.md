# 口腔门诊 AI 赋能系统 · 开发任务规约（TASK_SPEC）

> **版本**：v2.0 · 2026-08-05
> **目标客户**：武汉东华口腔青山店（沿港路27号，8:00-17:30，14 医生，电话 13797031993）
> **代码仓库**：`DDW底座平台/ddw-ai-hub/plugins/`
> **插件协议**：继承 `core.plugin_base.PluginBase`，目录下划线命名 `ddw_xxx`，含 `__init__.py`（PLUGIN_NAME + VERSION）+ `plugin.py`（Plugin 类 + setup 注册 router）
> **LLM 优先级**：MiniMax-M3（套餐内≈0 成本）→ DeepSeek fallback → 知识库兜底
> **关联 PRD**：`DDW底座平台/ddw-prd/PRD_口腔门诊AI赋能_v1.1_20260805.md`（产品层，已归档）

---

## 〇、全局依赖图

```
T0 ddw_talk_a1_asr（A1 录音采集 + whisper 转写）
  ↓
T1 ddw_clinical_asr（LLM 医疗实体抽取）
  ↓
T2 ddw_dental_emr（病历主插件 + 9 类模板）
  ↓  ↑ 依赖 T16 ddw_dental_emr_template_kit（模板套件）
T3 ddw_patient_crm ──→ T8 ddw_followup ──→ T11 ddw_marketing
T4 ddw_doctor_schedule
T5 ddw_payment ──→ T6 ddw_commission
T7 ddw_inventory
T9 ddw_member_vip
T10 ddw_kpi_dashboard（依赖 T3-T9 数据）
T11 ddw_marketing
T12 ddw_dental_imaging
T13 ddw_dental_sterilization
T14 ddw_informed_consent
T15 ddw_aggregated_pay（依赖 T5）
```

**STEP 2 周期（3 周 = 15 工作日）**：

| 周 | 任务 | 工作量 |
|:--|:--|:--|
| W1 前半 | T0（A1 录音采集） | 2.5d |
| W1 后半 | T1（LLM 抽取）+ T16（模板套件）+ T2（病历主插件） | 2.5d |
| W2 | T3（CRM）+ T4（排班）+ T5（支付）+ T6（提成） | 5d |
| W3 | T7（耗材）+ T8（回访）+ T9（会员）+ 联调 | 5d |

**STEP 3 周期（2.5 周 = 12.5 工作日）**：

| 周 | 任务 | 工作量 |
|:--|:--|:--|
| W4 | T10（报表）+ T11（营销） | 5d |
| W5 | T12（影像）+ T13（消毒） | 5d |
| W6 前半 | T14（知情同意）+ T15（聚合支付）+ 联调 | 2.5d |

---

## 〇'、DDW 插件协议速查（所有任务共用）

```
plugins/ddw_{name}/
├── __init__.py          # PLUGIN_NAME = "ddw_{name}"; VERSION = "0.1.0"
├── plugin.py            # class Plugin(PluginBase): def setup(self): self._router = router; self.app.include_router(router)
├── router.py            # FastAPI APIRouter(prefix="/api/v1/plugins/ddw_{name}")
├── models.py            # Pydantic 数据模型（可选）
├── kb.py                # RAG 知识库检索（可选）
├── knowledge/           # 知识库 md 文件（可选）
│   └── *.md
├── scripts/             # 预置数据/模板（可选）
│   └── *.json / *.yaml
├── tests/
│   └── test_{name}.py   # pytest 测试
└── manifest.yaml        # 插件元数据
```

**manifest.yaml 模板**：
```yaml
name: ddw_{name}
version: "0.1.0"
description: "{description}"
author: "DDW Team"
dependencies: []
```

**router.py 模板**：
```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/plugins/ddw_{name}", tags=["ddw_{name}"])

class HealthResponse(BaseModel):
    plugin: str
    version: str
    status: str

@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(plugin="ddw_{name}", version="0.1.0", status="ok")
```

---

## T0: ddw_talk_a1_asr（钉钉 Talk A1 录音采集 + Whisper 转写）

**依赖**：无（STEP 2 最先启动）
**工作量**：2.5 天

### 目录结构
```
plugins/ddw_talk_a1_asr/
├── __init__.py
├── plugin.py
├── router.py
├── transcriber.py        # whisper 转写核心逻辑
├── audio_queue/          # 待转写音频队列
│   └── .gitkeep
├── output/               # 转写结果输出（jsonl）
│   └── .gitkeep
├── config.py             # 配置管理
├── manifest.yaml
└── tests/
    └── test_talk_a1_asr.py
```

### 配置（config.py）
```python
import os
from pathlib import Path

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "ggml-medium.bin")  # 中文识别率 ~98%
WHISPER_MODEL_DIR = Path(os.getenv("WHISPER_MODEL_DIR", str(Path.home() / "models" / "whisper")))
WHISPER_CLI = os.getenv("WHISPER_CLI", "whisper-cli")  # brew install whisper-cpp
AUDIO_SAMPLE_RATE = 16000  # whisper 要求 16kHz 单声道
AUDIO_CHANNELS = 1
QUEUE_DIR = Path(__file__).parent / "audio_queue"
OUTPUT_DIR = Path(__file__).parent / "output"
MAX_CONCURRENT_JOBS = 3  # 同时转写任务上限
```

### 核心逻辑（transcriber.py）
```python
import subprocess
import json
import uuid
from pathlib import Path
from datetime import datetime

def transcribe_audio(audio_path: str, output_dir: str) -> dict:
    """
    输入：音频文件路径（wav/mp3/m4a）
    输出：转写结果 dict，含 text + segments + metadata
    """
    job_id = str(uuid.uuid4())[:8]
    output_prefix = Path(output_dir) / f"{job_id}"

    # whisper-cli 转写命令
    cmd = [
        str(config.WHISPER_CLI),
        "--model", str(config.WHISPER_MODEL_DIR / config.WHISPER_MODEL),
        "--language", "zh",
        "--output-format", "json",
        "--output-dir", str(output_dir),
        audio_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        raise RuntimeError(f"whisper-cli failed: {result.stderr}")

    # 读取 whisper 输出的 JSON
    json_path = Path(output_dir) / f"{Path(audio_path).stem}.json"
    if not json_path.exists():
        raise FileNotFoundError(f"whisper output not found: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        whisper_result = json.load(f)

    # 构建标准化输出
    segments = []
    for seg in whisper_result.get("segments", []):
        segments.append({
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"]
        })

    output = {
        "job_id": job_id,
        "audio_path": audio_path,
        "full_text": whisper_result.get("text", ""),
        "segments": segments,
        "language": whisper_result.get("language", "zh"),
        "transcribed_at": datetime.now().isoformat(),
        "model": config.WHISPER_MODEL
    }

    # 保存结果
    result_path = Path(output_dir) / f"{job_id}.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return output
```

### API 端点（router.py）

#### POST /api/v1/plugins/ddw_talk_a1_asr/upload
上传音频文件，异步转写。

**Request**：
```json
{
  "file": "<binary: audio file (wav/mp3/m4a/m4b)>",
  "doctor_id": "doc_001",
  "patient_name": "张三",
  "session_type": "consultation"  // consultation | follow_up | emergency
}
```
（实际用 `UploadFile` + `Form` 字段）

**Response**：
```json
{
  "job_id": "a1b2c3d4",
  "status": "queued",
  "message": "音频已接收，正在转写中"
}
```

#### GET /api/v1/plugins/ddw_talk_a1_asr/status/{job_id}
查询转写状态。

**Response（转写中）**：
```json
{
  "job_id": "a1b2c3d4",
  "status": "transcribing",
  "progress": 0.6
}
```

**Response（完成）**：
```json
{
  "job_id": "a1b2c3d4",
  "status": "completed",
  "full_text": "患者说牙痛三天了，晚上加重……",
  "segments": [
    {"start": 0.0, "end": 3.5, "text": "患者说牙痛三天了"},
    {"start": 3.5, "end": 7.2, "text": "晚上加重，冷热刺激痛"}
  ],
  "duration_seconds": 185,
  "output_path": "/opt/ddw/ddw-ai-hub/plugins/ddw_talk_a1_asr/output/a1b2c3d4.json"
}
```

**Response（失败）**：
```json
{
  "job_id": "a1b2c3d4",
  "status": "failed",
  "error": "whisper-cli model not found"
}
```

#### GET /api/v1/plugins/ddw_talk_a1_asr/health
```json
{"plugin":"ddw_talk_a1_asr","version":"0.1.0","status":"ok","whisper_model":"ggml-medium.bin","queue_size":2}
```

### 测试用例（test_talk_a1_asr.py）
```python
import pytest
from pathlib import Path

# T0-1: 上传音频文件返回 job_id
# T0-2: 查询不存在的 job_id 返回 404
# T0-3: health 返回 status=ok + whisper_model 非空
# T0-4: transcribe_audio 接口：mock whisper-cli，验证输出 JSON 结构
# T0-5: 并发上传 3 个文件，全部转写成功
# T0-6: 上传非音频文件（txt）返回 400
# T0-7: 超大音频文件（>100MB）返回 413
```

### 验收标准
- (a) 1 个医生上传 A1 录音（3-5 分钟），转写完成 ≤ 60 秒
- (b) 中文识别率 ≥ 95%（口腔医学术语）
- (c) 3 个并发任务全部成功
- (d) job_id 查询状态准确

---

## T1: ddw_clinical_asr（LLM 医疗实体抽取）

**依赖**：T0（转写文本）
**工作量**：1 天（与 T16、T2 并行）

### 目录结构
```
plugins/ddw_clinical_asr/
├── __init__.py
├── plugin.py
├── router.py
├── extractor.py          # LLM 实体抽取核心逻辑
├── prompts/              # 9 类诊疗抽取 prompt
│   ├── orthodontics.txt   # 正畸
│   ├── pulp_open.txt      # 开髓
│   ├── extraction.txt     # 拔牙
│   ├── cosmetic.txt       # 医美
│   ├── root_canal.txt     # 根管
│   ├── implant.txt        # 种植
│   ├── prosthesis.txt     # 修复
│   ├── periodontal.txt    # 牙周
│   └── pediatric.txt      # 儿牙
├── schema.py             # 9 类结构化输出 schema
├── manifest.yaml
└── tests/
    └── test_clinical_asr.py
```

### 诊疗类型枚举（schema.py）
```python
from enum import Enum

class TreatmentType(str, Enum):
    ORTHODONTICS = "orthodontics"      # 正畸
    PULP_OPEN = "pulp_open"            # 开髓
    EXTRACTION = "extraction"          # 拔牙
    COSMETIC = "cosmetic"              # 医美（贴面/美白/树脂）
    ROOT_CANAL = "root_canal"          # 根管充填
    IMPLANT = "implant"                # 种植
    PROSTHESIS = "prosthesis"          # 修复（冠/桥/嵌体）
    PERIODONTAL = "periodontal"        # 牙周
    PEDIATRIC = "pediatric"            # 儿牙
```

### 通用抽取输出 schema（schema.py）
```python
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

class TreatmentType(str, Enum):
    ORTHODONTICS = "orthodontics"
    PULP_OPEN = "pulp_open"
    EXTRACTION = "extraction"
    COSMETIC = "cosmetic"
    ROOT_CANAL = "root_canal"
    IMPLANT = "implant"
    PROSTHESIS = "prosthesis"
    PERIODONTAL = "periodontal"
    PEDIATRIC = "pediatric"

class ExtractionResult(BaseModel):
    treatment_type: TreatmentType
    confidence: float = Field(ge=0, le=1)
    chief_complaint: str = Field(description="主诉")
    present_illness: str = Field(description="现病史")
    past_history: Optional[str] = None
    examination: dict = Field(description="检查结果（key-value）")
    diagnosis: str = Field(description="诊断")
    treatment_plan: str = Field(description="治疗计划")
    special_findings: dict = Field(default_factory=dict, description="诊疗类型特有字段")
    urgency: str = Field(default="routine", description="routine|urgent|emergency")
    raw_transcript_ref: str = Field(description="关联的转写 job_id")
```

### 抽取 Prompt 模板（prompts/extraction_system.txt）
```
你是一位口腔医学病历助手。根据以下医患对话转写文本，提取结构化病历信息。

输出格式：严格 JSON，不要添加任何解释文字。

提取规则：
1. treatment_type：判断诊疗类型（orthodontics/pulp_open/extraction/cosmetic/root_canal/implant/prosthesis/periodontal/pediatric）
2. confidence：你对类型判断的置信度（0-1）
3. chief_complaint：患者的主诉（一句话）
4. present_illness：现病史（包括持续时间、加重因素、缓解因素）
5. past_history：既往史（如有）
6. examination：检查结果（键值对，如 {"tooth_position": "左上6", "mobility": "II度"}）
7. diagnosis：诊断
8. treatment_plan：治疗计划
9. special_findings：该诊疗类型的特有字段（见下方各类型要求）
10. urgency：routine/urgent/emergency

{type_specific_rules}

重要：
- 如果转写文本中信息不足，用 "待补充" 标记
- 不要编造信息
- 口腔专业术语用标准中文表述
```

### 各类型特有抽取规则（prompts/ 目录下各文件）

**orthodontics.txt（正畸）**：
```
special_findings 必须包含：
- malocclusion_type: 错合类型（crowding/spacing/crossbite/deepbite/openbite/protrusion）
- angle_class: 安氏分类（I/II/III）
- arch_form: 牙弓形态（oval/tapered/square）
- overjet: 覆盖（mm）
- overbite: 覆合（mm）
- crowe_index: Crowe 指数（轻度/中度/重度）
- treatment_modality: 矫治器选择（fixed/removable/invisible/combined）
- estimated_duration: 预估疗程（月）
- extraction_needed: 是否需要拔牙（true/false）
```

**extraction.txt（拔牙）**：
```
special_findings 必须包含：
- tooth_position: 牙位（如 "左下8"）
- extraction_reason: 拔牙原因（impaction/caries/periodontal/orthodontic/trauma）
- difficulty_level: 难度（simple/surgical/complex）
- anesthesia_type: 麻醉方式（local/intraligamentary/inferior_alveolar）
- anticoagulant_use: 是否使用抗凝药（true/false + 药名）
- bleeding_amount: 术中出血量（ml 估计）
- socket_management: 牙槽窝处理（normal/suturing/bone_graft）
- contraindications: 禁忌症检查结果
```

**implant.txt（种植）**：
```
special_findings 必须包含：
- missing_tooth: 缺失牙位
- edentulous_period: 缺牙时间（月/年）
- bone_quality: 骨质评估（I/II/III/IV）
- bone_volume: 骨量评估（sufficient/insufficient）
- implant_brand: 种植体品牌
- implant_size: 种植体规格（直径×长度mm）
- loading_protocol: 负荷方式（immediate/delayed/conventional）
- stages: 阶段（phase_1/phase_2/prosthetic）
- cbct_performed: CBCT 是否完成（true/false）
```

### 核心逻辑（extractor.py）
```python
import json
from typing import Optional

async def extract_medical_entities(
    transcript: str,
    job_id: str,
    treatment_hint: Optional[str] = None  # 可选：如果已有类型判断
) -> dict:
    """
    输入：转写文本 + job_id
    输出：结构化 ExtractionResult dict

    流程：
    1. 构建 prompt（system + user）
    2. 调用 LLM（MiniMax-M3 优先）
    3. 解析 JSON 输出
    4. 校验 schema
    5. 返回结构化结果
    """
    # 1. 选择 prompt
    system_prompt = load_prompt("extraction_system.txt")
    if treatment_hint:
        type_rules = load_prompt(f"{treatment_hint}.txt")
        system_prompt = system_prompt.replace("{type_specific_rules}", type_rules)
    else:
        # 先判断类型，再加载对应规则
        system_prompt = system_prompt.replace(
            "{type_specific_rules}",
            "请先判断诊疗类型，然后按该类型的规则提取 special_findings。"
        )

    # 2. 调用 LLM
    llm_response = await call_llm(
        system=system_prompt,
        user=f"以下是一段口腔诊疗对话的转写文本：\n\n{transcript}\n\n请提取结构化病历信息。"
    )

    # 3. 解析 JSON
    try:
        result = json.loads(llm_response)
    except json.JSONDecodeError:
        # 尝试从 markdown code block 中提取
        import re
        match = re.search(r'```json\n(.*?)```', llm_response, re.DOTALL)
        if match:
            result = json.loads(match.group(1))
        else:
            raise ValueError(f"LLM 返回非 JSON：{llm_response[:200]}")

    # 4. 校验 schema
    validated = ExtractionResult(**result)
    validated.raw_transcript_ref = job_id

    return validated.dict()
```

### API 端点

#### POST /api/v1/plugins/ddw_clinical_asr/extract
```json
// Request
{
  "transcript_text": "患者说牙痛三天了，晚上加重，冷热刺激痛……",
  "job_id": "a1b2c3d4",
  "treatment_hint": "pulp_open"  // 可选
}

// Response
{
  "status": "ok",
  "result": {
    "treatment_type": "pulp_open",
    "confidence": 0.92,
    "chief_complaint": "左下后牙疼痛三天，夜间加重",
    "present_illness": "三天前开始自发性疼痛，夜间加重，冷热刺激痛，咬合不适",
    "past_history": null,
    "examination": {
      "tooth_position": "左下6",
      "caries_location": "近中邻面",
      "tenderness_to_percussion": true,
      "thermal_test": "延迟性锐痛",
      "mobility": "0度"
    },
    "diagnosis": "左下6 急性牙髓炎",
    "treatment_plan": "根管治疗，分 2-3 次完成",
    "special_findings": {
      "pulp_vitality": "alive, inflamed",
      "estimated_canals": 3
    },
    "urgency": "urgent",
    "raw_transcript_ref": "a1b2c3d4"
  }
}
```

#### POST /api/v1/plugins/ddw_clinical_asr/classify
纯分类（不抽取），返回 treatment_type + confidence。

#### GET /api/v1/plugins/ddw_clinical_asr/prompts
列出所有可用的抽取 prompt 文件。

#### GET /api/v1/plugins/ddw_clinical_asr/health
```json
{"plugin":"ddw_clinical_asr","version":"0.1.0","status":"ok","available_types":9}
```

### 测试用例
```python
# T1-1: extract 接口，传入模拟转写文本，返回 ExtractionResult 结构
# T1-2: 传入牙痛文本，treatment_type 判断为 pulp_open
# T1-3: 传入拔牙文本，treatment_type 判断为 extraction，special_findings 含 anticoagulant_use
# T1-4: extract 接口，LLM 返回非法 JSON，触发 fallback 解析
# T1-5: classify 接口，返回 confidence > 0.8
# T1-6: 信息不足时，字段值为 "待补充"（不报错）
# T1-7: extract 接口性能：输入 2000 字文本，响应 ≤ 10 秒
# T1-8: 9 种诊疗类型各有一条正向测试用例
```

---

## T16: ddw_dental_emr_template_kit（9 类诊疗病历模板套件）

**依赖**：无
**工作量**：1 天（与 T0 并行）

### 目录结构
```
plugins/ddw_dental_emr_template_kit/
├── __init__.py
├── plugin.py
├── router.py
├── templates/            # 9 个 YAML 模板
│   ├── orthodontics.yaml
│   ├── pulp_open.yaml
│   ├── extraction.yaml
│   ├── cosmetic.yaml
│   ├── root_canal.yaml
│   ├── implant.yaml
│   ├── prosthesis.yaml
│   ├── periodontal.yaml
│   └── pediatric.yaml
├── validators/           # 9 个字段校验器
│   └── {type}.py
├── manifest.yaml
└── tests/
    └── test_template_kit.py
```

### YAML 模板格式（以 extraction.yaml 为例）
```yaml
type: extraction
name: 拔牙病历
version: "1.0"
required_fields:
  - chief_complaint
  - present_illness
  - tooth_position
  - extraction_reason
  - difficulty_level
  - anesthesia_type
  - anticoagulant_use
  - contraindications

fields:
  chief_complaint:
    label: 主诉
    type: text
    max_length: 200
    required: true
  present_illness:
    label: 现病史
    type: text
    max_length: 1000
    required: true
  past_history:
    label: 既往史
    type: text
    max_length: 500
    required: false
  tooth_position:
    label: 牙位
    type: select
    options:
      - "右上1-8"
      - "左上1-8"
      - "右下1-8"
      - "左下1-8"
    required: true
  extraction_reason:
    label: 拔牙原因
    type: select
    options: [impaction, caries, periodontal, orthodontic, trauma]
    required: true
  difficulty_level:
    label: 难度评估
    type: select
    options: [simple, surgical, complex]
    required: true
  anesthesia_type:
    label: 麻醉方式
    type: select
    options: [local, intraligamentary, inferior_alveolar, general]
    required: true
  anticoagulant_use:
    label: 抗凝药使用
    type: boolean
    required: true
  anticoagulant_drug:
    label: 抗凝药物名称
    type: text
    required_if: "anticoagulant_use == true"
  contraindications:
    label: 禁忌症检查
    type: text
    required: true
  intraoperative_notes:
    label: 术中记录
    type: text
    max_length: 1000
    required: false
  postop_instructions:
    label: 术后医嘱
    type: text
    max_length: 500
    required: true

display_order:
  - chief_complaint
  - present_illness
  - past_history
  - tooth_position
  - extraction_reason
  - difficulty_level
  - anesthesia_type
  - anticoagulant_use
  - anticoagulant_drug
  - contraindications
  - intraoperative_notes
  - postop_instructions
```

### orthodontics.yaml（正畸，部分字段）
```yaml
type: orthodontics
name: 正畸病历
required_fields:
  - chief_complaint
  - malocclusion_type
  - angle_class
  - overjet
  - overbite
  - crowe_index
  - treatment_modality
  - estimated_duration

fields:
  malocclusion_type:
    label: 错合类型
    type: select
    options: [crowding, spacing, crossbite, deepbite, openbite, protrusion]
  angle_class:
    label: 安氏分类
    type: select
    options: [I, II_1, II_2, III]
  overjet:
    label: 覆盖(mm)
    type: number
    unit: mm
  overbite:
    label: 覆合(mm)
    type: number
    unit: mm
  crowe_index:
    label: Crowe 指数
    type: select
    options: [mild, moderate, severe]
  arch_form:
    label: 牙弓形态
    type: select
    options: [oval, tapered, square]
  treatment_modality:
    label: 矫治方案
    type: select
    options: [fixed, removable, invisible, combined]
  extraction_needed:
    label: 是否拔牙
    type: boolean
  estimated_duration:
    label: 预估疗程(月)
    type: number
    unit: months
```

### API 端点
```
GET  /api/v1/plugins/ddw_dental_emr_template_kit/templates          # 列出所有模板
GET  /api/v1/plugins/ddw_dental_emr_template_kit/templates/{type}   # 获取单个模板
GET  /api/v1/plugins/ddw_dental_emr_template_kit/health
```

### 测试用例
```python
# T16-1: 列出 9 个模板，type 不重复
# T16-2: 获取 extraction 模板，required_fields 含 anticoagulant_use
# T16-3: 获取 orthodontics 模板，required_fields 含 angle_class
# T16-4: 获取不存在的类型返回 404
# T16-5: 所有模板 YAML 格式合法（yaml.safe_load 不报错）
# T16-6: 每个模板至少 8 个字段
# T16-7: 所有 select 类型字段的 options 非空
```

---

## T2: ddw_dental_emr（病历主插件）

**依赖**：T1（实体抽取）、T16（模板套件）
**工作量**：0.5 天（W1 后半）

### 目录结构
```
plugins/ddw_dental_emr/
├── __init__.py
├── plugin.py
├── router.py
├── models.py             # 病历数据模型
├── store.py              # 病历存储（SQLite）
├── manifest.yaml
└── tests/
    └── test_dental_emr.py
```

### 数据模型（models.py）
```python
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

class DentalRecord(BaseModel):
    id: Optional[str] = None
    patient_id: str                            # 关联 ddw_patient_crm
    doctor_id: str                             # 关联 ddw_doctor_schedule
    treatment_type: str                        # 9 类之一
    chief_complaint: str
    present_illness: str
    past_history: Optional[str] = None
    examination: Dict[str, Any] = {}
    diagnosis: str
    treatment_plan: str
    special_findings: Dict[str, Any] = {}      # 各类型特有字段
    urgency: str = "routine"
    status: str = "draft"                      # draft | reviewed | finalized
    transcript_job_id: Optional[str] = None    # 关联 ddw_talk_a1_asr
    images: List[str] = []                     # 关联 ddw_dental_imaging
    notes: Optional[str] = None                # 医生微调备注
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class RecordListResponse(BaseModel):
    total: int
    records: List[DentalRecord]
    page: int = 1
    page_size: int = 20
```

### 存储（store.py）
```python
import sqlite3
import json
from datetime import datetime
from typing import List, Optional

class DentalRecordStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dental_records (
                    id TEXT PRIMARY KEY,
                    patient_id TEXT NOT NULL,
                    doctor_id TEXT NOT NULL,
                    treatment_type TEXT NOT NULL,
                    chief_complaint TEXT NOT NULL,
                    present_illness TEXT NOT NULL,
                    past_history TEXT,
                    examination TEXT,  -- JSON
                    diagnosis TEXT NOT NULL,
                    treatment_plan TEXT NOT NULL,
                    special_findings TEXT,  -- JSON
                    urgency TEXT DEFAULT 'routine',
                    status TEXT DEFAULT 'draft',
                    transcript_job_id TEXT,
                    images TEXT,  -- JSON array
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_records_patient
                ON dental_records(patient_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_records_doctor
                ON dental_records(doctor_id)
            """)

    def create(self, record: dict) -> dict:
        now = datetime.now().isoformat()
        record["id"] = record.get("id") or f"emr_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        record["created_at"] = now
        record["updated_at"] = now
        record["examination"] = json.dumps(record.get("examination", {}), ensure_ascii=False)
        record["special_findings"] = json.dumps(record.get("special_findings", {}), ensure_ascii=False)
        record["images"] = json.dumps(record.get("images", []), ensure_ascii=False)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO dental_records
                   (id, patient_id, doctor_id, treatment_type, chief_complaint,
                    present_illness, past_history, examination, diagnosis,
                    treatment_plan, special_findings, urgency, status,
                    transcript_job_id, images, notes, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                tuple(record[k] for k in [
                    "id", "patient_id", "doctor_id", "treatment_type",
                    "chief_complaint", "present_illness", "past_history",
                    "examination", "diagnosis", "treatment_plan",
                    "special_findings", "urgency", "status",
                    "transcript_job_id", "images", "notes",
                    "created_at", "updated_at"
                ])
            )
        record["examination"] = json.loads(record["examination"]) if isinstance(record["examination"], str) else record["examination"]
        record["special_findings"] = json.loads(record["special_findings"]) if isinstance(record["special_findings"], str) else record["special_findings"]
        record["images"] = json.loads(record["images"]) if isinstance(record["images"], str) else record["images"]
        return record

    def get(self, record_id: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM dental_records WHERE id=?", (record_id,)).fetchone()
            if row:
                d = dict(row)
                d["examination"] = json.loads(d["examination"]) if d["examination"] else {}
                d["special_findings"] = json.loads(d["special_findings"]) if d["special_findings"] else {}
                d["images"] = json.loads(d["images"]) if d["images"] else []
                return d
        return None

    def list_by_patient(self, patient_id: str, page: int = 1, page_size: int = 20) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            total = conn.execute("SELECT COUNT(*) FROM dental_records WHERE patient_id=?", (patient_id,)).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM dental_records WHERE patient_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (patient_id, page_size, (page - 1) * page_size)
            ).fetchall()
            records = []
            for row in rows:
                d = dict(row)
                d["examination"] = json.loads(d["examination"]) if d["examination"] else {}
                d["special_findings"] = json.loads(d["special_findings"]) if d["special_findings"] else {}
                d["images"] = json.loads(d["images"]) if d["images"] else []
                records.append(d)
            return {"total": total, "records": records, "page": page, "page_size": page_size}

    def update_status(self, record_id: str, status: str, notes: str = None) -> Optional[dict]:
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            if notes:
                conn.execute("UPDATE dental_records SET status=?, notes=?, updated_at=? WHERE id=?",
                           (status, notes, now, record_id))
            else:
                conn.execute("UPDATE dental_records SET status=?, updated_at=? WHERE id=?",
                           (status, now, record_id))
        return self.get(record_id)
```

### API 端点（router.py）

#### POST /api/v1/plugins/ddw_dental_emr/records
创建病历（从实体抽取结果 + 医生微调）。

**Request**：
```json
{
  "patient_id": "pt_001",
  "doctor_id": "doc_001",
  "treatment_type": "extraction",
  "chief_complaint": "左下后牙疼痛三天",
  "present_illness": "三天前开始自发性疼痛……",
  "past_history": "高血压病史，服用氨氯地平",
  "examination": {"tooth_position": "左下8", "mobility": "I度"},
  "diagnosis": "左下8 近中阻生",
  "treatment_plan": "微创拔除左下8",
  "special_findings": {"anticoagulant_use": false, "difficulty_level": "simple"},
  "urgency": "routine",
  "transcript_job_id": "a1b2c3d4"
}
```

**Response**：`201 Created` + DentalRecord

#### GET /api/v1/plugins/ddw_dental_emr/records/{id}
获取单条病历。

#### GET /api/v1/plugins/ddw_dental_emr/records?patient_id=pt_001
按患者查询病历列表（分页）。

#### PATCH /api/v1/plugins/ddw_dental_emr/records/{id}/status
更新病历状态（draft → reviewed → finalized）。

**Request**：
```json
{"status": "reviewed", "notes": "医生已审核，字段无误"}
```

#### POST /api/v1/plugins/ddw_dental_emr/from-transcript
**核心端点**：从转写 job_id 一键生成病历草稿。

**Request**：
```json
{
  "transcript_job_id": "a1b2c3d4",
  "patient_id": "pt_001",
  "doctor_id": "doc_001"
}
```

**内部流程**：
1. 调用 T0 的 output 获取转写文本
2. 调用 T1 的 /extract 获取结构化实体
3. 加载 T16 的模板进行字段校验
4. 生成病历草稿（status=draft）
5. 返回完整病历

**Response**：
```json
{
  "status": "ok",
  "record": { ... DentalRecord ... },
  "validation": {
    "missing_fields": [],
    "warnings": ["anticoagulant_drug 字段缺失，建议补充"]
  }
}
```

#### GET /api/v1/plugins/ddw_dental_emr/templates
代理 T16 的模板列表。

#### GET /api/v1/plugins/ddw_dental_emr/health
```json
{"plugin":"ddw_dental_emr","version":"0.1.0","status":"ok","total_records":156,"template_count":9}
```

### 测试用例
```python
# T2-1: 创建病历，返回 201 + id 非空
# T2-2: 获取病历，字段完整
# T2-3: 按 patient_id 查询列表，分页正确
# T2-4: 更新状态 draft → reviewed → finalized
# T2-5: from-transcript 端到端（mock T0+T1），返回完整病历
# T2-6: from-transcript 缺少 patient_id 返回 422
# T2-7: 查询不存在的 record_id 返回 404
# T2-8: 牙周病历 special_findings 含 pd_values 字段
# T2-9: 种植病历 special_findings 含 implant_brand 字段
```

---

## T3: ddw_patient_crm（患者档案 CRM）

**依赖**：无
**工作量**：1 天

### 数据模型
```python
class Patient(BaseModel):
    id: Optional[str] = None
    name: str                                  # 患者姓名
    phone: str                                 # 手机号（唯一）
    gender: Optional[str] = None               # male/female
    birth_date: Optional[str] = None           # YYYY-MM-DD
    source: str = "unknown"                    # old_patient/referral/online/walk_in
    tags: List[str] = []                       # 自定义标签
    allergies: List[str] = []                  # 过敏史
    medical_history: Optional[str] = None      # 全身病史
    notes: Optional[str] = None                # 备注
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
```

### API 端点
```
POST   /api/v1/plugins/ddw_patient_crm/patients          # 创建患者
GET    /api/v1/plugins/ddw_patient_crm/patients/{id}     # 获取患者
GET    /api/v1/plugins/ddw_patient_crm/patients           # 搜索患者（name/phone/tag）
PATCH  /api/v1/plugins/ddw_patient_crm/patients/{id}     # 更新患者
GET    /api/v1/plugins/ddw_patient_crm/patients/{id}/visits  # 患者就诊记录（关联 T2）
GET    /api/v1/plugins/ddw_patient_crm/stats              # 统计：总患者数/本月新增/来源分布
GET    /api/v1/plugins/ddw_patient_crm/health
```

### 存储：SQLite，表 `patients`，字段对应 Pydantic 模型。phone 字段建 UNIQUE 索引。

### 测试用例
```python
# T3-1: 创建患者，phone 唯一，重复 phone 返回 409
# T3-2: 按 name 模糊搜索（LIKE '%关键词%'）
# T3-3: 按 phone 精确搜索
# T3-4: 按 tag 筛选
# T3-5: 获取患者就诊记录（关联 dental_records 表）
# T3-6: stats 返回本月新增数量
# T3-7: 更新患者信息（name/phone/tags）
# T3-8: patient 创建 → 关联病历 → 查看就诊记录（端到端）
```

---

## T4: ddw_doctor_schedule（医生与排班）

**依赖**：无
**工作量**：1 天

### 数据模型
```python
class Doctor(BaseModel):
    id: Optional[str] = None
    name: str
    title: Optional[str] = None               # 主治医师/副主任医师
    specialty: List[str] = []                  # 擅长领域
    phone: Optional[str] = None               # 内部联系方式
    is_active: bool = True
    created_at: Optional[datetime] = None

class ScheduleSlot(BaseModel):
    id: Optional[str] = None
    doctor_id: str
    date: str                                  # YYYY-MM-DD
    start_time: str                            # HH:MM
    end_time: str                              # HH:MM
    slot_type: str = "normal"                  # normal | on_call | off | leave
    max_patients: int = 10                     # 该时段最大接诊量
    booked_count: int = 0                      # 已预约人数
    created_at: Optional[datetime] = None
```

### API 端点
```
POST   /api/v1/plugins/ddw_doctor_schedule/doctors            # 添加医生
GET    /api/v1/plugins/ddw_doctor_schedule/doctors            # 列出所有医生
PATCH  /api/v1/plugins/ddw_doctor_schedule/doctors/{id}       # 更新医生
POST   /api/v1/plugins/ddw_doctor_schedule/slots              # 创建排班（批量）
GET    /api/v1/plugins/ddw_doctor_schedule/slots?date=2026-08-12  # 查看某日排班
PATCH  /api/v1/plugins/ddw_doctor_schedule/slots/{id}         # 更新排班（调班）
GET    /api/v1/plugins/ddw_doctor_schedule/doctors/{id}/slots?week=2026-W33  # 某医生周排班
GET    /api/v1/plugins/ddw_doctor_schedule/health
```

### 测试用例
```python
# T4-1: 添加 14 个医生，list 返回 14 条
# T4-2: 批量创建一周排班（14 医生 × 7 天 × 3 时段）
# T4-3: 查看某日排班，按 start_time 排序
# T4-4: 调班（slot_type 从 normal 改为 leave）
# T4-5: 检查冲突（同医生同时段不能有两个 normal slot）
# T4-6: 某医生周排班含 off/leave 标记
# T4-7: max_patients 限制（booked_count 达到后该 slot 不可选）
```

---

## T5: ddw_payment（收费与支付）

**依赖**：无
**工作量**：1 天

### 数据模型
```python
class PaymentRecord(BaseModel):
    id: Optional[str] = None
    patient_id: str
    doctor_id: str
    items: List[PaymentItem]                   # 收费项目
    total_amount: float                        # 总金额
    discount_amount: float = 0.0               # 优惠金额
    actual_amount: float                       # 实收金额
    payment_method: str                        # cash/wechat/alipay/card
    status: str = "pending"                    # pending | paid | refunded
    paid_at: Optional[datetime] = None
    receipt_number: Optional[str] = None       # 收据号
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

class PaymentItem(BaseModel):
    item_name: str                             # 项目名称
    quantity: int = 1
    unit_price: float
    subtotal: float
    treatment_type: Optional[str] = None       # 关联 9 类诊疗
```

### API 端点
```
POST   /api/v1/plugins/ddw_payment/records           # 创建收费记录
GET    /api/v1/plugins/ddw_payment/records/{id}      # 获取单条
GET    /api/v1/plugins/ddw_payment/records            # 查询列表（日期/患者/状态）
POST   /api/v1/plugins/ddw_payment/records/{id}/pay   # 确认收款
POST   /api/v1/plugins/ddw_payment/records/{id}/refund # 退款
GET    /api/v1/plugins/ddw_payment/daily-summary?date=2026-08-12  # 日结汇总
GET    /api/v1/plugins/ddw_payment/health
```

### 日结汇总 response
```json
{
  "date": "2026-08-12",
  "total_income": 12500.00,
  "by_method": {
    "wechat": 8000.00,
    "alipay": 3000.00,
    "cash": 1500.00
  },
  "transaction_count": 23,
  "refund_count": 1,
  "refund_amount": 200.00
}
```

### 测试用例
```python
# T5-1: 创建收费记录，total_amount = sum(items.subtotal)
# T5-2: 确认收款，status → paid，paid_at 非空
# T5-3: 退款，status → refunded，refund_amount ≤ actual_amount
# T5-4: 日结汇总：按支付方式分组
# T5-5: 查询日期范围内的收费记录
# T5-6: 收据号自动生成（格式：R{YYYYMMDD}{序号}）
```

---

## T6: ddw_commission（提成核算）

**依赖**：T5（收费数据）
**工作量**：1 天

### 数据模型
```python
class CommissionRule(BaseModel):
    id: Optional[str] = None
    treatment_type: str                        # 诊疗类型（或 "general"）
    doctor_id: Optional[str] = None            # None = 适用于所有医生
    percentage: float                          # 提成比例（0.0-1.0）
    min_amount: float = 0.0                    # 最低提成金额
    is_active: bool = True
    created_at: Optional[datetime] = None

class CommissionRecord(BaseModel):
    id: Optional[str] = None
    doctor_id: str
    period: str                                # YYYY-MM
    total_income: float                        # 该医生当月总创收
    commission_amount: float                   # 提成金额
    rule_applied: str                          # 使用的规则 ID
    status: str = "pending"                    # pending | confirmed | paid
    confirmed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
```

### API 端点
```
POST   /api/v1/plugins/ddw_commission/rules              # 创建提成规则
GET    /api/v1/plugins/ddw_commission/rules              # 列出规则
PATCH  /api/v1/plugins/ddw_commission/rules/{id}         # 更新规则
POST   /api/v1/plugins/ddw_commission/calculate?period=2026-08  # 计算月度提成
GET    /api/v1/plugins/ddw_commission/records?period=2026-08  # 查看月度提成
POST   /api/v1/plugins/ddw_commission/records/{id}/confirm  # 确认提成
GET    /api/v1/plugins/ddw_commission/health
```

### calculate 内部逻辑
1. 读取当月所有 paid 状态的 PaymentRecord
2. 按 doctor_id 分组
3. 每个医生：按 treatment_type 匹配 CommissionRule
4. 提成金额 = total_income × percentage
5. 生成 CommissionRecord 列表

### 测试用例
```python
# T6-1: 创建规则（extraction 15%），计算后提成 = extraction 收入 × 0.15
# T6-2: 同一医生多条收费，提成合并计算
# T6-3: 多个医生分别计算
# T6-4: 无匹配规则时提成为 0（不报错）
# T6-5: 确认提成后 status → confirmed
# T6-6: min_amount 兜底：提成低于 min_amount 时按 min_amount 计算
```

---

## T7: ddw_inventory（耗材管理）

**依赖**：无
**工作量**：1 天

### 数据模型
```python
class InventoryItem(BaseModel):
    id: Optional[str] = None
    name: str                                  # 耗材名称
    category: str                              # consumable/equipment/disposable
    quantity: int = 0                          # 当前库存
    unit: str = "个"                            # 计量单位
    min_quantity: int = 0                      # 最低库存预警
    expiry_date: Optional[str] = None          # 有效期 YYYY-MM-DD
    supplier: Optional[str] = None
    unit_cost: float = 0.0                     # 单价
    location: Optional[str] = None             # 存放位置
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class InventoryLog(BaseModel):
    id: Optional[str] = None
    item_id: str
    action: str                                # in | out | adjust
    quantity_change: int                       # 正数入库/负数出库
    reason: Optional[str] = None               # 采购/领用/盘点/报损
    operator: Optional[str] = None
    created_at: Optional[datetime] = None
```

### API 端点
```
POST   /api/v1/plugins/ddw_inventory/items              # 添加耗材
GET    /api/v1/plugins/ddw_inventory/items              # 列表
PATCH  /api/v1/plugins/ddw_inventory/items/{id}         # 更新
POST   /api/v1/plugins/ddw_inventory/items/{id}/in      # 入库
POST   /api/v1/plugins/ddw_inventory/items/{id}/out     # 出库
GET    /api/v1/plugins/ddw_inventory/alerts             # 预警（库存不足 + 即将过期）
GET    /api/v1/plugins/ddw_inventory/logs?item_id=xxx   # 操作日志
GET    /api/v1/plugins/ddw_inventory/health
```

### alerts 内部逻辑
- **库存不足**：quantity ≤ min_quantity
- **即将过期**：expiry_date 在未来 30 天内
- 返回两个列表：`low_stock: [...]` + `expiring_soon: [...]`

### 测试用例
```python
# T7-1: 添加耗材，入库 +100，quantity = 100
# T7-2: 出库 -10，quantity = 90
# T7-3: 出库 -200（超出库存），返回 400
# T7-4: alerts 含 low_stock（quantity ≤ min_quantity）
# T7-5: alerts 含 expiring_soon（30 天内过期）
# T7-6: 操作日志记录完整（action + quantity_change + reason + timestamp）
```

---

## T8: ddw_followup（回访与复诊提醒）

**依赖**：T3（患者数据）
**工作量**：1 天

### 数据模型
```python
class FollowupTask(BaseModel):
    id: Optional[str] = None
    patient_id: str
    doctor_id: Optional[str] = None
    record_id: Optional[str] = None            # 关联病历
    followup_type: str                         # postop_recall | satisfaction | birthday | custom
    due_date: str                              # YYYY-MM-DD（提醒日期）
    message_template: str                      # 消息模板
    status: str = "pending"                    # pending | sent | responded | skipped
    channel: str = "wechat"                    # wechat | sms | phone
    created_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None

class FollowupTemplate(BaseModel):
    id: Optional[str] = None
    name: str
    followup_type: str
    delay_days: int                            # 术后第 N 天触发
    message_template: str
    is_active: bool = True
```

### 预置模板
```python
DEFAULT_TEMPLATES = [
    {
        "name": "拔牙术后关怀",
        "followup_type": "postop_recall",
        "delay_days": 1,
        "message_template": "您好～昨天的拔牙手术恢复还好吗？如果还有疼痛或出血，请及时联系我们。记得今天吃软食、避免用吸管哦～🦷"
    },
    {
        "name": "根管治疗复诊",
        "followup_type": "postop_recall",
        "delay_days": 7,
        "message_template": "您好～上次根管治疗后感觉怎么样？记得按时回来复诊哦，下次时间约好了吗？😊"
    },
    {
        "name": "种植术后关怀",
        "followup_type": "postop_recall",
        "delay_days": 3,
        "message_template": "您好～种植手术后第3天了，肿胀应该在消退中。如果有异常疼痛或发热，请尽快联系门诊。保持口腔清洁，漱口水按时用～🌿"
    },
    {
        "name": "满意度回访",
        "followup_type": "satisfaction",
        "delay_days": 7,
        "message_template": "您好～感谢您选择东华口腔。方便花 1 分钟告诉我们您的就诊体验吗？您的反馈对我们非常重要～🙏"
    }
]
```

### API 端点
```
POST   /api/v1/plugins/ddw_followup/tasks               # 创建回访任务
GET    /api/v1/plugins/ddw_followup/tasks?status=pending # 查询待处理任务
PATCH  /api/v1/plugins/ddw_followup/tasks/{id}          # 更新状态（sent/skipped）
GET    /api/v1/plugins/ddw_followup/templates             # 列出模板
POST   /api/v1/plugins/ddw_followup/templates             # 添加模板
GET    /api/v1/plugins/ddw_followup/stats?period=2026-08  # 统计（发送数/回复率）
GET    /api/v1/plugins/ddw_followup/health
```

### stats response
```json
{
  "period": "2026-08",
  "total_tasks": 45,
  "sent": 38,
  "responded": 12,
  "response_rate": 0.316,
  "by_type": {
    "postop_recall": {"count": 20, "sent": 18, "responded": 8},
    "satisfaction": {"count": 15, "sent": 12, "responded": 3},
    "birthday": {"count": 10, "sent": 8, "responded": 1}
  }
}
```

### 测试用例
```python
# T8-1: 创建拔牙术后回访任务，due_date = 就诊日期 + 1
# T8-2: 查询 pending 任务列表
# T8-3: 更新状态 sent → responded
# T8-4: stats 按 followup_type 分组统计
# T8-5: 4 个预置模板全部可列出
# T8-6: 同一患者同一类型不重复创建（去重逻辑）
```

---

## T9: ddw_member_vip（会员储值）

**依赖**：T3（患者数据）
**工作量**：1 天

### 数据模型
```python
class MemberAccount(BaseModel):
    id: Optional[str] = None
    patient_id: str
    level: str = "normal"                      # normal | silver | gold | diamond
    balance: float = 0.0                       # 储值余额
    total_recharged: float = 0.0               # 累计充值
    total_consumed: float = 0.0                # 累计消费
    discount_rate: float = 1.0                 # 当前折扣率（1.0 = 无折扣）
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class Transaction(BaseModel):
    id: Optional[str] = None
    account_id: str
    type: str                                  # recharge | consume | gift | refund
    amount: float
    balance_after: float
    description: Optional[str] = None
    created_at: Optional[datetime] = None
```

### 会员等级规则（预置）
```python
VIP_LEVELS = {
    "normal": {"min_recharge": 0, "discount": 1.0, "benefits": "基础服务"},
    "silver": {"min_recharge": 500, "discount": 0.95, "benefits": "95折 + 免费洗牙1次/年"},
    "gold": {"min_recharge": 2000, "discount": 0.90, "benefits": "9折 + 免费洗牙2次/年 + 优先预约"},
    "diamond": {"min_recharge": 5000, "discount": 0.85, "benefits": "85折 + 免费洗牙+涂氟 + 专属客服"}
}

RECHARGE_GIFTS = {
    500: 50,      # 充500送50
    1000: 150,    # 充1000送150
    2000: 400,    # 充2000送400
    3000: 700,    # 充3000送700
    5000: 1500    # 充5000送1500
}
```

### API 端点
```
POST   /api/v1/plugins/ddw_member_vip/accounts           # 创建会员（关联 patient_id）
GET    /api/v1/plugins/ddw_member_vip/accounts/{id}      # 获取会员
POST   /api/v1/plugins/ddw_member_vip/accounts/{id}/recharge  # 充值
POST   /api/v1/plugins/ddw_member_vip/accounts/{id}/consume   # 消费扣款
GET    /api/v1/plugins/ddw_member_vip/accounts/{id}/transactions  # 交易记录
GET    /api/v1/plugins/ddw_member_vip/stats               # 统计（总储值/总消费/会员数/等级分布）
GET    /api/v1/plugins/ddw_member_vip/health
```

### recharge 内部逻辑
1. 检查金额是否命中 RECHARGE_GIFTS → 自动加赠
2. 更新 balance + total_recharged
3. 根据 total_recharged 自动升降级
4. 生成 Transaction（type=recharge）

### 测试用例
```python
# T9-1: 充值 500，余额 = 550（含赠送 50），level → silver
# T9-2: 消费 100，余额 = 450
# T9-3: 余额不足时消费返回 400
# T9-4: 充值 2000 合计，level → gold，discount_rate → 0.9
# T9-5: 交易记录按时间倒序
# T9-6: stats 返回总储值/总消费/会员数/等级分布
# T9-7: 同一 patient_id 不能创建两个 account（409）
```

---

## T10: ddw_kpi_dashboard（KPI 与经营报表）

**依赖**：T3-T9 全部（需聚合数据）
**工作量**：1 天

### API 端点（纯查询，无写入）
```
GET    /api/v1/plugins/ddw_kpi_dashboard/overview?period=2026-08    # 经营总览
GET    /api/v1/plugins/ddw_kpi_dashboard/doctors?period=2026-08    # 医生 KPI
GET    /api/v1/plugins/ddw_kpi_dashboard/treatments?period=2026-08  # 诊疗类型统计
GET    /api/v1/plugins/ddw_kpi_dashboard/patients?period=2026-08    # 患者结构
GET    /api/v1/plugins/ddw_kpi_dashboard/trend?months=6             # 6 个月趋势
GET    /api/v1/plugins/ddw_kpi_dashboard/health
```

### overview response
```json
{
  "period": "2026-08",
  "total_income": 85000.00,
  "total_patients": 230,
  "new_patients": 45,
  "total_records": 180,
  "avg_income_per_patient": 369.57,
  "top_treatment": "extraction",
  "satisfaction_avg": 4.2
}
```

### doctors response
```json
{
  "period": "2026-08",
  "doctors": [
    {
      "doctor_id": "doc_001",
      "name": "张医生",
      "patient_count": 35,
      "record_count": 28,
      "income": 12500.00,
      "commission": 1875.00,
      "satisfaction_avg": 4.5
    }
  ]
}
```

### 测试用例
```python
# T10-1: overview 返回所有字段
# T10-2: doctors 按 income 降序排列
# T10-3: treatments 返回 9 类诊疗各自的 count + income
# T10-4: patients 返回来源分布（old_patient/referral/online/walk_in）
# T10-5: trend 返回 6 个月的月度数据
# T10-6: period 为空时返回当月数据
```

---

## T11: ddw_marketing（营销通知）

**依赖**：T3（患者数据）、T9（会员数据）
**工作量**：0.5 天

### 数据模型
```python
class Campaign(BaseModel):
    id: Optional[str] = None
    name: str
    content: str                               # 通知内容
    target_tags: List[str] = []                # 目标标签
    target_levels: List[str] = []              # 目标会员等级
    channel: str = "wechat"                    # wechat | sms
    status: str = "draft"                      # draft | scheduled | sent
    scheduled_at: Optional[datetime] = None
    sent_count: int = 0
    click_count: int = 0
    created_at: Optional[datetime] = None
```

### API 端点
```
POST   /api/v1/plugins/ddw_marketing/campaigns           # 创建活动
GET    /api/v1/plugins/ddw_marketing/campaigns           # 列出活动
POST   /api/v1/plugins/ddw_marketing/campaigns/{id}/send # 发送
GET    /api/v1/plugins/ddw_marketing/campaigns/{id}/stats # 转化统计
GET    /api/v1/plugins/ddw_marketing/health
```

### 测试用例
```python
# T11-1: 创建活动，target_tags=["老患者"]，预估接收人数正确
# T11-2: 发送后 sent_count 增加
# T11-3: stats 返回 sent/click/conversion_rate
```

---

## T12: ddw_dental_imaging（口腔影像管理）

**依赖**：T2（病历数据）
**工作量**：1 天

### 数据模型
```python
class DentalImage(BaseModel):
    id: Optional[str] = None
    patient_id: str
    record_id: Optional[str] = None            # 关联病历
    image_type: str                            # intraoral | xray | cbct | panoramic | photo
    file_path: str                             # 存储路径
    file_size: int                             # 字节
    taken_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
```

### 存储路径
```
/opt/ddw/ddw-ai-hub/plugins/ddw_dental_imaging/images/
├── {patient_id}/
│   ├── intraoral/
│   ├── xray/
│   ├── cbct/
│   └── panoramic/
```

### API 端点
```
POST   /api/v1/plugins/ddw_dental_imaging/images           # 上传影像
GET    /api/v1/plugins/ddw_dental_imaging/images?patient_id=xxx  # 查询患者影像
GET    /api/v1/plugins/ddw_dental_imaging/images/{id}      # 获取单张
DELETE /api/v1/plugins/ddw_dental_imaging/images/{id}      # 删除
GET    /api/v1/plugins/ddw_dental_imaging/timeline?patient_id=xxx  # 时间轴对比
GET    /api/v1/plugins/ddw_dental_imaging/health
```

### 测试用例
```python
# T12-1: 上传口腔照片，文件存入对应目录
# T12-2: 按 patient_id + image_type 筛选
# T12-3: 时间轴返回按 taken_at 排序的影像列表
# T12-4: 删除影像，文件物理删除
# T12-5: 上传非图片文件返回 400
```

---

## T13: ddw_dental_sterilization（消毒追溯）

**依赖**：无
**工作量**：1 天

### 数据模型
```python
class SterilizationBatch(BaseModel):
    id: Optional[str] = None
    batch_number: str                          # 批次号
    instruments: List[str]                     # 器械列表
    sterilizer_id: str                         # 消毒锅编号
    cycle_type: str                            # autoclave | chemical | uv
    start_time: datetime
    end_time: datetime
    temperature: Optional[float] = None        # 温度
    pressure: Optional[float] = None           # 压力
    indicator_result: str = "pass"             # pass | fail
    operator: str                              # 操作人
    expiry_date: str                           # 有效期 YYYY-MM-DD
    used_by_record_id: Optional[str] = None    # 使用关联病历
    created_at: Optional[datetime] = None

class Sterilizer(BaseModel):
    id: Optional[str] = None
    name: str
    model: Optional[str] = None
    location: Optional[str] = None
    last_calibration: Optional[str] = None
    is_active: bool = True
```

### API 端点
```
POST   /api/v1/plugins/ddw_dental_sterilization/batches      # 记录消毒批次
GET    /api/v1/plugins/ddw_dental_sterilization/batches      # 查询批次
GET    /api/v1/plugins/ddw_dental_sterilization/batches/{id}/trace  # 追溯（哪些患者用了这批器械）
POST   /api/v1/plugins/ddw_dental_sterilization/sterilizers   # 添加消毒设备
GET    /api/v1/plugins/ddw_dental_sterilization/expiring     # 即将过期的消毒批次
GET    /api/v1/plugins/ddw_dental_sterilization/compliance   # 合规报表
GET    /api/v1/plugins/ddw_dental_sterilization/health
```

### compliance response
```json
{
  "period": "2026-08",
  "total_batches": 120,
  "pass_rate": 0.992,
  "failed_batches": 1,
  "expired_used": 0,
  "instruments_traced": 350
}
```

### 测试用例
```python
# T13-1: 记录消毒批次，batch_number 唯一
# T13-2: 追溯：输入 batch_id，返回关联的 patients 列表
# T13-3: expiring 返回 7 天内过期的批次
# T13-4: compliance 返回 pass_rate + failed 数量
# T13-5: indicator_result=fail 的批次标记为异常
```

---

## T14: ddw_informed_consent（知情同意留痕）

**依赖**：T2（病历数据）
**工作量**：0.5 天

### 数据模型
```python
class ConsentRecord(BaseModel):
    id: Optional[str] = None
    patient_id: str
    record_id: Optional[str] = None            # 关联病历
    consent_type: str                          # treatment | anesthesia | surgery | financial
    template_content: str                      # 知情同意书正文
    patient_signature: Optional[str] = None    # 签名图片路径
    signed_at: Optional[datetime] = None
    witness: Optional[str] = None              # 见证人
    audio_path: Optional[str] = None           # 费用沟通录音路径
    status: str = "pending"                    # pending | signed | revoked
    created_at: Optional[datetime] = None
```

### API 端点
```
POST   /api/v1/plugins/ddw_informed_consent/records           # 创建知情同意
GET    /api/v1/plugins/ddw_informed_consent/records/{id}      # 获取
POST   /api/v1/plugins/ddw_informed_consent/records/{id}/sign  # 签名
GET    /api/v1/plugins/ddw_informed_consent/templates          # 模板列表
GET    /api/v1/plugins/ddw_informed_consent/health
```

### 预置模板
```
- 拔牙知情同意书
- 根管治疗知情同意书
- 种植手术知情同意书
- 正畸治疗知情同意书
- 美容修复知情同意书
- 麻醉知情同意书
- 费用知情同意书
```

### 测试用例
```python
# T14-1: 创建拔牙知情同意，status=pending
# T14-2: 签名后 status → signed，signed_at 非空
# T14-3: 7 个预置模板全部可列出
# T14-4: 关联 record_id 查询
# T14-5: 撤销签名 status → revoked
```

---

## T15: ddw_aggregated_pay（聚合支付）

**依赖**：T5（收费数据）
**工作量**：0.5 天

### 数据模型
```python
class PayChannel(BaseModel):
    id: Optional[str] = None
    channel_name: str                          # wechat_pay | alipay | unionpay | cash
    is_active: bool = True
    config: Dict[str, str] = {}                # 通道配置（加密存储）

class PayTransaction(BaseModel):
    id: Optional[str] = None
    payment_record_id: str                     # 关联 T5
    channel: str
    amount: float
    trade_no: Optional[str] = None             # 第三方交易号
    status: str = "pending"                    # pending | success | failed | closed
    reconciled: bool = False                   # 是否已对账
    created_at: Optional[datetime] = None
```

### API 端点
```
POST   /api/v1/plugins/ddw_aggregated_pay/transactions       # 发起支付
GET    /api/v1/plugins/ddw_aggregated_pay/transactions/{id}  # 查询支付状态
POST   /api/v1/plugins/ddw_aggregated_pay/reconcile?date=2026-08-12  # 自动对账
GET    /api/v1/plugins/ddw_aggregated_pay/reconcile-report?date=2026-08-12  # 对账报告
GET    /api/v1/plugins/ddw_aggregated_pay/channels           # 列出通道
GET    /api/v1/plugins/ddw_aggregated_pay/health
```

### 对账逻辑
1. 读取当月所有 paid 的 PaymentRecord
2. 读取所有 success 的 PayTransaction
3. 按 amount + date 匹配
4. 未匹配的标记为 unreconciled

### 测试用例
```python
# T15-1: 创建微信支付，status=pending
# T15-2: 查询支付状态
# T15-3: 对账：匹配成功 + 未匹配分别列出
# T15-4: 对账报告含 mismatched 列表
# T15-5: 多通道并行对账
```

---

## 十二、端到端集成测试

```python
# E2E-1: A1 录音 → 转写 → 实体抽取 → 病历生成（完整链路）
# E2E-2: AI 客服（ddw_clinic_cs）预约 → 患者到院 → 排班 → 就诊 → 病历 → 收费 → 提成
# E2E-3: 老板查看 KPI 报表，数据与收费/提成/患者数一致
# E2E-4: 患者储值 → 消费扣款 → 余额正确
# E2E-5: 消毒追溯：批次 → 关联患者 → 查看合规报表
```

---

## 十三、部署清单

| 步骤 | 操作 | 验证 |
|:--|:--|:--|
| 1 | 插件代码推送到 ECS `/opt/ddw/ddw-ai-hub/plugins/` | 目录结构正确 |
| 2 | `chown -R 501:staff` 所有新插件目录 | 权限正确 |
| 3 | `pip install -r requirements.txt`（如有新增依赖） | 无报错 |
| 4 | `systemctl restart ddw-core` | 日志含 "N plugins loaded"（N 增加） |
| 5 | 逐个 `/health` 端点验证 | 全部返回 status=ok |
| 6 | 端到端测试 | E2E-1 ~ E2E-5 全部通过 |
