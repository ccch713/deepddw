"""FastAPI 路由 — 安全法规问答 / 隐患上报 / 培训卡片 / 风险提示牌"""

from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from .models import (
    ControlMeasure,
    HazardReport,
    HazardReportCreate,
    HazardStatusUpdate,
    PluginHealth,
    Regulation,
    RegulationAnswer,
    RegulationQuery,
    RegulationSeedResult,
    RiskBulletin,
    RiskLevel,
    TrainingAnswer,
    TrainingQuestion,
    TrainingResult,
    WorkType,
)
from . import storage, PLUGIN_NAME, VERSION

router = APIRouter(prefix="/api/v1/plugins/ddw_chem_safety")

PROMPT_PATH = Path(__file__).parent / "prompts" / "safety_qa.txt"

# ── 内置法规摘要（兜底用） ──
FALLBACK_REGULATIONS = [
    "《安全生产法》(2021修订)：三管三必须、全员安全责任制、罚款上限1亿",
    "《安全生产治本攻坚三年行动方案(2024-2026)》：八大行动、重大隐患动态清零",
    "GB 30871-2022：特殊作业安全规范（动火/受限空间/高处/吊装/盲板/临时用电/动土/断路）",  # noqa: E501
    "AQ 3064-2025：特殊作业审批与过程管理、人员定位",
    "AQ 3067-2026：重大隐患判定准则",
    "《危险化学品安全法》(2026)：危化品全生命周期管理",
]


# ── 9 类特殊作业风险数据 ──

