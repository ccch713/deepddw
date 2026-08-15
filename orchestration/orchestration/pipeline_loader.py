#!/usr/bin/env python3
"""
G3: Pipeline 模板加载器
DDW AI Hub Orchestration — 长任务无人值守体系

功能：
- 加载 YAML 编排模板
- 解析六层配置
- 构建 DAG 对象
- 验证 YAML 结构完整性
"""

from __future__ import annotations
import yaml
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List

# 导入 DAG 模块
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from runtime.dag_runtime import (
    DAG, DAGNode, DAGEdge, DAGRunner, NodeType, NodeStatus,
    create_linear_dag, create_fan_out_dag,
)


# ── 模板加载器 ──

class PipelineLoader:
    """
    YAML 模板加载器
    
    用法:
        loader = PipelineLoader()
        pipeline = loader.load("templates/pipeline_template.yaml")
        
        dag = pipeline.build_dag()
        runner = DAGRunner(dag)
        result = runner.run()
    """
    
    def __init__(self, template_dir: str = None):
        if template_dir:
            self.template_dir = Path(template_dir)
        else:
            self.template_dir = Path(__file__).parent.parent / "templates"
    
    def load(self, template_name: str) -> "Pipeline":
        """加载 YAML 模板"""
        template_path = self.template_dir / template_name
        if not template_path.suffix:
            template_path = template_path.with_suffix(".yaml")
        
        if not template_path.exists():
            raise FileNotFoundError(f"模板不存在: {template_path}")
        
        with open(template_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        
        return Pipeline(raw, template_path)
    
    def list_templates(self) -> List[str]:
        """列出所有可用模板"""
        if not self.template_dir.exists():
            return []
        return [
            f.name for f in self.template_dir.glob("*.yaml")
        ]


class Pipeline:
    """
    解析后的 Pipeline 对象
    
    提供:
    - 配置访问（按层）
    - 构建 DAG
    - 导出配置
    """
    
    def __init__(self, raw: Dict, path: Path = None):
        self.raw = raw
        self.path = path
        self._validate()
    
    def _validate(self):
        """验证 YAML 结构完整性"""
        required_sections = ["pipeline", "orchestration"]
        for section in required_sections:
            if section not in self.raw:
                raise ValueError(f"缺少必需段: {section}")
        
        if "nodes" not in self.raw.get("orchestration", {}):
            raise ValueError("orchestration.nodes 未定义")
    
    @property
    def name(self) -> str:
        return self.raw.get("pipeline", {}).get("name", "unnamed")
    
    @property
    def version(self) -> str:
        return self.raw.get("pipeline", {}).get("version", "0.0.0")
    
    @property
    def defaults(self) -> Dict:
        return self.raw.get("pipeline", {}).get("defaults", {})
    
    def get_nodes(self) -> List[Dict]:
        return self.raw["orchestration"]["nodes"]
    
    def get_model_config(self, node_id: str) -> Dict:
        """获取指定节点的模型配置"""
        models = self.raw.get("models", {})
        node_model = models.get(node_id, {})
        default = models.get("default", {})
        return {**default, **node_model}
    
    def get_container_config(self, node_id: str) -> Dict:
        """获取指定节点的容器配置"""
        containers = self.raw.get("containers", {})
        node_container = containers.get(node_id, {})
        default = containers.get("default", {})
        return {**default, **node_container}
    
    def get_safety_config(self, node_id: str = None) -> Dict:
        """获取安全配置"""
        safety = self.raw.get("safety", {})
        global_cfg = safety.get("global", {})
        if node_id:
            per_node = safety.get("per_node", {}).get(node_id, {})
            return {**global_cfg, **per_node}
        return global_cfg
    
    def get_prompt(self, node_type: str) -> str:
        """获取指定类型的 system prompt"""
        prompts = self.raw.get("prompts", {})
        node_prompt = prompts.get(node_type, "")
        default = prompts.get("default", "")
        return node_prompt or default
    
    def get_scorecard_config(self) -> Dict:
        return self.raw.get("scorecard", {})
    
    def get_monitoring_config(self) -> Dict:
        return self.raw.get("monitoring", {})
    
    def build_dag(self) -> DAG:
        """
        根据 YAML 配置构建 DAG 对象
        
        Returns:
            可执行的 DAG 对象
        """
        dag = DAG(name=self.name)
        
        # 1. 创建所有节点
        for node_def in self.get_nodes():
            node = DAGNode(
                id=node_def["id"],
                name=node_def.get("name", node_def["id"]),
                node_type=NodeType(node_def.get("type", "custom")),
                model=node_def.get("model", self.defaults.get("model", "minimax-m3")),
                retry_limit=node_def.get("retry_limit", self.defaults.get("retry_limit", 2)),
                timeout_seconds=node_def.get("timeout", self.defaults.get("timeout_seconds", 600)),
                depends_on=node_def.get("depends_on", []),
                work_params=node_def.get("params", {}),
            )
            dag.add_node(node)
        
        # 2. 添加边（从 depends_on 自动创建）
        for node_def in self.get_nodes():
            target = node_def["id"]
            for dep in node_def.get("depends_on", []):
                # 检查是否已存在
                exists = any(
                    e.source == dep and e.target == target
                    for e in dag.edges
                )
                if not exists:
                    dag.add_edge(dep, target)
        
        # 3. 回退规则
        topology = self.raw.get("topology", {})
        rollback = topology.get("rollback", {})
        for rule_name, rule in rollback.items():
            trigger_node = rule.get("trigger", "").split(".")[0]
            if trigger_node in dag.nodes:
                dag.nodes[trigger_node].on_failure = rule.get("rollback_to")
        
        return dag
    
    def export_config(self) -> Dict:
        """导出完整配置为 dict"""
        return {
            "name": self.name,
            "version": self.version,
            "nodes": [n for n in self.get_nodes()],
            "models": self.raw.get("models", {}),
            "safety": self.raw.get("safety", {}),
            "scorecard": self.get_scorecard_config(),
            "monitoring": self.get_monitoring_config(),
        }


# ── 便捷函数 ──

def load_and_run(
    template_name: str,
    task_params: Dict = None,
    template_dir: str = None,
) -> Dict:
    """
    加载 YAML 模板 → 构建 DAG → 执行
    
    这是最便捷的一键函数。
    
    Usage:
        result = load_and_run("pipeline_template.yaml", {"task": "重构 User 模块"})
    """
    loader = PipelineLoader(template_dir)
    pipeline = loader.load(template_name)
    dag = pipeline.build_dag()
    
    runner = DAGRunner(dag, config=pipeline.get_safety_config())
    
    # TODO: 集成真实的 agent 执行（delegate_task / subagent）
    # 目前只返回 DAG 结构
    
    return {
        "pipeline": pipeline.name,
        "dag": dag.to_dict(),
        "status": "ready",
    }


# ── 自测 ──

if __name__ == "__main__":
    print("=== Pipeline Loader 自测 ===\n")
    
    template_dir = Path(__file__).parent.parent / "templates"
    loader = PipelineLoader(str(template_dir))
    
    # 列出模板
    templates = loader.list_templates()
    print(f"可用模板: {templates}")
    
    # 加载模板
    pipeline = loader.load("pipeline_template.yaml")
    print(f"\nPipeline: {pipeline.name} v{pipeline.version}")
    print(f"节点数: {len(pipeline.get_nodes())}")
    
    for node_def in pipeline.get_nodes():
        print(f"  - {node_def['id']}: {node_def['name']} ({node_def.get('type', '?')})")
        print(f"    depends_on: {node_def.get('depends_on', [])}")
    
    # 构建 DAG
    dag = pipeline.build_dag()
    print(f"\nDAG: {dag.name}")
    print(dag.to_mermaid())
    
    # 模型配置
    print(f"\nCoder 模型配置: {json.dumps(pipeline.get_model_config('coder'), indent=2)}")
    
    # 安全配置
    print(f"\n安全配置: {json.dumps(pipeline.get_safety_config(), indent=2)}")
    
    # Scorecard
    print(f"\nScorecard: enabled={pipeline.get_scorecard_config().get('enabled')}")
    
    # 导出
    export = pipeline.export_config()
    print(f"\n导出配置: {json.dumps(export['name'], ensure_ascii=False)} v{export['version']}")
