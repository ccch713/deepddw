#!/usr/bin/env python3
"""
G1: DAG 执行引擎
DDW AI Hub Orchestration — 长任务无人值守体系

设计原则：
- 轻量级，不依赖 Airflow/Temporal
- 支持 fan-out / fan-in / 条件分支 / 回退循环
- 节点之间通过结构化 handoff 传递数据
- 拓扑锁死执行顺序，数据可提前到达

核心概念：
- Node: 单个 agent 任务（coder/tester/reviewer/...）
- Edge: 节点之间的数据流 + 依赖关系
- DAG: 有向无环图
- Runner: 拓扑排序执行器

支持拓扑类型：
- 串行: A → B → C
- 并行（fan-out）: A → [B, C, D]
- 汇聚（fan-in）: [A, B, C] → D
- 条件分支: A → (if pass: B else: A 重试)
"""

from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import deque


class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class NodeType(str, Enum):
    CODER = "coder"
    TESTER = "tester"
    REVIEWER = "reviewer"
    QUALITY = "quality"
    COMMITTER = "committer"
    ANALYZER = "analyzer"
    RESEARCHER = "researcher"
    CUSTOM = "custom"


@dataclass
class DAGNode:
    """DAG 中的一个节点"""
    id: str
    name: str
    node_type: NodeType = NodeType.CUSTOM
    status: NodeStatus = NodeStatus.PENDING
    
    # 执行配置
    work_fn: Optional[str] = None        # 工作函数名
    work_params: Dict[str, Any] = field(default_factory=dict)  # 工作参数
    model: str = "minimax-m3"            # 使用的模型
    retry_limit: int = 2                 # 重试上限
    timeout_seconds: int = 600           # 超时
    
    # 控制流
    depends_on: List[str] = field(default_factory=list)  # 依赖的节点 ID 列表
    condition: Optional[str] = None       # 条件表达式（如 "result.passed"）
    on_failure: Optional[str] = None      # 失败后回退到哪个节点
    
    # 运行时状态
    started_at: float = 0.0
    finished_at: float = 0.0
    retry_count: int = 0
    result: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    
    @property
    def elapsed_seconds(self) -> float:
        if self.finished_at and self.started_at:
            return self.finished_at - self.started_at
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.node_type.value,
            "status": self.status.value,
            "depends_on": self.depends_on,
            "condition": self.condition,
            "retry_count": self.retry_count,
            "elapsed": round(self.elapsed_seconds, 1),
            "error": self.error,
        }


@dataclass
class DAGEdge:
    """DAG 中的边：节点之间的数据流"""
    source: str
    target: str
    data_key: Optional[str] = None       # 传递的数据键（None = 传递全部）
    condition: Optional[str] = None       # 条件（如 "source.status == 'success'"）


@dataclass
class DAG:
    """有向无环图"""
    name: str
    nodes: Dict[str, DAGNode] = field(default_factory=dict)
    edges: List[DAGEdge] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_node(self, node: DAGNode) -> None:
        self.nodes[node.id] = node
    
    def add_edge(
        self,
        source: str,
        target: str,
        data_key: str = None,
        condition: str = None,
    ) -> None:
        """添加边（自动添加依赖）"""
        self.edges.append(DAGEdge(source, target, data_key, condition))
        if target in self.nodes:
            if source not in self.nodes[target].depends_on:
                self.nodes[target].depends_on.append(source)
    
    def get_ready_nodes(self) -> List[DAGNode]:
        """获取所有依赖已满足的节点"""
        ready = []
        for node in self.nodes.values():
            if node.status != NodeStatus.PENDING:
                continue
            # 所有依赖都成功了？
            deps_ok = all(
                self.nodes[dep].status == NodeStatus.SUCCESS
                for dep in node.depends_on
                if dep in self.nodes
            )
            if deps_ok:
                ready.append(node)
        return ready
    
    def get_blocked_nodes(self) -> List[DAGNode]:
        """获取被阻塞的节点（依赖失败）"""
        blocked = []
        for node in self.nodes.values():
            if node.status != NodeStatus.PENDING:
                continue
            any_failed = any(
                self.nodes[dep].status == NodeStatus.FAILED
                for dep in node.depends_on
                if dep in self.nodes
            )
            if any_failed:
                blocked.append(node)
        return blocked
    
    def has_running(self) -> bool:
        return any(
            n.status == NodeStatus.RUNNING for n in self.nodes.values()
        )
    
    def all_done(self) -> bool:
        return all(
            n.status in (NodeStatus.SUCCESS, NodeStatus.FAILED, NodeStatus.SKIPPED)
            for n in self.nodes.values()
        )
    
    def success_rate(self) -> float:
        total = len(self.nodes)
        if total == 0:
            return 0.0
        succeeded = sum(1 for n in self.nodes.values() if n.status == NodeStatus.SUCCESS)
        return succeeded / total
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [
                {"from": e.source, "to": e.target, "data_key": e.data_key, "condition": e.condition}
                for e in self.edges
            ],
            "success_rate": self.success_rate(),
            "all_done": self.all_done(),
        }
    
    def to_mermaid(self) -> str:
        """生成 Mermaid 图"""
        lines = ["graph LR"]
        for nid, node in self.nodes.items():
            label = f"{node.name}({node.status.value})"
            lines.append(f"    {nid}[\"{label}\"]")
        for edge in self.edges:
            lines.append(f"    {edge.source} --> {edge.target}")
        return "\n".join(lines)