RISK_DATA: dict[str, RiskBulletin] = {
    "hot_work": RiskBulletin(
        work_type=WorkType.HOT_WORK,
        risk_level=RiskLevel.HIGH,
        hazards=["火灾爆炸", "灼烫", "中毒窒息", "触电"],
        control_measures=[
            ControlMeasure(
                title="作业前准备", description="办理动火作业许可证，明确动火级别（特殊/一级/二级），清除动火区域可燃物"),  # noqa: E501
            ControlMeasure(
                title="气体检测", description="动火前30分钟内进行可燃气体分析，合格后方可作业，作业期间持续监测"),  # noqa: E501
            ControlMeasure(title="人员资质", description="动火人持证上岗，监火人全程监护，配备灭火器材"),  # noqa: E501
            ControlMeasure(title="隔离措施", description="与受限空间、可燃物料管道有效隔离，加装盲板或拆除一段管道"),  # noqa: E501
        ],
        emergency_procedures=["立即停止动火作业", "使用灭火器材扑灭初期火灾",
            "疏散无关人员至安全区域", "拨打119报警并启动应急预案", "报告车间主任和安全部门"],  # noqa: E501
        legal_references=["GB 30871-2022 第5章", "AQ 3064-2025", "《安全生产法》第三十八条"],  # noqa: E501
    ),
    "confined_space": RiskBulletin(
        work_type=WorkType.CONFINED_SPACE,
        risk_level=RiskLevel.HIGH,
        hazards=["中毒窒息", "爆炸", "淹溺", "掩埋", "触电"],
        control_measures=[
            ControlMeasure(
                title="气体检测", description="作业前检测氧含量(19.5%-23.5%)、有毒有害气体浓度、可燃气体浓度"),  # noqa: E501
            ControlMeasure(title="通风换气", description="作业前和作业中持续强制通风，禁止纯氧通风"),  # noqa: E501
            ControlMeasure(title="人员监护", description="设专人监护，作业人员佩戴安全绳，外部配备应急救援设备"),  # noqa: E501
            ControlMeasure(title="作业许可", description="办理受限空间作业许可证，明确作业时间和人员"),  # noqa: E501
        ],
        emergency_procedures=["立即停止作业", "佩戴正压式空气呼吸器进入救援",
            "将中毒人员移至通风处", "进行心肺复苏", "拨打120急救电话"],
        legal_references=["GB 30871-2022 第6章", "AQ 3064-2025"],
    ),
    "high_altitude": RiskBulletin(
        work_type=WorkType.HIGH_ALTITUDE,
        risk_level=RiskLevel.MEDIUM,
        hazards=["高处坠落", "物体打击", "触电"],
        control_measures=[
            ControlMeasure(title="作业许可", description="办理高处作业许可证，2米以上作业必须审批"),  # noqa: E501
            ControlMeasure(title="防护装备", description="佩戴安全帽、安全带，安全带高挂低用"),  # noqa: E501
            ControlMeasure(title="脚手架检查", description="作业前检查脚手架、梯子、平台的稳固性"),  # noqa: E501
            ControlMeasure(title="工具管理", description="工具放入工具袋，禁止抛掷，下方设警戒区"),  # noqa: E501
        ],
        emergency_procedures=["立即停止作业", "对坠落人员进行初步救治", "拨打120急救电话", "保护事故现场", "报告安全部门"],  # noqa: E501
        legal_references=["GB 30871-2022 第7章", "《安全生产法》第四十一条"],
    ),
    "lifting": RiskBulletin(
        work_type=WorkType.LIFTING,
        risk_level=RiskLevel.MEDIUM,
        hazards=["起重伤害", "物体打击", "机械伤害"],
        control_measures=[
            ControlMeasure(title="作业许可", description="办理吊装作业许可证，明确吊装方案"),  # noqa: E501
            ControlMeasure(title="设备检查", description="检查吊装机具、钢丝绳、吊钩等，确保完好"),  # noqa: E501
            ControlMeasure(title="人员指挥", description="设专职指挥人员，统一指挥信号"),  # noqa: E501
            ControlMeasure(title="载荷控制", description="严禁超载，吊物下方严禁站人"),
        ],
        emergency_procedures=["立即停止吊装作业", "疏散吊物下方人员", "对受伤人员进行急救", "保护事故现场"],  # noqa: E501
        legal_references=["GB 30871-2022 第8章"],
    ),
    "blind_plate": RiskBulletin(
        work_type=WorkType.BLIND_PLATE,
        risk_level=RiskLevel.MEDIUM,
        hazards=["中毒窒息", "灼烫", "化学品泄漏"],
        control_measures=[
            ControlMeasure(title="作业许可", description="办理盲板抽堵作业许可证"),
            ControlMeasure(title="压力泄放", description="确认管道压力降至常压，泄放残液"),  # noqa: E501
            ControlMeasure(title="个人防护", description="佩戴防毒面具、防化服等 appropriate PPE"),  # noqa: E501
            ControlMeasure(title="标识管理", description="盲板编号登记，作业完成后确认恢复"),  # noqa: E501
        ],
        emergency_procedures=["立即停止作业", "发生泄漏时启动应急响应", "疏散至上风向", "穿戴防护装备进行堵漏"],  # noqa: E501
        legal_references=["GB 30871-2022 第9章"],
    ),
    "temporary_power": RiskBulletin(
        work_type=WorkType.TEMPORARY_POWER,
        risk_level=RiskLevel.MEDIUM,
        hazards=["触电", "电气火灾", "电弧灼伤"],
        control_measures=[
            ControlMeasure(title="作业许可", description="办理临时用电作业许可证"),
            ControlMeasure(title="线路检查", description="使用合格电缆，架空敷设，不得与金属管道接触"),  # noqa: E501
            ControlMeasure(title="漏电保护", description="安装漏电保护器，接地可靠"),
            ControlMeasure(title="防爆要求", description="爆炸危险场所使用防爆电气设备"),  # noqa: E501
        ],
        emergency_procedures=["立即切断电源", "使用绝缘工具使触电者脱离电源", "进行心肺复苏", "拨打120急救电话"],  # noqa: E501
        legal_references=["GB 30871-2022 第10章"],
    ),
    "ground_excavation": RiskBulletin(
        work_type=WorkType.GROUND_EXCAVATION,
        risk_level=RiskLevel.LOW,
        hazards=["坍塌", "地下管线损坏", "人员坠落"],
        control_measures=[
            ControlMeasure(title="作业许可", description="办理动土作业许可证"),
            ControlMeasure(title="管线排查", description="作业前确认地下管线（水/电/气/化学品）位置"),  # noqa: E501
            ControlMeasure(title="支护措施", description="深度超过1.5米设置支护或放坡"),
            ControlMeasure(title="警示标识", description="设置围栏和警示标志，夜间设红灯"),  # noqa: E501
        ],
        emergency_procedures=["立即停止作业", "坍塌时组织救援（注意二次坍塌风险）", "管线损坏时通知相关单位", "拨打急救电话"],  # noqa: E501
        legal_references=["GB 30871-2022 第11章"],
    ),
    "road_blocking": RiskBulletin(
        work_type=WorkType.ROAD_BLOCKING,
        risk_level=RiskLevel.LOW,
        hazards=["交通事故", "阻碍应急通道"],
        control_measures=[
            ControlMeasure(title="作业许可", description="办理断路作业许可证"),
            ControlMeasure(title="交通疏导", description="设置交通标志、路障，安排专人指挥"),  # noqa: E501
            ControlMeasure(title="应急通道", description="确保消防通道和应急疏散路线畅通"),  # noqa: E501
            ControlMeasure(title="夜间警示", description="设置警示灯和反光标志"),
        ],
        emergency_procedures=["立即恢复道路通行能力", "发生交通事故时报警", "通知应急管理部门"],  # noqa: E501
        legal_references=["GB 30871-2022 第12章"],
    ),
    "pressure_work": RiskBulletin(
        work_type=WorkType.PRESSURE_WORK,
        risk_level=RiskLevel.HIGH,
        hazards=["介质喷射伤人", "管道爆裂", "中毒窒息"],
        control_measures=[
            ControlMeasure(title="作业许可", description="办理带压作业许可证，经企业主要负责人审批"),  # noqa: E501
            ControlMeasure(title="风险评估", description="评估管道内介质、压力、温度，制定专项方案"),  # noqa: E501
            ControlMeasure(title="防护措施", description="作业人员穿防化服，设安全撤离通道"),  # noqa: E501
            ControlMeasure(title="应急准备", description="现场配备应急堵漏工具和急救设备"),  # noqa: E501
        ],
        emergency_procedures=["立即停止作业", "人员迅速撤离至上风向",
            "关闭上游阀门（如安全可行）", "启动应急预案", "拨打119"],
        legal_references=["GB 30871-2022", "AQ 3064-2025", "《安全生产法》第三十八条"],
    ),
}

# ── 预置培训题库 ──

