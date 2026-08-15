#!/usr/bin/env python3
"""Generate 8 draft framework JSON files for the ESG question bank."""
import json
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "data" / "frameworks"

FRAMEWORKS = [
    {
        "id": "iso14001",
        "name": "ISO 14001 环境管理体系",
        "organization": "ISO",
        "url": "https://www.iso.org/standard/14001",
        "description": "国际标准化组织（ISO）发布的环境管理体系标准，帮助企业系统化管理环境影响，持续改进环境绩效。",
        "version": "2015",
        "category": "international",
        "status": "draft",
        "standard_code": "ISO 14001:2015",
        "is_mandatory": False,
        "issuing_body": "International Organization for Standardization",
        "issue_date": "2015-09-15",
        "effective_date": "2015-09-15",
        "supported_sizes": ["small", "medium", "large", "enterprise"],
        "category_color": "#00A651",
        "themes": [
            {"id": "ENV", "name": "环境管理", "category": "environment", "weight": 1, "description": "环境管理体系要求", "color": "#34C759"},
        ],
        "indicators": [
            {
                "code": "ENV1", "name": "环境方针", "theme_id": "ENV", "weight": 1,
                "description": "环境方针的制定与沟通",
                "questions": [
                    {"id": "ENV1-Q1", "text": "企业是否制定了环境方针？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "无方针"}, {"value": 2, "label": "口头方针"}, {"value": 3, "label": "书面方针"}, {"value": 4, "label": "公开方针+承诺"}, {"value": 5, "label": "第三方认证+全员传达"}
                    ]},
                    {"id": "ENV1-Q2", "text": "企业是否识别了重要环境因素？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未识别"}, {"value": 2, "label": "初步识别"}, {"value": 3, "label": "系统识别"}, {"value": 4, "label": "定量评估"}, {"value": 5, "label": "生命周期评估+定期更新"}
                    ]},
                    {"id": "ENV1-Q3", "text": "企业是否遵守适用的环境法规？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "存在违规"}, {"value": 2, "label": "基本合规"}, {"value": 3, "label": "全面合规"}, {"value": 4, "label": "合规管理+定期评估"}, {"value": 5, "label": "超越合规+行业倡导"}
                    ]},
                ]
            },
            {
                "code": "ENV2", "name": "运行控制", "theme_id": "ENV", "weight": 1,
                "description": "环境管理运行控制措施",
                "questions": [
                    {"id": "ENV2-Q1", "text": "企业是否对重要环境因素实施运行控制？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "无控制"}, {"value": 2, "label": "基本管理"}, {"value": 3, "label": "程序控制"}, {"value": 4, "label": "标准化控制+监测"}, {"value": 5, "label": "智能化控制+持续改进"}
                    ]},
                    {"id": "ENV2-Q2", "text": "企业是否建立应急准备和响应程序？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "无程序"}, {"value": 2, "label": "基本预案"}, {"value": 3, "label": "完整程序"}, {"value": 4, "label": "定期演练"}, {"value": 5, "label": "全员参与+持续改进"}
                    ]},
                ]
            },
            {
                "code": "ENV3", "name": "监测与改进", "theme_id": "ENV", "weight": 1,
                "description": "环境绩效监测与持续改进",
                "questions": [
                    {"id": "ENV3-Q1", "text": "企业是否定期监测环境绩效？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未监测"}, {"value": 2, "label": "偶尔检查"}, {"value": 3, "label": "定期监测"}, {"value": 4, "label": "实时监测"}, {"value": 5, "label": "数据驱动+AI分析"}
                    ]},
                    {"id": "ENV3-Q2", "text": "企业是否进行内部环境审核？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未审核"}, {"value": 2, "label": "简单检查"}, {"value": 3, "label": "定期审核"}, {"value": 4, "label": "独立审核"}, {"value": 5, "label": "第三方审核+持续改进"}
                    ]},
                ]
            },
        ]
    },
    {
        "id": "iso45001",
        "name": "ISO 45001 职业健康安全管理体系",
        "organization": "ISO",
        "url": "https://www.iso.org/standard/45001",
        "description": "国际标准化组织（ISO）发布的职业健康安全管理体系标准，帮助组织预防工伤和健康问题。",
        "version": "2018",
        "category": "international",
        "status": "draft",
        "standard_code": "ISO 45001:2018",
        "is_mandatory": False,
        "issuing_body": "International Organization for Standardization",
        "issue_date": "2018-03-12",
        "effective_date": "2018-03-12",
        "supported_sizes": ["small", "medium", "large", "enterprise"],
        "category_color": "#FF3B30",
        "themes": [
            {"id": "OHS", "name": "职业健康安全", "category": "social", "weight": 1, "description": "职业健康安全管理要求", "color": "#FF3B30"},
        ],
        "indicators": [
            {
                "code": "OHS1", "name": "危险源识别", "theme_id": "OHS", "weight": 1,
                "description": "危险源辨识与风险评估",
                "questions": [
                    {"id": "OHS1-Q1", "text": "企业是否进行危险源辨识和风险评估？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未辨识"}, {"value": 2, "label": "简单识别"}, {"value": 3, "label": "系统评估"}, {"value": 4, "label": "定量风险评估"}, {"value": 5, "label": "全员参与+AI预警"}
                    ]},
                    {"id": "OHS1-Q2", "text": "企业是否制定风险控制措施？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "无措施"}, {"value": 2, "label": "基本防护"}, {"value": 3, "label": "系统控制"}, {"value": 4, "label": "层级控制"}, {"value": 5, "label": "消除+工程控制+管理"}
                    ]},
                    {"id": "OHS1-Q3", "text": "企业是否定期审查和更新风险评估？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未更新"}, {"value": 2, "label": "偶尔更新"}, {"value": 3, "label": "定期更新"}, {"value": 4, "label": "事件驱动更新"}, {"value": 5, "label": "持续监测+动态更新"}
                    ]},
                ]
            },
            {
                "code": "OHS2", "name": "事故预防", "theme_id": "OHS", "weight": 1,
                "description": "事故预防与应急管理",
                "questions": [
                    {"id": "OHS2-Q1", "text": "企业是否建立事故调查和报告机制？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "无机制"}, {"value": 2, "label": "基本报告"}, {"value": 3, "label": "调查流程"}, {"value": 4, "label": "根因分析"}, {"value": 5, "label": "学习型组织+预防文化"}
                    ]},
                    {"id": "OHS2-Q2", "text": "企业是否为员工提供安全培训和PPE？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "无培训"}, {"value": 2, "label": "入职培训"}, {"value": 3, "label": "定期培训+PPE"}, {"value": 4, "label": "专项培训+管理"}, {"value": 5, "label": "全员安全文化"}
                    ]},
                ]
            },
            {
                "code": "OHS3", "name": "绩效评估", "theme_id": "OHS", "weight": 1,
                "description": "职业健康安全绩效评估与改进",
                "questions": [
                    {"id": "OHS3-Q1", "text": "企业是否设定职业健康安全目标？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "无目标"}, {"value": 2, "label": "定性目标"}, {"value": 3, "label": "量化目标"}, {"value": 4, "label": "SMART目标"}, {"value": 5, "label": "零伤害目标+路径"}
                    ]},
                    {"id": "OHS3-Q2", "text": "企业是否定期进行管理评审？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未评审"}, {"value": 2, "label": "简单回顾"}, {"value": 3, "label": "年度评审"}, {"value": 4, "label": "季度评审"}, {"value": 5, "label": "持续改进+高层参与"}
                    ]},
                ]
            },
        ]
    },
    {
        "id": "gri",
        "name": "GRI 全球报告倡议标准",
        "organization": "GRI",
        "url": "https://www.globalreporting.org",
        "description": "全球最广泛使用的可持续发展报告标准，为组织提供编制可持续发展报告的框架。",
        "version": "2021",
        "category": "international",
        "status": "draft",
        "standard_code": "GRI Standards 2021",
        "is_mandatory": False,
        "issuing_body": "Global Reporting Initiative",
        "issue_date": "2021-10-01",
        "effective_date": "2023-01-01",
        "supported_sizes": ["medium", "large", "enterprise"],
        "category_color": "#007AFF",
        "themes": [
            {"id": "REP", "name": "报告披露", "category": "governance", "weight": 1, "description": "可持续发展报告编制要求", "color": "#007AFF"},
            {"id": "STK", "name": "利益相关方参与", "category": "governance", "weight": 1, "description": "利益相关方沟通与参与", "color": "#5856D6"},
        ],
        "indicators": [
            {
                "code": "REP1", "name": "报告基础", "theme_id": "REP", "weight": 1,
                "description": "报告编制基础与方法",
                "questions": [
                    {"id": "REP1-Q1", "text": "企业是否定期发布可持续发展报告？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未发布"}, {"value": 2, "label": "社会责任简报"}, {"value": 3, "label": "年度报告"}, {"value": 4, "label": "GRI框架报告"}, {"value": 5, "label": "GRI+第三方鉴证"}
                    ]},
                    {"id": "REP1-Q2", "text": "报告是否涵盖实质性议题？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未识别"}, {"value": 2, "label": "简单列举"}, {"value": 3, "label": "利益相关方参与"}, {"value": 4, "label": "定量评估"}, {"value": 5, "label": "双重实质性评估"}
                    ]},
                ]
            },
            {
                "code": "REP2", "name": "数据质量", "theme_id": "REP", "weight": 1,
                "description": "报告数据的质量保证",
                "questions": [
                    {"id": "REP2-Q1", "text": "报告数据是否经过内部审核？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未审核"}, {"value": 2, "label": "简单检查"}, {"value": 3, "label": "内部审核"}, {"value": 4, "label": "独立验证"}, {"value": 5, "label": "第三方鉴证"}
                    ]},
                    {"id": "REP2-Q2", "text": "报告是否遵循国际标准？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "无标准"}, {"value": 2, "label": "参考标准"}, {"value": 3, "label": "GRI标准"}, {"value": 4, "label": "多框架对标"}, {"value": 5, "label": "全面对标+创新"}
                    ]},
                ]
            },
            {
                "code": "STK1", "name": "利益相关方识别", "theme_id": "STK", "weight": 1,
                "description": "利益相关方的识别与优先级排序",
                "questions": [
                    {"id": "STK1-Q1", "text": "企业是否识别了关键利益相关方？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未识别"}, {"value": 2, "label": "简单列举"}, {"value": 3, "label": "系统识别"}, {"value": 4, "label": "影响评估"}, {"value": 5, "label": "动态管理+参与式治理"}
                    ]},
                    {"id": "STK1-Q2", "text": "企业是否定期与利益相关方沟通？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "无沟通"}, {"value": 2, "label": "被动回应"}, {"value": 3, "label": "定期沟通"}, {"value": 4, "label": "多元渠道"}, {"value": 5, "label": "共建共治"}
                    ]},
                ]
            },
        ]
    },
    {
        "id": "cdp",
        "name": "CDP 碳信息披露项目",
        "organization": "CDP",
        "url": "https://www.cdp.net",
        "description": "全球领先的环境信息披露平台，推动企业披露气候变化、水安全和森林相关数据。",
        "version": "2024",
        "category": "international",
        "status": "draft",
        "standard_code": "CDP Questionnaire 2024",
        "is_mandatory": False,
        "issuing_body": "CDP Worldwide",
        "issue_date": "2024-01-01",
        "effective_date": "2024-01-01",
        "supported_sizes": ["large", "enterprise"],
        "category_color": "#00A651",
        "themes": [
            {"id": "CC", "name": "气候变化", "category": "environment", "weight": 1, "description": "气候变化信息披露", "color": "#34C759"},
            {"id": "WS", "name": "水安全", "category": "environment", "weight": 1, "description": "水安全信息披露", "color": "#007AFF"},
        ],
        "indicators": [
            {
                "code": "CC1", "name": "治理", "theme_id": "CC", "weight": 1,
                "description": "气候变化治理架构",
                "questions": [
                    {"id": "CC1-Q1", "text": "企业是否有气候变化治理机制？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "无治理"}, {"value": 2, "label": "兼职负责"}, {"value": 3, "label": "工作组"}, {"value": 4, "label": "董事会级委员会"}, {"value": 5, "label": "委员会+ESG整合"}
                    ]},
                    {"id": "CC1-Q2", "text": "气候变化风险是否纳入企业战略？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未纳入"}, {"value": 2, "label": "初步识别"}, {"value": 3, "label": "纳入战略"}, {"value": 4, "label": "情景分析"}, {"value": 5, "label": "战略整合+转型计划"}
                    ]},
                ]
            },
            {
                "code": "CC2", "name": "风险管理", "theme_id": "CC", "weight": 1,
                "description": "气候风险管理与机遇识别",
                "questions": [
                    {"id": "CC2-Q1", "text": "企业是否识别气候变化相关风险？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未识别"}, {"value": 2, "label": "初步识别"}, {"value": 3, "label": "系统识别"}, {"value": 4, "label": "量化评估"}, {"value": 5, "label": "TCFD对标+整合"}
                    ]},
                    {"id": "CC2-Q2", "text": "企业是否设定科学碳目标？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "无目标"}, {"value": 2, "label": "定性目标"}, {"value": 3, "label": "量化目标"}, {"value": 4, "label": "SBTi目标"}, {"value": 5, "label": "净零目标+路径"}
                    ]},
                ]
            },
            {
                "code": "WS1", "name": "水治理", "theme_id": "WS", "weight": 1,
                "description": "水资源治理与披露",
                "questions": [
                    {"id": "WS1-Q1", "text": "企业是否监测用水量？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未监测"}, {"value": 2, "label": "基本记录"}, {"value": 3, "label": "定期监测"}, {"value": 4, "label": "实时监测"}, {"value": 5, "label": "智能水务+目标管理"}
                    ]},
                    {"id": "WS1-Q2", "text": "企业是否设定节水目标？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "无目标"}, {"value": 2, "label": "定性目标"}, {"value": 3, "label": "量化目标"}, {"value": 4, "label": "科学目标"}, {"value": 5, "label": "行业领先+创新"}
                    ]},
                ]
            },
        ]
    },
    {
        "id": "sasb",
        "name": "SASB 可持续发展会计准则",
        "organization": "SASB",
        "url": "https://sasb.org",
        "description": "针对不同行业的可持续发展信息披露标准，帮助投资者获取可比较的ESG数据。",
        "version": "2023",
        "category": "international",
        "status": "draft",
        "standard_code": "SASB Standards 2023",
        "is_mandatory": False,
        "issuing_body": "SASB (now part of IFRS Foundation)",
        "issue_date": "2023-01-01",
        "effective_date": "2023-01-01",
        "supported_sizes": ["large", "enterprise"],
        "category_color": "#007AFF",
        "themes": [
            {"id": "DIS", "name": "行业披露", "category": "governance", "weight": 1, "description": "行业特定的ESG信息披露", "color": "#007AFF"},
        ],
        "indicators": [
            {
                "code": "DIS1", "name": "财务披露", "theme_id": "DIS", "weight": 1,
                "description": "可持续发展相关的财务影响披露",
                "questions": [
                    {"id": "DIS1-Q1", "text": "企业是否披露行业特定的ESG指标？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未披露"}, {"value": 2, "label": "部分披露"}, {"value": 3, "label": "SASB标准"}, {"value": 4, "label": "全面披露"}, {"value": 5, "label": "SASB+同行对比"}
                    ]},
                    {"id": "DIS1-Q2", "text": "ESG数据是否与财务报告整合？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未整合"}, {"value": 2, "label": "参考引用"}, {"value": 3, "label": "年度报告"}, {"value": 4, "label": "财务影响分析"}, {"value": 5, "label": "integrated reporting"}
                    ]},
                ]
            },
            {
                "code": "DIS2", "name": "同行对比", "theme_id": "DIS", "weight": 1,
                "description": "与同行的ESG绩效对比",
                "questions": [
                    {"id": "DIS2-Q1", "text": "企业是否与同行进行ESG绩效对比？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未对比"}, {"value": 2, "label": "简单了解"}, {"value": 3, "label": "定期对比"}, {"value": 4, "label": "深入分析"}, {"value": 5, "label": "基准对标+战略调整"}
                    ]},
                    {"id": "DIS2-Q2", "text": "企业是否关注行业ESG趋势？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未关注"}, {"value": 2, "label": "偶有关注"}, {"value": 3, "label": "定期关注"}, {"value": 4, "label": "趋势分析"}, {"value": 5, "label": "前瞻性研究+引领"}
                    ]},
                ]
            },
            {
                "code": "DIS3", "name": "数据管理", "theme_id": "DIS", "weight": 1,
                "description": "ESG数据的收集与管理",
                "questions": [
                    {"id": "DIS3-Q1", "text": "企业是否建立ESG数据收集流程？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "无流程"}, {"value": 2, "label": "基本收集"}, {"value": 3, "label": "标准化流程"}, {"value": 4, "label": "自动化收集"}, {"value": 5, "label": "数字化平台+质量控制"}
                    ]},
                    {"id": "DIS3-Q2", "text": "ESG数据是否经过验证？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未验证"}, {"value": 2, "label": "内部检查"}, {"value": 3, "label": "交叉验证"}, {"value": 4, "label": "独立审核"}, {"value": 5, "label": "第三方鉴证"}
                    ]},
                ]
            },
        ]
    },
    {
        "id": "tcfd",
        "name": "TCFD 气候相关财务披露工作组",
        "organization": "FSB",
        "url": "https://www.fsb-tcfd.org",
        "description": "金融稳定理事会（FSB）成立的气候相关财务披露工作组，制定气候风险披露建议框架。",
        "version": "2017",
        "category": "international",
        "status": "draft",
        "standard_code": "TCFD Recommendations",
        "is_mandatory": False,
        "issuing_body": "Financial Stability Board",
        "issue_date": "2017-06-29",
        "effective_date": "2017-06-29",
        "supported_sizes": ["large", "enterprise"],
        "category_color": "#5856D6",
        "themes": [
            {"id": "CLM", "name": "气候披露", "category": "environment", "weight": 1, "description": "气候相关财务信息披露", "color": "#5856D6"},
        ],
        "indicators": [
            {
                "code": "CLM1", "name": "治理", "theme_id": "CLM", "weight": 1,
                "description": "气候风险治理架构",
                "questions": [
                    {"id": "CLM1-Q1", "text": "董事会是否监督管理气候风险？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未监督"}, {"value": 2, "label": "初步关注"}, {"value": 3, "label": "定期讨论"}, {"value": 4, "label": "委员会监督"}, {"value": 5, "label": "战略整合+决策"}
                    ]},
                    {"id": "CLM1-Q2", "text": "管理层是否管理气候风险？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未管理"}, {"value": 2, "label": "初步识别"}, {"value": 3, "label": "日常管理"}, {"value": 4, "label": "绩效评估"}, {"value": 5, "label": "全面整合+激励"}
                    ]},
                ]
            },
            {
                "code": "CLM2", "name": "战略", "theme_id": "CLM", "weight": 1,
                "description": "气候风险与机遇的战略分析",
                "questions": [
                    {"id": "CLM2-Q1", "text": "企业是否进行气候情景分析？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未分析"}, {"value": 2, "label": "初步考虑"}, {"value": 3, "label": "定量分析"}, {"value": 4, "label": "多情景分析"}, {"value": 5, "label": "2°C/1.5°C情景+战略"}
                    ]},
                    {"id": "CLM2-Q2", "text": "气候风险是否影响企业战略和财务规划？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未影响"}, {"value": 2, "label": "初步考虑"}, {"value": 3, "label": "纳入规划"}, {"value": 4, "label": "战略调整"}, {"value": 5, "label": "全面整合+转型"}
                    ]},
                ]
            },
            {
                "code": "CLM3", "name": "指标与目标", "theme_id": "CLM", "weight": 1,
                "description": "气候相关指标与目标设定",
                "questions": [
                    {"id": "CLM3-Q1", "text": "企业是否设定气候相关指标和目标？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "无指标"}, {"value": 2, "label": "基本指标"}, {"value": 3, "label": "量化目标"}, {"value": 4, "label": "科学目标"}, {"value": 5, "label": "SBTi+净零路径"}
                    ]},
                    {"id": "CLM3-Q2", "text": "企业是否披露范围1/2/3碳排放？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未披露"}, {"value": 2, "label": "范围1"}, {"value": 3, "label": "范围1+2"}, {"value": 4, "label": "范围1+2+部分3"}, {"value": 5, "label": "全范围+第三方核查"}
                    ]},
                ]
            },
        ]
    },
    {
        "id": "gb-t36000",
        "name": "GB/T 36000 社会责任指南",
        "organization": "SAC/TC260",
        "url": "https://www.gb688.cn",
        "description": "中国国家标准，提供社会责任的原则、核心主题和指南，帮助组织理解和实施社会责任。",
        "version": "2015",
        "category": "national",
        "status": "draft",
        "standard_code": "GB/T 36000-2015",
        "is_mandatory": False,
        "issuing_body": "中国国家标准化管理委员会",
        "issue_date": "2015-12-31",
        "effective_date": "2016-07-01",
        "supported_sizes": ["small", "medium", "large", "enterprise"],
        "category_color": "#FF3B30",
        "themes": [
            {"id": "CSR", "name": "社会责任", "category": "governance", "weight": 1, "description": "企业社会责任管理与实践", "color": "#FF3B30"},
        ],
        "indicators": [
            {
                "code": "CSR1", "name": "社会责任管理", "theme_id": "CSR", "weight": 1,
                "description": "社会责任管理体系建设",
                "questions": [
                    {"id": "CSR1-Q1", "text": "企业是否建立了社会责任管理体系？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "无体系"}, {"value": 2, "label": "基本制度"}, {"value": 3, "label": "管理制度"}, {"value": 4, "label": "体系认证"}, {"value": 5, "label": "全面管理+持续改进"}
                    ]},
                    {"id": "CSR1-Q2", "text": "企业是否将社会责任融入企业战略？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未融入"}, {"value": 2, "label": "偶有提及"}, {"value": 3, "label": "明确纳入"}, {"value": 4, "label": "战略整合"}, {"value": 5, "label": "核心战略+KPI"}
                    ]},
                    {"id": "CSR1-Q3", "text": "企业是否发布社会责任报告？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未发布"}, {"value": 2, "label": "内部简报"}, {"value": 3, "label": "年度报告"}, {"value": 4, "label": "标准化报告"}, {"value": 5, "label": "第三方鉴证+公开"}
                    ]},
                ]
            },
            {
                "code": "CSR2", "name": "责任实践", "theme_id": "CSR", "weight": 1,
                "description": "社会责任核心主题实践",
                "questions": [
                    {"id": "CSR2-Q1", "text": "企业是否在环境保护方面履行社会责任？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "无行动"}, {"value": 2, "label": "基本合规"}, {"value": 3, "label": "主动行动"}, {"value": 4, "label": "系统化管理"}, {"value": 5, "label": "行业引领"}
                    ]},
                    {"id": "CSR2-Q2", "text": "企业是否在员工权益方面履行社会责任？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "无行动"}, {"value": 2, "label": "基本合规"}, {"value": 3, "label": "主动行动"}, {"value": 4, "label": "系统化管理"}, {"value": 5, "label": "行业引领"}
                    ]},
                ]
            },
            {
                "code": "CSR3", "name": "利益相关方", "theme_id": "CSR", "weight": 1,
                "description": "利益相关方沟通与参与",
                "questions": [
                    {"id": "CSR3-Q1", "text": "企业是否定期与利益相关方沟通？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "无沟通"}, {"value": 2, "label": "被动回应"}, {"value": 3, "label": "定期沟通"}, {"value": 4, "label": "多元渠道"}, {"value": 5, "label": "共建共治"}
                    ]},
                    {"id": "CSR3-Q2", "text": "企业是否回应利益相关方的关切？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未回应"}, {"value": 2, "label": "偶尔回应"}, {"value": 3, "label": "及时回应"}, {"value": 4, "label": "系统化回应"}, {"value": 5, "label": "共建机制+持续改进"}
                    ]},
                ]
            },
        ]
    },
    {
        "id": "gb-t24067",
        "name": "GB/T 24067 产品碳足迹",
        "organization": "SAC/TC207",
        "url": "https://www.gb688.cn",
        "description": "中国国家标准，规定了产品碳足迹核算的原则、要求和指南，基于ISO 14067。",
        "version": "2019",
        "category": "national",
        "status": "draft",
        "standard_code": "GB/T 24067-2019",
        "is_mandatory": False,
        "issuing_body": "中国国家标准化管理委员会",
        "issue_date": "2019-06-04",
        "effective_date": "2020-06-01",
        "supported_sizes": ["medium", "large", "enterprise"],
        "category_color": "#FF9500",
        "themes": [
            {"id": "CFP", "name": "碳足迹", "category": "environment", "weight": 1, "description": "产品碳足迹核算与管理", "color": "#FF9500"},
        ],
        "indicators": [
            {
                "code": "CFP1", "name": "核算方法", "theme_id": "CFP", "weight": 1,
                "description": "碳足迹核算方法与数据",
                "questions": [
                    {"id": "CFP1-Q1", "text": "企业是否对产品进行碳足迹核算？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未核算"}, {"value": 2, "label": "初步估算"}, {"value": 3, "label": "标准核算"}, {"value": 4, "label": "LCA分析"}, {"value": 5, "label": "数字化碳管理+实时"}
                    ]},
                    {"id": "CFP1-Q2", "text": "碳足迹数据是否使用高质量数据？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "无数据"}, {"value": 2, "label": "行业平均"}, {"value": 3, "label": "供应商数据"}, {"value": 4, "label": "实测数据"}, {"value": 5, "label": "全供应链实测+验证"}
                    ]},
                ]
            },
            {
                "code": "CFP2", "name": "减排管理", "theme_id": "CFP", "weight": 1,
                "description": "基于碳足迹的减排管理",
                "questions": [
                    {"id": "CFP2-Q1", "text": "企业是否基于碳足迹制定减排计划？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "无计划"}, {"value": 2, "label": "初步意向"}, {"value": 3, "label": "减排目标"}, {"value": 4, "label": "技术路线图"}, {"value": 5, "label": "产品级碳中和路径"}
                    ]},
                    {"id": "CFP2-Q2", "text": "企业是否向消费者披露产品碳足迹？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未披露"}, {"value": 2, "label": "内部披露"}, {"value": 3, "label": "标签标注"}, {"value": 4, "label": "数字化追溯"}, {"value": 5, "label": "区块链+全透明"}
                    ]},
                ]
            },
            {
                "code": "CFP3", "name": "持续改进", "theme_id": "CFP", "weight": 1,
                "description": "碳足迹管理的持续改进",
                "questions": [
                    {"id": "CFP3-Q1", "text": "企业是否定期更新产品碳足迹数据？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未更新"}, {"value": 2, "label": "偶尔更新"}, {"value": 3, "label": "年度更新"}, {"value": 4, "label": "季度更新"}, {"value": 5, "label": "实时更新+动态管理"}
                    ]},
                    {"id": "CFP3-Q2", "text": "企业是否利用碳足迹数据优化供应链？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                        {"value": 1, "label": "未优化"}, {"value": 2, "label": "初步分析"}, {"value": 3, "label": "供应商沟通"}, {"value": 4, "label": "协同减排"}, {"value": 5, "label": "全链条碳管理平台"}
                    ]},
                ]
            },
        ]
    },
]