# ── DAG Runner ──

class DAGRunner:
    """
    DAG 执行器
    
    用法:
        dag = DAG(name="hello-world")
        dag.add_node(DAGNode(id="a", name="Step A"))
        dag.add_node(DAGNode(id="b", name="Step B"))
        dag.add_edge("a", "b")
        
        runner = DAGRunner(dag)
        runner.set_executor("a", lambda node: {"ok": True})
        runner.set_executor("b", lambda node: {"ok": True})
        
        result = runner.run()
    """
    
    def __init__(self, dag: DAG, config: Dict = None):
        self.dag = dag
        self.config = config or {}
        self._executors: Dict[str, Callable[[DAGNode], Dict]] = {}
        self._on_node_start: Optional[Callable] = None
        self._on_node_complete: Optional[Callable] = None
        self._on_node_fail: Optional[Callable] = None
        self._abort_flag = False
        
        # 集成其他模块（如果可用）
        self._watchdog = None
        self._scorecard = None
        self._token_monitor = None
    
    def set_executor(self, node_id: str, fn: Callable[[DAGNode], Dict]) -> None:
        """设置节点的执行函数"""
        self._executors[node_id] = fn
    
    def on_node_start(self, fn: Callable[[DAGNode], None]):
        """节点开始时的回调"""
        self._on_node_start = fn
    
    def on_node_complete(self, fn: Callable[[DAGNode, Dict], None]):
        """节点完成时的回调"""
        self._on_node_complete = fn
    
    def on_node_fail(self, fn: Callable[[DAGNode, str], None]):
        """节点失败时的回调"""
        self._on_node_fail = fn
    
    def abort(self):
        """中止执行"""
        self._abort_flag = True
    
    def _execute_node(self, node: DAGNode) -> Dict:
        """执行单个节点"""
        node.status = NodeStatus.RUNNING
        node.started_at = time.time()
        
        if self._on_node_start:
            self._on_node_start(node)
        
        executor = self._executors.get(node.id)
        if not executor:
            node.status = NodeStatus.SKIPPED
            node.error = "无执行器"
            return {}
        
        try:
            result = executor(node)
            node.result = result
            
            # 检查条件
            if node.condition:
                if not eval(node.condition, {"result": result, "node": node}):
                    node.status = NodeStatus.FAILED
                    node.error = f"条件不满足: {node.condition}"
                    if self._on_node_fail:
                        self._on_node_fail(node, node.error)
                    return result
            
            node.status = NodeStatus.SUCCESS
            node.finished_at = time.time()
            
            if self._on_node_complete:
                self._on_node_complete(node, result)
            
            return result
        
        except Exception as e:
            node.status = NodeStatus.FAILED
            node.error = str(e)
            node.finished_at = time.time()
            
            if self._on_node_fail:
                self._on_node_fail(node, node.error)
            
            return {"error": str(e)}
    
    def run(self, max_parallel: int = 3) -> Dict[str, Any]:
        """
        执行整个 DAG
        
        Returns:
            执行结果摘要
        """
        total_start = time.time()
        
        while not self.dag.all_done() and not self._abort_flag:
            ready = self.dag.get_ready_nodes()
            
            if not ready and not self.dag.has_running():
                # 检查是否有被阻塞的节点
                blocked = self.dag.get_blocked_nodes()
                if blocked:
                    for node in blocked:
                        node.status = NodeStatus.SKIPPED
                        node.error = "上游节点失败"
                break
            
            # 执行就绪节点（串行，后续可改为并行）
            for node in ready[:1]:  # 串行执行（单节点）
                self._execute_node(node)
                
                # 失败时触发回退
                if node.status == NodeStatus.FAILED:
                    if node.on_failure and node.retry_count < node.retry_limit:
                        node.retry_count += 1
                        node.status = NodeStatus.PENDING
                        node.error = ""
                        continue
                    # 回退到上游
                    if node.on_failure:
                        target = self.dag.nodes.get(node.on_failure)
                        if target:
                            target.status = NodeStatus.PENDING
                            target.retry_count = target.retry_count + 1
            
            time.sleep(0.1)  # 避免忙等待
        
        total_elapsed = time.time() - total_start
        
        return {
            "name": self.dag.name,
            "success_rate": self.dag.success_rate(),
            "total_nodes": len(self.dag.nodes),
            "succeeded": sum(1 for n in self.dag.nodes.values() if n.status == NodeStatus.SUCCESS),
            "failed": sum(1 for n in self.dag.nodes.values() if n.status == NodeStatus.FAILED),
            "skipped": sum(1 for n in self.dag.nodes.values() if n.status == NodeStatus.SKIPPED),
            "elapsed_seconds": round(total_elapsed, 1),
            "nodes": {nid: n.to_dict() for nid, n in self.dag.nodes.items()},
            "aborted": self._abort_flag,
        }