TRAINING_QUESTION_BANK = [
    # 受限空间作业（4题）
    {
        "question": "进入受限空间作业前，氧含量应控制在什么范围？",
        "options": ["A. 16%-18%", "B. 19.5%-23.5%", "C. 20%-25%", "D. 18%-22%"],
        "correct_index": 1,
        "explanation": "根据GB 30871-2022，受限空间作业前氧含量应保持在19.5%-23.5%之间。低于19.5%为缺氧环境，高于23.5%存在富氧燃烧风险。",  # noqa: E501
        "category": "受限空间作业",
        "difficulty": 1,
    },
    {
        "question": "受限空间作业时，以下哪项做法是正确的？",
        "options": ["A. 使用纯氧进行通风", "B. 作业人员可自行进入作业", "C. 设专人监护并持续通风", "D. 检测合格后无需再监测"],  # noqa: E501
        "correct_index": 2,
        "explanation": "受限空间作业必须设专人监护，作业期间持续强制通风。禁止使用纯氧通风（防止富氧爆炸），作业人员不得自行进入，气体检测需持续进行。",  # noqa: E501
        "category": "受限空间作业",
        "difficulty": 1,
    },
    {
        "question": "发现受限空间内作业人员晕倒，首先应采取什么措施？",
        "options": ["A. 立即进入救人", "B. 佩戴正压式空气呼吸器进入救援", "C. 先报警再等待", "D. 向空间内吹氧"],  # noqa: E501
        "correct_index": 1,
        "explanation": "严禁盲目进入救人！必须佩戴正压式空气呼吸器等防护装备后方可进入施救，否则可能造成连锁中毒窒息事故。",  # noqa: E501
        "category": "受限空间作业",
        "difficulty": 2,
    },
    {
        "question": "受限空间作业许可证的有效时间最长为多少？",
        "options": ["A. 8小时", "B. 24小时", "C. 由企业自行确定但不超过一个作业周期", "D. 48小时"],  # noqa: E501
        "correct_index": 2,
        "explanation": "GB 30871-2022规定，受限空间作业许可证有效期由企业根据实际情况确定，但不应超过一个作业周期。作业条件变化时需重新办理。",  # noqa: E501
        "category": "受限空间作业",
        "difficulty": 2,
    },
    # 动火作业（4题）
    {
        "question": "动火作业前，可燃气体分析应在动火前多少分钟内进行？",
        "options": ["A. 10分钟", "B. 30分钟", "C. 60分钟", "D. 5分钟"],
        "correct_index": 1,
        "explanation": "GB 30871-2022规定，动火作业前30分钟内进行可燃气体分析，检测结果合格后方可动火。超过30分钟需重新检测。",  # noqa: E501
        "category": "动火作业",
        "difficulty": 1,
    },
    {
        "question": "以下哪个区域的动火作业属于特殊动火？",
        "options": ["A. 办公楼旁空地", "B. 正在运行的甲醇储罐区域", "C. 仓库外道路", "D. 停车场"],  # noqa: E501
        "correct_index": 1,
        "explanation": "特殊动火是指在运行状态下的易燃易爆生产装置、储罐区等部位的动火作业。正在运行的甲醇储罐区域属于特殊动火级别，需企业最高级别审批。",  # noqa: E501
        "category": "动火作业",
        "difficulty": 2,
    },
    {
        "question": "动火作业中监火人的主要职责是什么？",
        "options": ["A. 协助焊接作业", "B. 全程监护并准备灭火器材", "C. 负责办理许可证", "D. 检测气体浓度"],  # noqa: E501
        "correct_index": 1,
        "explanation": "监火人的核心职责是全程在场监护，确保灭火器材就位，发现异常立即制止动火作业并报警。监火人不得离开现场或兼做其他工作。",  # noqa: E501
        "category": "动火作业",
        "difficulty": 1,
    },
    {
        "question": "动火作业中断超过多少分钟，再次动火前应重新检测？",
        "options": ["A. 10分钟", "B. 20分钟", "C. 30分钟", "D. 60分钟"],
        "correct_index": 2,
        "explanation": "动火作业中断超过30分钟，再次动火前应重新进行可燃气体分析，确认合格后方可继续动火。",  # noqa: E501
        "category": "动火作业",
        "difficulty": 2,
    },
    # 高处作业（3题）
    {
        "question": "高处作业是指在坠落高度基准面多少米及以上的作业？",
        "options": ["A. 1米", "B. 2米", "C. 3米", "D. 5米"],
        "correct_index": 1,
        "explanation": "GB 30871-2022规定，高处作业是指在坠落高度基准面2米及以上的作业。2米以上作业必须办理高处作业许可证。",  # noqa: E501
        "category": "高处作业",
        "difficulty": 1,
    },
    {
        "question": "安全带的正确使用方法是？",
        "options": ["A. 低挂高用", "B. 高挂低用", "C. 平挂平用", "D. 随意挂设"],
        "correct_index": 1,
        "explanation": "安全带应「高挂低用」——即挂点高于腰部，这样在坠落时冲击力最小，能有效保护作业人员。低挂高用会增加坠落距离和冲击力。",  # noqa: E501
        "category": "高处作业",
        "difficulty": 1,
    },
    {
        "question": "高处作业下方应设置什么措施？",
        "options": ["A. 无需任何措施", "B. 设警戒区并挂警示牌", "C. 派人站岗即可", "D. 铺设防护网即可"],  # noqa: E501
        "correct_index": 1,
        "explanation": "高处作业下方应设置警戒区，悬挂警示标志，禁止无关人员进入。必要时还需铺设安全网等防坠措施。",  # noqa: E501
        "category": "高处作业",
        "difficulty": 1,
    },
    # 危化品管理（4题）
    {
        "question": "危险化学品的「一书一签」是指什么？",
        "options": ["A. 安全技术说明书和安全标签", "B. 检查记录和合格证", "C. 使用说明和操作规程", "D. 采购合同和发票"],  # noqa: E501
        "correct_index": 0,
        "explanation": "「一书一签」是指安全技术说明书(SDS/MSDS)和安全标签。所有危化品必须附带，内容包含危险性说明、防护措施、急救措施等。",  # noqa: E501
        "category": "危化品管理",
        "difficulty": 1,
    },
    {
        "question": "储存危化品的仓库应遵循什么原则？",
        "options": ["A. 所有化学品可混放", "B. 分类分区存放，禁忌物料不得混存", "C. 按到货时间先后存放", "D. 按体积大小存放"],  # noqa: E501
        "correct_index": 1,
        "explanation": "危化品仓库必须分类分区存放，性质相抵触（禁忌物料）的危化品不得混存。如酸类与碱类、氧化剂与还原剂必须分开存放。",  # noqa: E501
        "category": "危化品管理",
        "difficulty": 2,
    },
    {
        "question": "危化品泄漏现场，人员应向哪个方向撤离？",
        "options": ["A. 下风向", "B. 上风向或侧风向", "C. 任意方向", "D. 原地等待"],
        "correct_index": 1,
        "explanation": "危化品泄漏时，人员应向上风向或侧风向撤离，避免吸入有毒气体。下风向是最危险的方向，绝不能向下风向撤离。",  # noqa: E501
        "category": "危化品管理",
        "difficulty": 1,
    },
    {
        "question": "《危险化学品安全法》（2026年）的核心特点是什么？",
        "options": ["A. 仅适用于生产环节", "B. 覆盖全链条全生命周期管理", "C. 仅针对重大危险源", "D. 仅适用于大型企业"],  # noqa: E501
        "correct_index": 1,
        "explanation": "《危险化学品安全法》是危化品安全管理首部专门法律，覆盖生产、储存、使用、经营、运输全链条全生命周期，适用于所有涉及危化品的企业。",  # noqa: E501
        "category": "危化品管理",
        "difficulty": 2,
    },
    # 电气安全（3题）
    {
        "question": "临时用电线路应采用什么方式敷设？",
        "options": ["A. 直接沿地面铺设", "B. 架空敷设", "C. 缠绕在金属管道上", "D. 随意悬挂"],  # noqa: E501
        "correct_index": 1,
        "explanation": "临时用电线路应架空敷设，不得与金属管道接触，不得沿地面随意铺设，以防止机械损伤和人员绊倒触电。",  # noqa: E501
        "category": "电气安全",
        "difficulty": 1,
    },
    {
        "question": "发现有人触电，首先应做什么？",
        "options": ["A. 立即用手拉开触电者", "B. 切断电源或用绝缘工具使触电者脱离电源", "C. 向触电者泼水", "D. 进行心肺复苏"],  # noqa: E501
        "correct_index": 1,
        "explanation": "发现触电者，首先应切断电源或使用绝缘工具（如干燥木棒）使触电者脱离电源。绝对不能直接用手接触触电者，否则救助者也会触电。",  # noqa: E501
        "category": "电气安全",
        "difficulty": 1,
    },
    {
        "question": "爆炸危险场所的临时用电应使用什么类型的电气设备？",
        "options": ["A. 普通电气设备即可", "B. 防爆型电气设备", "C. 防水型电气设备", "D. 低压设备即可"],  # noqa: E501
        "correct_index": 1,
        "explanation": "爆炸危险场所必须使用防爆型电气设备，其防爆等级应与爆炸危险区域的等级相匹配。普通电气设备产生的电火花可能引燃爆炸性气体。",  # noqa: E501
        "category": "电气安全",
        "difficulty": 2,
    },
    # 应急处置（2题）
    {
        "question": "化工企业应急预案演练应多长时间组织一次？",
        "options": ["A. 每年一次即可", "B. 至少每半年组织一次综合演练或专项演练", "C. 每季度一次", "D. 每两年一次"],  # noqa: E501
        "correct_index": 1,
        "explanation": "《安全生产法》和《生产安全事故应急预案管理办法》要求，化工等高危企业至少每半年组织一次综合应急预案演练或专项应急预案演练。",  # noqa: E501
        "category": "应急处置",
        "difficulty": 2,
    },
    {
        "question": "发生化学品灼伤后，现场急救的第一步是什么？",
        "options": ["A. 涂抹药膏", "B. 用大量流动清水冲洗至少15分钟", "C. 用纱布包扎", "D. 送往医院"],  # noqa: E501
        "correct_index": 1,
        "explanation": "化学品灼伤后，立即用大量流动清水持续冲洗至少15分钟，以稀释和去除化学品。这是最关键的急救措施。冲洗后再根据化学品性质进行后续处理。",  # noqa: E501
        "category": "应急处置",
        "difficulty": 1,
    },
]