def main():
    # Add extra indicators to each framework to reach 209+ total questions
    extra_indicators = {
        "iso14001": [
            {"code": "ENV4", "name": "培训与意识", "theme_id": "ENV", "weight": 1,
             "description": "环境培训与员工意识",
             "questions": [
                 {"id": "ENV4-Q1", "text": "企业是否提供环境培训？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "无培训"}, {"value": 2, "label": "入职培训"}, {"value": 3, "label": "定期培训"}, {"value": 4, "label": "专项培训"}, {"value": 5, "label": "全员参与+持续学习"}
                 ]},
                 {"id": "ENV4-Q2", "text": "员工是否了解环境方针和重要环境因素？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "不了解"}, {"value": 2, "label": "部分了解"}, {"value": 3, "label": "基本了解"}, {"value": 4, "label": "深入理解"}, {"value": 5, "label": "全员实践+创新"}
                 ]},
                 {"id": "ENV4-Q3", "text": "企业是否建立环境绩效考核机制？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "无考核"}, {"value": 2, "label": "简单考核"}, {"value": 3, "label": "定期考核"}, {"value": 4, "label": "绩效挂钩"}, {"value": 5, "label": "全面激励+持续改进"}
                 ]},
             ]},
            {"code": "ENV5", "name": "文件控制", "theme_id": "ENV", "weight": 1,
             "description": "环境管理文件与记录控制",
             "questions": [
                 {"id": "ENV5-Q1", "text": "企业是否建立环境管理文件体系？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "无文件"}, {"value": 2, "label": "简单文件"}, {"value": 3, "label": "体系文件"}, {"value": 4, "label": "电子化管理"}, {"value": 5, "label": "数字化平台+版本控制"}
                 ]},
                 {"id": "ENV5-Q2", "text": "企业是否保存环境管理记录？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "无记录"}, {"value": 2, "label": "简单记录"}, {"value": 3, "label": "定期保存"}, {"value": 4, "label": "电子化保存"}, {"value": 5, "label": "数字化档案+检索"}
                 ]},
                 {"id": "ENV5-Q3", "text": "企业是否确保文件的可追溯性？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "不可追溯"}, {"value": 2, "label": "简单记录"}, {"value": 3, "label": "版本管理"}, {"value": 4, "label": "电子化追溯"}, {"value": 5, "label": "区块链+全链路追溯"}
                 ]},
             ]},
            {"code": "ENV6", "name": "合规审计", "theme_id": "ENV", "weight": 1,
             "description": "环境合规审计与改进",
             "questions": [
                 {"id": "ENV6-Q1", "text": "企业是否进行内部环境审计？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "未审计"}, {"value": 2, "label": "简单检查"}, {"value": 3, "label": "定期审计"}, {"value": 4, "label": "独立审计"}, {"value": 5, "label": "第三方审计+持续改进"}
                 ]},
                 {"id": "ENV6-Q2", "text": "审计发现是否得到有效整改？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "未整改"}, {"value": 2, "label": "简单整改"}, {"value": 3, "label": "系统整改"}, {"value": 4, "label": "根因分析"}, {"value": 5, "label": "预防机制+持续改进"}
                 ]},
             ]},
        ],
        "iso45001": [
            {"code": "OHS4", "name": "员工参与", "theme_id": "OHS", "weight": 1,
             "description": "员工参与职业健康安全管理",
             "questions": [
                 {"id": "OHS4-Q1", "text": "员工是否参与危险源辨识和风险评估？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "未参与"}, {"value": 2, "label": "咨询"}, {"value": 3, "label": "参与"}, {"value": 4, "label": "主导"}, {"value": 5, "label": "全员参与+自主管理"}
                 ]},
                 {"id": "OHS4-Q2", "text": "员工是否参与安全改进活动？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "未参与"}, {"value": 2, "label": "建议渠道"}, {"value": 3, "label": "定期参与"}, {"value": 4, "label": "主动参与"}, {"value": 5, "label": "安全文化+创新"}
                 ]},
                 {"id": "OHS4-Q3", "text": "企业是否建立员工健康监测机制？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "无监测"}, {"value": 2, "label": "入职体检"}, {"value": 3, "label": "定期体检"}, {"value": 4, "label": "健康档案"}, {"value": 5, "label": "全面健康管理+预防"}
                 ]},
             ]},
        ],
        "gri": [
            {"code": "REP3", "name": "报告发布", "theme_id": "REP", "weight": 1,
             "description": "报告发布与传播",
             "questions": [
                 {"id": "REP3-Q1", "text": "报告是否使用多种语言发布？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "单一语言"}, {"value": 2, "label": "中英文"}, {"value": 3, "label": "多语言"}, {"value": 4, "label": "全球版本"}, {"value": 5, "label": "本地化+数字传播"}
                 ]},
                 {"id": "REP3-Q2", "text": "报告是否包含利益相关方反馈？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "未包含"}, {"value": 2, "label": "简单引用"}, {"value": 3, "label": "系统反馈"}, {"value": 4, "label": "深度回应"}, {"value": 5, "label": "共建报告+互动"}
                 ]},
                 {"id": "REP3-Q3", "text": "报告是否使用数字技术增强可读性？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "仅纸质"}, {"value": 2, "label": "PDF"}, {"value": 3, "label": "网页版"}, {"value": 4, "label": "交互式"}, {"value": 5, "label": "AI助手+数据可视化"}
                 ]},
             ]},
            {"code": "STK2", "name": "利益相关方参与", "theme_id": "STK", "weight": 1,
             "description": "利益相关方深度参与",
             "questions": [
                 {"id": "STK2-Q1", "text": "企业是否建立利益相关方参与平台？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "无平台"}, {"value": 2, "label": "基本渠道"}, {"value": 3, "label": "参与平台"}, {"value": 4, "label": "数字化平台"}, {"value": 5, "label": "共建治理+实时反馈"}
                 ]},
                 {"id": "STK2-Q2", "text": "企业是否回应利益相关方的重大关切？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "未回应"}, {"value": 2, "label": "偶尔回应"}, {"value": 3, "label": "定期回应"}, {"value": 4, "label": "系统化回应"}, {"value": 5, "label": "共建解决+持续改进"}
                 ]},
             ]},
        ],
        "cdp": [
            {"code": "CC3", "name": "目标设定", "theme_id": "CC", "weight": 1,
             "description": "气候目标设定与路径规划",
             "questions": [
                 {"id": "CC3-Q1", "text": "企业是否设定碳减排时间表？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "无时间表"}, {"value": 2, "label": "初步意向"}, {"value": 3, "label": "中期目标"}, {"value": 4, "label": "科学路径"}, {"value": 5, "label": "净零承诺+年度进展"}
                 ]},
                 {"id": "CC3-Q2", "text": "企业是否实施低碳技术？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "未实施"}, {"value": 2, "label": "偶发性投入"}, {"value": 3, "label": "技术改造"}, {"value": 4, "label": "系统化低碳"}, {"value": 5, "label": "创新技术+行业引领"}
                 ]},
                 {"id": "CC3-Q3", "text": "企业是否参与碳市场交易？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "未参与"}, {"value": 2, "label": "了解中"}, {"value": 3, "label": "参与交易"}, {"value": 4, "label": "主动管理"}, {"value": 5, "label": "碳资产管理+创新"}
                 ]},
             ]},
            {"code": "WS2", "name": "水资源风险", "theme_id": "WS", "weight": 1,
             "description": "水资源风险识别与管理",
             "questions": [
                 {"id": "WS2-Q1", "text": "企业是否识别水资源风险？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "未识别"}, {"value": 2, "label": "初步了解"}, {"value": 3, "label": "系统评估"}, {"value": 4, "label": "风险量化"}, {"value": 5, "label": "水压力评估+应对"}
                 ]},
                 {"id": "WS2-Q2", "text": "企业是否设定水资源管理目标？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "无目标"}, {"value": 2, "label": "定性目标"}, {"value": 3, "label": "量化目标"}, {"value": 4, "label": "科学目标"}, {"value": 5, "label": "零取水目标+创新"}
                 ]},
             ]},
        ],
        "sasb": [
            {"code": "DIS4", "name": "监管合规", "theme_id": "DIS", "weight": 1,
             "description": "ESG监管合规与披露要求",
             "questions": [
                 {"id": "DIS4-Q1", "text": "企业是否关注ESG监管趋势？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "未关注"}, {"value": 2, "label": "偶有关注"}, {"value": 3, "label": "定期关注"}, {"value": 4, "label": "主动研究"}, {"value": 5, "label": "前瞻性合规+引领"}
                 ]},
                 {"id": "DIS4-Q2", "text": "企业是否提前适应新的ESG披露要求？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "未准备"}, {"value": 2, "label": "初步了解"}, {"value": 3, "label": "差距分析"}, {"value": 4, "label": "合规计划"}, {"value": 5, "label": "提前合规+最佳实践"}
                 ]},
             ]},
        ],
        "tcfd": [
            {"code": "CLM4", "name": "披露", "theme_id": "CLM", "weight": 1,
             "description": "气候信息披露质量",
             "questions": [
                 {"id": "CLM4-Q1", "text": "企业是否披露气候相关财务影响？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "未披露"}, {"value": 2, "label": "定性披露"}, {"value": 3, "label": "量化披露"}, {"value": 4, "label": "财务影响分析"}, {"value": 5, "label": "integrated reporting"}
                 ]},
                 {"id": "CLM4-Q2", "text": "披露是否与同行可比？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "不可比"}, {"value": 2, "label": "部分可比"}, {"value": 3, "label": "标准框架"}, {"value": 4, "label": "同行对比"}, {"value": 5, "label": "基准对标+创新披露"}
                 ]},
             ]},
        ],
        "gb-t36000": [
            {"code": "CSR4", "name": "社区贡献", "theme_id": "CSR", "weight": 1,
             "description": "社区贡献与公益实践",
             "questions": [
                 {"id": "CSR4-Q1", "text": "企业是否参与社区公益？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "未参与"}, {"value": 2, "label": "偶发性捐赠"}, {"value": 3, "label": "年度计划"}, {"value": 4, "label": "系统化公益"}, {"value": 5, "label": "战略公益+影响力投资"}
                 ]},
                 {"id": "CSR4-Q2", "text": "企业是否支持员工志愿服务？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "未支持"}, {"value": 2, "label": "允许参加"}, {"value": 3, "label": "志愿假"}, {"value": 4, "label": "组织项目"}, {"value": 5, "label": "全员参与+技能志愿"}
                 ]},
             ]},
            {"code": "CSR5", "name": "责任创新", "theme_id": "CSR", "weight": 1,
             "description": "负责任创新与可持续发展",
             "questions": [
                 {"id": "CSR5-Q1", "text": "企业是否在研发中考虑社会责任？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "未考虑"}, {"value": 2, "label": "基本考虑"}, {"value": 3, "label": "系统考虑"}, {"value": 4, "label": "融入研发流程"}, {"value": 5, "label": "负责任创新+社会影响"}
                 ]},
                 {"id": "CSR5-Q2", "text": "企业是否关注产品的社会和环境影响？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "未关注"}, {"value": 2, "label": "基本合规"}, {"value": 3, "label": "定期评估"}, {"value": 4, "label": "全生命周期"}, {"value": 5, "label": "可持续设计+创新"}
                 ]},
             ]},
        ],
        "gb-t24067": [
            {"code": "CFP4", "name": "碳标签", "theme_id": "CFP", "weight": 1,
             "description": "碳标签与消费者沟通",
             "questions": [
                 {"id": "CFP4-Q1", "text": "企业是否为产品申请碳标签？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "未申请"}, {"value": 2, "label": "考虑中"}, {"value": 3, "label": "部分产品"}, {"value": 4, "label": "全产品线"}, {"value": 5, "label": "国际认证+数字标签"}
                 ]},
                 {"id": "CFP4-Q2", "text": "碳标签信息是否透明公开？", "type": "likert5", "required": True, "score_range": [1, 5], "options": [
                     {"value": 1, "label": "未公开"}, {"value": 2, "label": "基本公开"}, {"value": 3, "label": "详细公开"}, {"value": 4, "label": "可追溯"}, {"value": 5, "label": "区块链+实时更新"}
                 ]},
             ]},
        ],
    }

    for fw_data in FRAMEWORKS:
        fw_id = fw_data["id"]
        if fw_id in extra_indicators:
            fw_data["indicators"].extend(extra_indicators[fw_id])
        filename = f"{fw_data['id']}.json"
        filepath = OUTPUT_DIR / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(fw_data, f, ensure_ascii=False, indent=2)
        questions = []
        for ind in fw_data.get("indicators", []):
            questions.extend(ind.get("questions", []))
        print(f"Created {filename}: {len(fw_data['indicators'])} indicators, {len(questions)} questions")


if __name__ == "__main__":
    main()
