import yaml
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter

from . import PLUGIN_NAME, VERSION

PLUGIN_DIR = Path(__file__).parent


def _load_yaml() -> Dict[str, Any]:
    with open(PLUGIN_DIR / "departments.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _list_departments_sorted() -> List[Dict[str, Any]]:
    data = _load_yaml()
    depts = []
    for dept_id, dept in data.get("departments", {}).items():
        depts.append(
            {
                "id": dept_id,
                "name": dept["name"],
                "emoji": dept["emoji"],
                "priority": dept.get("priority", 0),
                "skills": dept.get("skills", []),
                "permissions": dept.get("permissions", []),
            }
        )
    depts.sort(key=lambda d: -d["priority"])
    return depts


def build_router() -> APIRouter:
    router = APIRouter(prefix=f"/api/v1/plugins/{PLUGIN_NAME}")

    @router.get("/health")
    def health():
        return {
            "plugin": PLUGIN_NAME,
            "version": VERSION,
            "status": "ok",
            "departments": len(_load_yaml().get("departments", {})),
        }

    @router.get("/departments")
    def list_departments():
        return _list_departments_sorted()

    @router.post("/route")
    def route_message(body: Dict[str, str]):
        text = body.get("text", "")
        data = _load_yaml()
        depts = data.get("departments", {})

        # 显式路由：@部门名
        if text.startswith("@"):
            target = text.split(" ", 1)[0][1:]
            for dept_id, dept in depts.items():
                if target in (dept["name"], dept_id, dept["name"].replace("部", "")):
                    return {"department": dept_id, "method": "explicit"}

        # 关键词路由
        best_match = None
        best_score = 0
        for dept_id, dept in depts.items():
            keywords = dept.get("keywords", [])
            if any(kw in text for kw in keywords):
                prio = dept.get("priority", 0)
                if prio > best_score:
                    best_score = prio
                    best_match = dept_id

        if best_match:
            return {"department": best_match, "method": "keyword"}

        # fallback
        return {"department": "admin", "method": "fallback"}

    @router.get("/collaboration/{dept_id}")
    def get_collaboration(dept_id: str):
        data = _load_yaml()
        matrix = data.get("collaboration_matrix", {})
        targets = matrix.get(dept_id, [])
        return targets

    @router.get("/config")
    def get_config():
        return {
            "departments": {
                "ceo": {"enabled": True, "display": "CEO战略中心"},
                "product": {"enabled": True, "display": "产品部"},
                "design": {"enabled": True, "display": "设计部"},
                "dev": {"enabled": True, "display": "研发部"},
                "marketing": {"enabled": True, "display": "市场营销部"},
                "sales": {"enabled": True, "display": "销售部"},
                "finance": {"enabled": True, "display": "财务部"},
                "cs": {"enabled": True, "display": "客户服务部"},
                "legal": {"enabled": True, "display": "法务部"},
                "admin": {"enabled": True, "display": "行政运营部"},
                "quant": {"enabled": True, "display": "量化交易部"},
            },
            "routing": {
                "mode": "keyword",
                "fallback_agent": "admin",
                "separator": "@",
            },
            "collaboration": {
                "allow_cross_dept": True,
                "require_approval_from": "ceo",
            },
        }

    return router