# ═══════════════════════════════════════
# 端点实现
# ═══════════════════════════════════════


@router.get("/health", response_model=PluginHealth)
def health_check():
    return PluginHealth(
        plugin_name=PLUGIN_NAME,
        version=VERSION,
        status="healthy",
        database_connected=True,
        regulation_count=storage.count_regulations(),
        hazard_count=storage.count_hazards(),
        question_count=storage.count_questions(),
    )


# ── 安全法规问答 ──


@router.post("/regulation/ask", response_model=RegulationAnswer)
def ask_regulation(query: RegulationQuery):
    # 检查是否有 RAG 语料（预留接口）
    rag_context = _load_rag_context(query.question)
    rag_used = bool(rag_context)

    # 读取 prompt 模板
    prompt_template = _load_prompt()

    # 构造 prompt
    prompt = prompt_template.replace(
        "{rag_context}", rag_context or "（无外部检索结果，请使用内置法规知识回答）")
    prompt = prompt.replace("{question}", query.question)
    if query.context:
        prompt += f"\n\n## 补充上下文\n{query.context}"

    # 生成回答（兜底模式：基于内置法规摘要）
    answer, sources, confidence = _generate_answer(query.question, rag_context)

    return RegulationAnswer(
        question=query.question,
        answer=answer,
        sources=sources,
        confidence=confidence,
        rag_used=rag_used,
    )


def _load_prompt() -> str:
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8")
    return "你是化工安全合规助手。请回答用户的安全法规问题。\n\n{rag_context}\n\n{question}"  # noqa: E501


def _load_rag_context(question: str) -> Optional[str]:
    """预留 RAG 接口：检查 data/regulations/ 目录"""
    reg_dir = Path(__file__).parent / "data" / "regulations"
    if not reg_dir.exists():
        return None
    files = [f for f in reg_dir.iterdir() if f.is_file() and f.name != ".gitkeep"]
    if not files:
        return None
    # 预留：实际实现中此处调用向量检索
    return None