# ── 便捷构建函数 ──

def create_linear_dag(name: str, steps: List[Dict]) -> DAG:
    """创建线性 DAG (A → B → C)"""
    dag = DAG(name=name)
    
    prev_id = None
    for i, step in enumerate(steps):
        node_id = step.get("id", f"step-{i+1}")
        node = DAGNode(
            id=node_id,
            name=step.get("name", f"Step {i+1}"),
            node_type=NodeType(step.get("type", "custom")),
            model=step.get("model", "minimax-m3"),
            retry_limit=step.get("retry", 2),
        )
        dag.add_node(node)
        
        if prev_id:
            dag.add_edge(prev_id, node_id)
        prev_id = node_id
    
    return dag


def create_fan_out_dag(name: str, source: Dict, targets: List[Dict], collector: Dict = None) -> DAG:
    """创建扇出 DAG (A → [B, C, D] → E)"""
    dag = DAG(name=name)
    
    # 源节点
    src_node = DAGNode(
        id=source.get("id", "source"),
        name=source.get("name", "Source"),
        node_type=NodeType(source.get("type", "custom")),
    )
    dag.add_node(src_node)
    
    # 目标节点
    target_ids = []
    for i, t in enumerate(targets):
        tid = t.get("id", f"target-{i+1}")
        target_ids.append(tid)
        dag.add_node(DAGNode(
            id=tid,
            name=t.get("name", f"Target {i+1}"),
            node_type=NodeType(t.get("type", "custom")),
        ))
        dag.add_edge(src_node.id, tid)
    
    # 汇聚节点
    if collector:
        coll = DAGNode(
            id=collector.get("id", "collector"),
            name=collector.get("name", "Collector"),
            node_type=NodeType(collector.get("type", "custom")),
        )
        dag.add_node(coll)
        for tid in target_ids:
            dag.add_edge(tid, coll.id)
    
    return dag


# ── 自测 ──

if __name__ == "__main__":
    print("=== DAG Runner 自测 ===\n")
    
    # 创建简单 DAG: coder → tester → quality → committer
    dag = create_linear_dag(
        name="标准流水线",
        steps=[
            {"id": "coder", "name": "编码", "type": "coder"},
            {"id": "tester", "name": "测试", "type": "tester"},
            {"id": "quality", "name": "质量检查", "type": "quality"},
            {"id": "committer", "name": "提交", "type": "committer"},
        ],
    )
    
    print("Mermaid 图:")
    print(dag.to_mermaid())
    
    # 创建 runner
    runner = DAGRunner(dag)
    
    def make_executor(name):
        return lambda node: {"step": name, "passed": True}
    
    runner.set_executor("coder", make_executor("coder"))
    runner.set_executor("tester", make_executor("tester"))
    
    # 模拟 quality 检查失败后回退
    call_count = [0]
    def quality_with_retry(node):
        call_count[0] += 1
        if call_count[0] < 2:
            raise Exception("模拟质量检查失败")
        return {"step": "quality", "passed": True}
    
    runner.set_executor("quality", quality_with_retry)
    runner.set_executor("committer", make_executor("committer"))
    
    # 执行
    result = runner.run()
    print(f"\n执行结果: {result['succeeded']}/{result['total_nodes']} 成功, 耗时 {result['elapsed_seconds']}s")
    
    for nid, node in dag.nodes.items():
        print(f"  {nid}: {node.status.value} (retry={node.retry_count})")
    
    print(f"\n全状态: {json.dumps(dag.to_dict(), ensure_ascii=False, indent=2)}")
