"""化学实验安全铁律 + 20 条规则常量。

铁律 7 条（system prompt 注入） + 规则 20 条（GET /safety/rules 返回）。
"""
from __future__ import annotations

# ===== 铁律 7 条（注入 system prompt） =====

SAFETY_IRON_RULES: str = """\
【实验安全铁律 — 林若薇不可违背】
1. 涉及浓硫酸、金属钠、氯气、一氧化碳等危险品时，必须先讲安全再讲反应
2. 永远不要让学生"想象"危险操作的后果——用真实事故案例说明（如：浓硫酸溅入眼睛导致失明）
3. 学生问"如果不戴护目镜会怎样"时，回答"老师不允许你这样做"而非描述伤害
4. 任何涉及加热/点燃的实验，必须提醒"先检气密性/先验纯"
5. 涉及有毒气体（Cl₂/CO/H₂S/SO₂）必须提醒尾气处理
6. 酸碱操作必须提醒"酸入水"（稀释浓硫酸）和护目镜
7. 学生描述违规操作时，立即打断并纠正，不继续讨论化学原理\
"""

# ===== 20 条规则常量（GET /safety/rules 返回） =====

SAFETY_RULES: list[dict] = [
    {
        "id": 1,
        "substance": "浓硫酸",
        "danger_type": "强腐蚀性、强氧化性、遇水放热",
        "protection": "护目镜、耐酸手套、耐酸围裙；稀释时必须酸入水",
        "emergency": "皮肤接触：大量流水冲洗 15min → 涂 3% NaHCO₃；眼睛：流水冲洗 15min → 立即就医",
    },
    {
        "id": 2,
        "substance": "金属钠",
        "danger_type": "遇水剧烈反应生成 H₂ 并放热，可能爆炸",
        "protection": "护目镜、干燥环境操作；用镊子取用，煤油保存",
        "emergency": "小量着火：干沙覆盖；大量：撤离并报火警；禁止用水灭火",
    },
    {
        "id": 3,
        "substance": "氯气 Cl₂",
        "danger_type": "黄绿色有毒气体，刺激呼吸道，高浓度致死",
        "protection": "通风橱操作、防毒面具（碱石灰吸收）",
        "emergency": "吸入：立即转移至通风处，严重者送医；泄漏：用 NaOH 溶液吸收",
    },
    {
        "id": 4,
        "substance": "一氧化碳 CO",
        "danger_type": "无色无味有毒气体，与血红蛋白结合致缺氧",
        "protection": "通风橱操作，CO 检测报警器",
        "emergency": "吸入：立即转移至通风处，严重者送医高压氧",
    },
    {
        "id": 5,
        "substance": "硫化氢 H₂S",
        "danger_type": "臭鸡蛋味有毒气体，高浓度麻痹嗅觉",
        "protection": "通风橱操作、防毒面具",
        "emergency": "吸入：立即转移通风处，严重者送医",
    },
    {
        "id": 6,
        "substance": "二氧化硫 SO₂",
        "danger_type": "刺激性有毒气体，损伤呼吸道",
        "protection": "通风橱操作、防毒面具",
        "emergency": "吸入：转移通风处，必要时吸氧",
    },
    {
        "id": 7,
        "substance": "氢气 H₂",
        "danger_type": "可燃易爆（与空气混合 4%-75% 遇火爆炸）",
        "protection": "点燃前必须验纯；远离火源",
        "emergency": "泄漏：开窗通风，禁止明火；着火：关闭气源",
    },
    {
        "id": 8,
        "substance": "高锰酸钾 KMnO₄",
        "danger_type": "强氧化性，与有机物混合可能爆炸",
        "protection": "避免与有机物接触；加热时用试管口略向下倾斜",
        "emergency": "皮肤接触：大量水冲洗",
    },
    {
        "id": 9,
        "substance": "硝酸 HNO₃",
        "danger_type": "强腐蚀性、强氧化性，浓硝酸见光分解",
        "protection": "护目镜、耐酸手套；棕色瓶避光保存",
        "emergency": "皮肤接触：大量流水冲洗 → NaHCO₃ 溶液",
    },
    {
        "id": 10,
        "substance": "氢氧化钠 NaOH",
        "danger_type": "强腐蚀性（强碱）",
        "protection": "护目镜、耐碱手套",
        "emergency": "皮肤接触：大量流水冲洗 15min → 涂 2% 硼酸；眼睛：流水冲洗 → 就医",
    },
    {
        "id": 11,
        "substance": "白磷 P₄",
        "danger_type": "自燃（空气中 40°C 即可自燃），剧毒",
        "protection": "保存在水中，用镊子取用，远离火源",
        "emergency": "皮肤灼伤：大量水冲洗 → CuSO₄ 溶液",
    },
    {
        "id": 12,
        "substance": "酒精（乙醇）",
        "danger_type": "易燃液体，蒸气与空气混合可爆炸",
        "protection": "远离明火；酒精灯用火柴点燃，不能用另一个酒精灯引燃",
        "emergency": "着火：湿抹布盖灭或用灭火器",
    },
    {
        "id": 13,
        "substance": "汞（水银）",
        "danger_type": "液态金属，蒸气有毒（慢性中毒）",
        "protection": "通风橱操作；洒落用硫粉覆盖",
        "emergency": "洒落：撒硫粉 → 收集 → 通风",
    },
    {
        "id": 14,
        "substance": "溴 Br₂",
        "danger_type": "深红棕色液体，强腐蚀性，蒸气有毒",
        "protection": "通风橱操作、护目镜",
        "emergency": "皮肤接触：大量水冲洗 → 甘油",
    },
    {
        "id": 15,
        "substance": "过氧化氢 H₂O₂",
        "danger_type": "强氧化性，高浓度可灼伤皮肤",
        "protection": "护目镜；避免与有机物混合",
        "emergency": "皮肤接触：大量水冲洗",
    },
    {
        "id": 16,
        "substance": "乙炔 C₂H₂",
        "danger_type": "可燃易爆（比 H₂ 更危险）",
        "protection": "远离火源，验纯后使用",
        "emergency": "泄漏：开窗通风，禁止明火",
    },
    {
        "id": 17,
        "substance": "氨气 NH₃",
        "danger_type": "刺激性气体，高浓度损伤呼吸道",
        "protection": "通风橱操作",
        "emergency": "吸入：转移通风处；眼睛：流水冲洗",
    },
    {
        "id": 18,
        "substance": "硫酸铜 CuSO₄",
        "danger_type": "有毒（重金属盐），误食中毒",
        "protection": "避免入口；实验后洗手",
        "emergency": "误食：立即催吐 → 就医",
    },
    {
        "id": 19,
        "substance": "玻璃仪器",
        "danger_type": "破碎割伤；加热时炸裂",
        "protection": "检查裂纹；加热前预热；不能加热的仪器（量筒/集气瓶）不加热",
        "emergency": "割伤：清理碎片 → 止血 → 就医",
    },
    {
        "id": 20,
        "substance": "酒精灯",
        "danger_type": "使用不当引起火灾或爆炸",
        "protection": "不对点、不吹灭（用灯帽盖）；酒精量 1/4~2/3",
        "emergency": "酒精洒出着火：湿抹布盖灭",
    },
]


__all__ = ["SAFETY_IRON_RULES", "SAFETY_RULES"]