def _generate_answer(question: str, rag_context: Optional[str]) -> tuple:
    """基于内置法规摘要的兜底回答逻辑"""
    q = question.lower()

    # 关键词匹配 + 内置回答
    if any(kw in q for kw in ["动火", "焊接", "明火"]):
        return (
            "根据GB 30871-2022《化学品生产单位特殊作业安全规范》第5章规定，化工企业动火作业需要：\n\n"  # noqa: E501
            "1. **办理动火作业许可证**：明确动火级别（特殊动火/一级动火/二级动火），按级别审批\n"  # noqa: E501
            "2. **可燃气体分析**：动火前30分钟内进行，合格后方可作业\n"
            "3. **清除可燃物**：动火区域10米范围内清除可燃物质\n"
            "4. **配备监火人**：全程监护，配备灭火器材\n"
            "5. **人员资质**：动火人须持特种作业操作证\n\n"
            "特殊动火（如运行中的易燃易爆装置区域）需企业主要负责人审批。"
        ), ["GB 30871-2022 第5章", "AQ 3064-2025", "《安全生产法》第三十八条"], 0.9

    if any(kw in q for kw in ["受限空间", "密闭", "储罐", "容器"]):
        return (
            "根据GB 30871-2022第6章，受限空间作业的安全要求包括：\n\n"
            "1. **气体检测**：氧含量19.5%-23.5%，有毒气体低于职业接触限值，可燃气体浓度合格\n"  # noqa: E501
            "2. **通风换气**：作业前和作业中持续强制通风，禁止使用纯氧\n"
            "3. **作业许可**：办理受限空间作业许可证\n"
            "4. **人员监护**：设专人监护，作业人员佩戴安全绳\n"
            "5. **应急准备**：外部配备正压式空气呼吸器、安全绳等救援设备\n\n"
            "严禁未检测、未通风、未审批的「三违」进入受限空间。"
        ), ["GB 30871-2022 第6章", "《安全生产法》"], 0.9

    if any(kw in q for kw in ["高处", "高空", "登高", "脚手架"]):
        return (
            "根据GB 30871-2022第7章，高处作业安全要求：\n\n"
            "1. **作业许可**：2米及以上作业必须办理高处作业许可证\n"
            "2. **安全带**：正确佩戴，高挂低用\n"
            "3. **安全帽**：必须佩戴\n"
            "4. **脚手架**：作业前检查稳固性，合格后方可使用\n"
            "5. **工具管理**：工具放入工具袋，下方设警戒区\n\n"
            "六级及以上大风、暴雨、大雪等恶劣天气禁止露天高处作业。"
        ), ["GB 30871-2022 第7章"], 0.85

    if any(kw in q for kw in ["隐患", "排查", "重大隐患"]):
        return (
            "根据《安全生产治本攻坚三年行动方案(2024-2026)》和AQ 3067-2026：\n\n"
            "1. **隐患排查**：企业应建立安全风险分级管控制度，定期开展隐患排查\n"
            "2. **重大隐患判定**：依据AQ 3067-2026明确判定标准\n"
            "3. **动态清零**：发现重大隐患立即整改，整改前必须采取临时管控措施\n"
            "4. **「四防」体系**：人防、技防、工程防、管理防综合施策\n"
            "5. **报告义务**：重大隐患应及时报告当地应急管理部门\n\n"
            "《安全生产法》第三十八条要求建立安全风险分级管控制度。"
        ), ["AQ 3067-2026", "治本攻坚三年行动(2024-2026)", "《安全生产法》第三十八条"], 0.85  # noqa: E501

    if any(kw in q for kw in ["罚款", "处罚", "违法", "责任"]):
        return (
            "《安全生产法》(2021修订)大幅提高了处罚力度：\n\n"
            "1. **企业罚款上限**：从2000万元提高至1亿元\n"
            "2. **主要负责人罚款**：从年收入30%-80%提高至40%-100%\n"
            "3. **「三管三必须」**：管行业必须管安全、管业务必须管安全、管生产经营必须管安全\n"  # noqa: E501
            "4. **全员责任制**：主要负责人是安全生产第一责任人\n"
            "5. **关停处罚**：拒不整改的，可责令停产停业整顿\n\n"
            "发生特别重大事故的，对主要负责人处上一年年收入80%-100%的罚款。"
        ), ["《安全生产法》(2021修订)"], 0.9

    if any(kw in q for kw in ["危化品", "危险化学品", "化学品", "储存"]):
        return (
            "危化品管理相关法规要求：\n\n"
            "1. **《危险化学品安全法》(2026)**：首部专门法律，覆盖全链条全生命周期\n"
            "2. **「一书一签」**：安全技术说明书(SDS)和安全标签必须随附\n"
            "3. **分类存放**：禁忌物料不得混存，分区分类管理\n"
            "4. **储存条件**：温度、湿度、通风等符合化学品安全要求\n"
            "5. **台账管理**：建立出入库台账，做到账物相符\n\n"
            "2026年《危险化学品安全法》落地后，违规处罚将更加严厉。"
        ), ["《危险化学品安全法》(2026)", "《安全生产法》"], 0.85

    if any(kw in q for kw in ["培训", "教育", "考核", "特种作业"]):
        return (
            "安全培训相关要求：\n\n"
            "1. **全员培训**：《安全生产法》要求所有从业人员经过安全培训合格后方可上岗\n"  # noqa: E501
            "2. **特种作业**：特种作业人员（如焊工、电工）须持证上岗\n"
            "3. **新员工**：三级安全教育培训（公司级、车间级、班组级）\n"
            "4. **再培训**：每年至少进行一次安全再培训\n"
            "5. **培训档案**：建立培训档案，记录培训内容、时间、考核结果\n\n"
            "治本攻坚三年行动要求提升全员安全素质，加强安全培训。"
        ), ["《安全生产法》", "治本攻坚三年行动(2024-2026)"], 0.8

    # 默认通用回答
    return (
        "作为化工安全合规助手，我建议您关注以下核心法规要求：\n\n"
        "1. **《安全生产法》(2021修订)**：三管三必须、全员安全责任制\n"
        "2. **治本攻坚三年行动(2024-2026)**：重大隐患动态清零、四防体系\n"
        "3. **GB 30871-2022**：特殊作业安全规范\n"
        "4. **AQ 3064-2025**：危化安全生产数字化管理\n"
        "5. **《危险化学品安全法》(2026)**：危化品全生命周期管理\n\n"
        f"关于您的问题「{question}」，建议结合具体场景咨询安全管理部门或当地应急管理局，确保合规操作。"
    ), FALLBACK_REGULATIONS, 0.6


# ── 隐患上报 ──


@router.post("/hazard/report", response_model=HazardReport)
def create_hazard_report(report: HazardReportCreate):
    result = storage.create_hazard(
        area=report.area,
        hazard_type=report.hazard_type.value,
        description=report.description,
        image_urls=report.image_urls,
        reporter=report.reporter,
    )
    return HazardReport(**result)


@router.get("/hazard/list")
def list_hazard_reports(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return storage.list_hazards(status=status, page=page, page_size=page_size)


@router.put("/hazard/{hazard_id}/status", response_model=HazardReport)
def update_hazard_status(hazard_id: int, update: HazardStatusUpdate):
    existing = storage.get_hazard(hazard_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"隐患记录 {hazard_id} 不存在")

    result = storage.update_hazard_status(
        hazard_id=hazard_id,
        status=update.status.value,
        resolution_note=update.resolution_note,
    )
    return HazardReport(**result)


# ── 安全培训卡片 ──


@router.get("/training/random-question", response_model=TrainingQuestion)
def get_random_training_question():
    # 确保题库已初始化
    storage.insert_training_questions(TRAINING_QUESTION_BANK)
    q = storage.get_random_question()
    if not q:
        raise HTTPException(status_code=404, detail="题库为空")
    return TrainingQuestion(**q)


@router.post("/training/answer", response_model=TrainingResult)
def submit_training_answer(answer: TrainingAnswer):
    q = storage.get_question_by_id(answer.question_id)
    if not q:
        raise HTTPException(status_code=404, detail=f"题目 {answer.question_id} 不存在")
    if answer.selected_index >= len(q["options"]):
        raise HTTPException(status_code=400, detail="选择的选项索引超出范围")

    return TrainingResult(
        question_id=answer.question_id,
        correct=(answer.selected_index == q["correct_index"]),
        selected_index=answer.selected_index,
        correct_index=q["correct_index"],
        explanation=q["explanation"],
    )


# ── 风险提示牌 ──


@router.get("/risk-bulletin/{work_type}", response_model=RiskBulletin)
def get_risk_bulletin(work_type: str):
    if work_type not in RISK_DATA:
        valid_types = ", ".join(RISK_DATA.keys())
        raise HTTPException(
            status_code=404,
            detail=f"未知作业类型 '{work_type}'，有效值：{valid_types}",
        )
    return RISK_DATA[work_type]


# ── 法规语料库（真实法规数据） ──

REGULATION_SEED_DATA = [
    {
        "name": "中华人民共和国安全生产法（2021年修订）",
        "code": "安全生产法-2021",
        "year": 2021,
        "category": "法律",
        "clauses": [
            {"clause_number": "第三条", "summary": "安全生产工作坚持中国共产党的领导，以人为本，坚持人民至上、生命至上，把保护人民生命安全摆在首位，树牢安全发展理念，坚持安全第一、预防为主、综合治理的方针",  # noqa: E501
                "applicable_scenario": "所有生产经营活动"},
            {"clause_number": "第四条", "summary": "生产经营单位必须遵守本法和其他有关安全生产的法律、法规，加强安全生产管理，建立健全全员安全生产责任制和安全生产规章制度",  # noqa: E501
                "applicable_scenario": "企业安全管理制度建设"},
            {"clause_number": "第二十一条", "summary": "生产经营单位的主要负责人对本单位安全生产工作负有建立、健全本单位安全生产责任制等七项职责",  # noqa: E501
                "applicable_scenario": "主要负责人履职"},
            {"clause_number": "第二十五条", "summary": "生产经营单位的安全生产管理机构以及安全生产管理人员履行组织或者参与本单位安全生产教育和培训等七项职责",  # noqa: E501
                "applicable_scenario": "安全管理部门设置"},
            {"clause_number": "第三十八条", "summary": "生产经营单位应当建立安全风险分级管控制度，按照安全风险分级采取相应的管控措施",  # noqa: E501
                "applicable_scenario": "风险分级管控"},
            {"clause_number": "第四十一条", "summary": "生产经营单位应当教育和督促从业人员严格执行本单位的安全生产规章制度和安全操作规程，如实告知作业场所和工作岗位存在的危险因素、防范措施以及事故应急措施",  # noqa: E501
                "applicable_scenario": "安全培训教育"},
            {"clause_number": "第四十二条", "summary": "生产经营单位必须为从业人员提供符合国家标准或者行业标准的劳动防护用品，并监督、教育从业人员按照使用规则佩戴、使用",  # noqa: E501
                "applicable_scenario": "劳动防护用品管理"},
            {"clause_number": "第九十四条", "summary": "未按照规定设置安全生产管理机构或者配备安全生产管理人员的，责令限期改正，可以处五万元以下罚款",  # noqa: E501
                "applicable_scenario": "安全管理机构处罚"},
            {"clause_number": "第一百零九条", "summary": "发生生产安全事故，对负有责任的生产经营单位除要求其依法承担相应的赔偿等责任外，由应急管理部门处以罚款，最高可处一亿元罚款",  # noqa: E501
                "applicable_scenario": "事故处罚"},
            {"clause_number": "第一百一十四条", "summary": "发生生产安全事故，情节特别严重、影响特别恶劣的，可以按照前款罚款数额的二倍以上五倍以下对负有责任的生产经营单位处以罚款",  # noqa: E501
                "applicable_scenario": "特别重大事故处罚"},
        ],
        "applicable_scenarios": [
            "全员安全生产责任制建设",
            "安全风险分级管控",
            "安全管理制度制定",
            "主要负责人履职考核",
            "安全生产违法行为处罚",
            "安全培训教育体系",
            "劳动防护用品管理",
        ],
    },
    {
        "name": "安全生产治本攻坚三年行动方案（2024-2026年）",
        "code": "治本攻坚-2024",
        "year": 2024,
        "category": "政策文件",
        "clauses": [
            {"clause_number": "总体目标", "summary": "通过三年治本攻坚，地方政府和部门统筹发展和安全的理念进一步强化，安全生产责任体系进一步完善，消减重大安全风险、消除重大事故隐患的积极性主动性显著增强",  # noqa: E501
                "applicable_scenario": "安全生产总体规划"},
            {"clause_number": "八大行动", "summary": "生产经营单位主要负责人安全教育培训行动、重大事故隐患判定标准体系提升行动、重大事故隐患动态清零行动、安全科技支撑和工程治理行动、生产经营单位从业人员安全素质能力提升行动、生产经营单位安全管理体系建设行动、安全生产精准执法和帮扶行动、全民安全素质提升行动", "applicable_scenario": "安全生产专项整治"},  # noqa: E501
            {"clause_number": "重大隐患清零", "summary": "建立重大事故隐患数据库，实行清单制管理，动态更新、闭环销号。2024年底前基本消除2023年及以前排查发现的重大事故隐患",  # noqa: E501
                "applicable_scenario": "隐患排查治理"},
            {"clause_number": "四防体系", "summary": "构建人防、技防、工程防、管理防综合防范体系，提升本质安全水平",  # noqa: E501
                "applicable_scenario": "化工安全体系建设"},
            {"clause_number": "安全科技支撑", "summary": "推进化工园区和危化品企业数字化智能化管控平台建设，推广先进适用技术和装备",  # noqa: E501
                "applicable_scenario": "化工园区数字化建设"},
            {"clause_number": "从业人员素质提升", "summary": "开展危化品企业从业人员安全资质核查，推动高危岗位人员持证上岗率达100%",  # noqa: E501
                "applicable_scenario": "化工企业人员资质管理"},
        ],
        "applicable_scenarios": [
            "化工企业隐患排查治理",
            "重大事故隐患判定与整改",
            "安全管理体系升级",
            "化工园区数字化建设",
            "从业人员安全培训",
            "安全生产执法检查",
        ],
    },
    {
        "name": "化学品生产单位特殊作业安全规范",
        "code": "GB 30871-2022",
        "year": 2022,
        "category": "国家标准",
        "clauses": [
            {"clause_number": "第5章 动火作业", "summary": "动火作业分为特殊动火、一级动火和二级动火三级。动火前30分钟内进行可燃气体分析，合格后方可作业。特殊动火需企业主要负责人审批",  # noqa: E501
                "applicable_scenario": "动火作业管理"},
            {"clause_number": "第6章 受限空间作业",
                "summary": "受限空间作业前检测氧含量(19.5%-23.5%)、有毒有害气体浓度、可燃气体浓度。作业期间持续强制通风，禁止使用纯氧通风。设专人监护", "applicable_scenario": "受限空间作业管理"},  # noqa: E501
            {"clause_number": "第7章 高处作业", "summary": "高处作业是指在坠落高度基准面2米及以上的作业，必须办理高处作业许可证。安全带高挂低用，六级及以上大风禁止露天高处作业",  # noqa: E501
                "applicable_scenario": "高处作业管理"},
            {"clause_number": "第8章 吊装作业", "summary": "吊装作业按吊装重物质量分为三级，严禁超载，吊物下方严禁站人，设专职指挥人员",  # noqa: E501
                "applicable_scenario": "吊装作业管理"},
            {"clause_number": "第9章 盲板抽堵作业", "summary": "盲板抽堵作业前确认管道压力降至常压，泄放残液，佩戴防毒面具、防化服等防护装备。盲板编号登记",  # noqa: E501
                "applicable_scenario": "盲板抽堵作业管理"},
            {"clause_number": "第10章 临时用电作业", "summary": "临时用电线路应架空敷设，安装漏电保护器，爆炸危险场所使用防爆电气设备",  # noqa: E501
                "applicable_scenario": "临时用电管理"},
            {"clause_number": "第11章 动土作业", "summary": "动土作业前确认地下管线位置，深度超过1.5米设置支护或放坡，设置围栏和警示标志",  # noqa: E501
                "applicable_scenario": "动土作业管理"},
            {"clause_number": "第12章 断路作业", "summary": "断路作业设置交通标志、路障，确保消防通道和应急疏散路线畅通",  # noqa: E501
                "applicable_scenario": "断路作业管理"},
        ],
        "applicable_scenarios": [
            "化工企业特殊作业审批",
            "动火作业许可证管理",
            "受限空间作业安全管理",
            "高处作业防护",
            "吊装作业方案制定",
            "盲板抽堵作业安全",
            "临时用电安全",
            "动土作业地下管线保护",
            "断路作业交通疏导",
        ],
    },
    {
        "name": "化工和危险化学品生产经营企业重大生产安全事故隐患判定标准",
        "code": "AQ 3021-2008",
        "year": 2008,
        "category": "安全生产行业标准",
        "clauses": [
            {"clause_number": "总则", "summary": "本标准适用于化工和危险化学品生产经营单位重大生产安全事故隐患的判定。重大事故隐患是指危害和整改难度较大，应当全部或者局部停产停业，并经过一定时间整改治理方能排除的隐患",  # noqa: E501
                "applicable_scenario": "隐患排查判定"},
            {"clause_number": "危险化学品储存", "summary": "危险化学品储存场所不符合国家标准、行业标准要求的，判定为重大事故隐患",  # noqa: E501
                "applicable_scenario": "危化品储存隐患判定"},
            {"clause_number": "特种设备", "summary": "使用未取得许可生产、未经检验或者检验不合格的特种设备的，判定为重大事故隐患",  # noqa: E501
                "applicable_scenario": "特种设备隐患判定"},
            {"clause_number": "安全设施", "summary": "涉及重点监管危险化工工艺的装置未实现自动化控制的，判定为重大事故隐患",  # noqa: E501
                "applicable_scenario": "化工工艺自动化"},
            {"clause_number": "应急管理", "summary": "未对重大危险源进行安全评估或者未建立安全监测监控系统的，判定为重大事故隐患",  # noqa: E501
                "applicable_scenario": "重大危险源管理"},
        ],
        "applicable_scenarios": [
            "化工企业重大隐患排查",
            "危险化学品储存安全检查",
            "特种设备隐患判定",
            "化工工艺自动化改造",
            "重大危险源监控",
            "安全生产标准化评审",
        ],
    },
    {
        "name": "工业互联网+危化安全生产",
        "code": "AQ 3064-2025",
        "year": 2025,
        "category": "安全生产行业标准",
        "clauses": [
            {"clause_number": "特殊作业数字化审批", "summary": "特殊作业许可应通过信息化系统进行审批，实现作业申请、审批、验收全流程电子化，审批记录可追溯",  # noqa: E501
                "applicable_scenario": "特殊作业数字化管理"},
            {"clause_number": "人员定位系统", "summary": "化工园区和涉及重大危险源的企业应建设人员定位系统，实现人员实时定位、轨迹追踪、电子围栏和超员报警功能（2026年7月实施）",  # noqa: E501
                "applicable_scenario": "人员定位管理"},
            {"clause_number": "视频智能监控", "summary": "在重大危险源、关键装置和重点部位部署视频智能分析系统，实现违章行为自动识别和预警",  # noqa: E501
                "applicable_scenario": "智能视频监控"},
            {"clause_number": "双重预防机制信息化", "summary": "建设安全风险分级管控和隐患排查治理双重预防机制信息化平台，实现风险四色图和隐患闭环管理",  # noqa: E501
                "applicable_scenario": "双重预防机制建设"},
        ],
        "applicable_scenarios": [
            "化工园区数字化建设",
            "特殊作业电子审批",
            "人员定位系统部署",
            "智能视频监控建设",
            "双重预防机制信息化",
            "危化品全生命周期追溯",
        ],
    },
    {
        "name": "化工和危险化学品生产经营企业重大生产安全事故隐患判定准则（2026版）",
        "code": "AQ 3067-2026",
        "year": 2026,
        "category": "安全生产行业标准",
        "clauses": [
            {"clause_number": "总则", "summary": "本准则适用于化工和危险化学品生产经营单位重大生产安全事故隐患的判定，明确了重大隐患的分类、判定条件和管理要求",  # noqa: E501
                "applicable_scenario": "隐患排查标准化"},
            {"clause_number": "人员管理类隐患", "summary": "主要负责人和安全管理人员未依法经考核合格、特种作业人员未持证上岗等情形判定为重大隐患",  # noqa: E501
                "applicable_scenario": "人员资质管理"},
            {"clause_number": "设备设施类隐患", "summary": "涉及重点监管危险化工工艺的装置未实现自动化控制、涉及重大危险源未建立安全监测监控系统等判定为重大隐患",  # noqa: E501
                "applicable_scenario": "设备设施安全"},
            {"clause_number": "安全管理类隐患", "summary": "未建立安全风险分级管控制度、未建立隐患排查治理制度、未制定应急预案等判定为重大隐患",  # noqa: E501
                "applicable_scenario": "安全管理制度"},
        ],
        "applicable_scenarios": [
            "化工企业重大隐患判定",
            "安全生产执法检查",
            "隐患排查治理标准化",
            "安全管理制度合规性审查",
            "人员资质合规检查",
            "设备设施安全评估",
        ],
    },
    {
        "name": "危险化学品安全法（2026年）",
        "code": "危化品安全法-2026",
        "year": 2026,
        "category": "法律",
        "clauses": [
            {"clause_number": "总则", "summary": "危化品安全管理首部专门法律，覆盖生产、储存、使用、经营、运输全链条全生命周期管理。坚持安全第一、预防为主、综合治理的方针",  # noqa: E501
                "applicable_scenario": "危化品全链条管理"},
            {"clause_number": "生产许可", "summary": "危化品生产企业必须取得安全生产许可证，建立完善的安全管理制度和操作规程",  # noqa: E501
                "applicable_scenario": "危化品生产许可"},
            {"clause_number": "储存管理", "summary": "危化品储存应当分类分区存放，禁忌物料不得混存，建立出入库台账，做到账物相符",  # noqa: E501
                "applicable_scenario": "危化品储存管理"},
            {"clause_number": "运输安全", "summary": "危化品运输应当取得相应资质，运输车辆安装卫星定位装置，驾驶员和押运员持证上岗",  # noqa: E501
                "applicable_scenario": "危化品运输管理"},
            {"clause_number": "应急救援", "summary": "危化品企业应当制定应急预案，配备应急救援器材和设备，定期组织演练",  # noqa: E501
                "applicable_scenario": "危化品应急管理"},
        ],
        "applicable_scenarios": [
            "危化品生产企业合规",
            "危化品仓库安全管理",
            "危化品运输资质管理",
            "危化品应急预案编制",
            "危化品全生命周期追溯",
            "危化品安全执法检查",
        ],
    },
]


# ── 法规语料端点 ──


@router.get("/regulations", response_model=List[Regulation])
def list_regulations(keyword: Optional[str] = Query(None, description="搜索关键词")):
    """列出所有法规语料，支持关键词搜索"""
    if keyword:
        return storage.search_regulations(keyword)
    return storage.list_regulations()


@router.post("/regulations/seed", response_model=RegulationSeedResult)
def seed_regulations():
    """初始化法规语料入库（幂等：重复调用不产生重复数据）"""
    result = storage.seed_regulations(REGULATION_SEED_DATA)
    return RegulationSeedResult(**result)


@router.get("/regulations/{reg_id}", response_model=Regulation)
def get_regulation(reg_id: int):
    """获取单条法规详情"""
    reg = storage.get_regulation(reg_id)
    if not reg:
        raise HTTPException(status_code=404, detail=f"法规记录 {reg_id} 不存在")
    return Regulation(**reg)
