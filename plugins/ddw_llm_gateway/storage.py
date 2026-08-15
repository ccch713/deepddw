import sqlite3
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

try:
    from .models import ModelRegistration, RouteRule, UsageRecord, KeyCredential, BudgetPolicy  # noqa: E501
except ImportError:
    from models import ModelRegistration, RouteRule, UsageRecord, KeyCredential, BudgetPolicy  # noqa: E501


class Storage:
    """SQLite 存储层"""

    def __init__(self, db_path: str = "data/llm_gateway.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = None

    def init_db(self):
        """初始化数据库表"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # 创建表
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS dw_llm_models (
                model_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                display_name TEXT NOT NULL,
                base_url TEXT NOT NULL,
                api_key TEXT DEFAULT '',
                context_window INTEGER DEFAULT 128000,
                input_price_per_1m REAL DEFAULT 0.0,
                output_price_per_1m REAL DEFAULT 0.0,
                capabilities TEXT DEFAULT '[]',
                priority INTEGER DEFAULT 100,
                weight INTEGER DEFAULT 1,
                is_local INTEGER DEFAULT 0,
                health_status TEXT DEFAULT 'unknown',
                enabled INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS dw_llm_routes (
                rule_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                scene TEXT DEFAULT 'default',
                strategy TEXT DEFAULT 'priority',
                model_chain TEXT NOT NULL,
                max_retries INTEGER DEFAULT 3,
                timeout_seconds REAL DEFAULT 30.0,
                enabled INTEGER DEFAULT 1,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS dw_llm_keys (
                key_id TEXT PRIMARY KEY,
                key_prefix TEXT NOT NULL,
                key_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                plugin_name TEXT DEFAULT '',
                user_id TEXT DEFAULT '',
                allowed_models TEXT DEFAULT '[]',
                rate_limit_rpm INTEGER DEFAULT 60,
                rate_limit_tpm INTEGER DEFAULT 100000,
                budget_cents INTEGER DEFAULT 0,
                budget_period TEXT DEFAULT 'monthly',
                used_cents INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                expires_at TEXT,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS dw_llm_budgets (
                policy_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                scope TEXT NOT NULL,
                scope_id TEXT NOT NULL,
                limit_cents INTEGER NOT NULL,
                period TEXT DEFAULT 'monthly',
                action_on_exceed TEXT DEFAULT 'block',
                current_usage_cents INTEGER DEFAULT 0,
                reset_at TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS dw_llm_audit (
                audit_id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                actor_key_id TEXT,
                target_type TEXT,
                target_id TEXT,
                detail TEXT,
                ip TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS dw_llm_usage (
                record_id TEXT PRIMARY KEY,
                api_key_id TEXT NOT NULL,
                plugin_name TEXT DEFAULT 'ddw_llm_gateway',
                user_id TEXT DEFAULT '',
                model_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                input_cost_cents INTEGER DEFAULT 0,
                output_cost_cents INTEGER DEFAULT 0,
                total_cost_cents INTEGER DEFAULT 0,
                cache_hit INTEGER DEFAULT 0,
                latency_ms INTEGER DEFAULT 0,
                status_code INTEGER DEFAULT 200,
                scene TEXT DEFAULT 'default',
                request_id TEXT DEFAULT '',
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS dw_llm_health (
                model_id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'unknown',
                latency_ms INTEGER DEFAULT 0,
                last_check TEXT,
                error_message TEXT
            );
        """)
        self.conn.commit()

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()

    # 模型管理
    def create_model(self, model: ModelRegistration) -> ModelRegistration:
        """创建模型"""
        now = datetime.utcnow().isoformat()
        self.conn.execute("""
            INSERT OR REPLACE INTO dw_llm_models
            (model_id, provider, display_name, base_url, api_key, context_window,
             input_price_per_1m, output_price_per_1m, capabilities, priority, weight,
             is_local, health_status, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            model.model_id, model.provider, model.display_name, model.base_url,
            model.api_key, model.context_window, model.input_price_per_1m,
            model.output_price_per_1m, json.dumps(model.capabilities),
            model.priority, model.weight, int(model.is_local),
            model.health_status, int(model.enabled), now, now
        ))
        self.conn.commit()
        return model

    def get_model(self, model_id: str) -> Optional[ModelRegistration]:
        """获取模型"""
        cursor = self.conn.execute(
            "SELECT * FROM dw_llm_models WHERE model_id = ?", (model_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_model(row)

    def list_models(self, enabled: Optional[bool] = None, provider: Optional[str] = None) -> List[ModelRegistration]:  # noqa: E501
        """列出模型"""
        query = "SELECT * FROM dw_llm_models WHERE 1=1"
        params = []
        if enabled is not None:
            query += " AND enabled = ?"
            params.append(int(enabled))
        if provider:
            query += " AND provider = ?"
            params.append(provider)
        query += " ORDER BY priority ASC, model_id"

        cursor = self.conn.execute(query, params)
        return [self._row_to_model(row) for row in cursor.fetchall()]

    def update_model(self, model_id: str, updates: Dict[str, Any]) -> Optional[ModelRegistration]:  # noqa: E501
        """更新模型"""
        model = self.get_model(model_id)
        if not model:
            return None

        # 构建更新语句
        set_clauses = []
        params = []
        for key, value in updates.items():
            if hasattr(model, key):
                set_clauses.append(f"{key} = ?")
                if key == "capabilities":
                    params.append(json.dumps(value))
                elif key in ("is_local", "enabled"):
                    params.append(int(value))
                else:
                    params.append(value)

        if not set_clauses:
            return model

        set_clauses.append("updated_at = ?")
        params.append(datetime.utcnow().isoformat())
        params.append(model_id)

        sql = f"UPDATE dw_llm_models SET {', '.join(set_clauses)} WHERE model_id = ?"
        self.conn.execute(sql, params)
        self.conn.commit()

        return self.get_model(model_id)

    def delete_model(self, model_id: str) -> bool:
        """删除模型"""
        cursor = self.conn.execute(
            "DELETE FROM dw_llm_models WHERE model_id = ?", (model_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def _row_to_model(self, row: sqlite3.Row) -> ModelRegistration:
        """将数据库行转换为 ModelRegistration"""
        return ModelRegistration(
            model_id=row["model_id"],
            provider=row["provider"],
            display_name=row["display_name"],
            base_url=row["base_url"],
            api_key=row["api_key"],
            context_window=row["context_window"],
            input_price_per_1m=row["input_price_per_1m"],
            output_price_per_1m=row["output_price_per_1m"],
            capabilities=json.loads(row["capabilities"]),
            priority=row["priority"],
            weight=row["weight"],
            is_local=bool(row["is_local"]),
            health_status=row["health_status"],
            enabled=bool(row["enabled"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"])
        )

    # 路由规则管理
    def create_route(self, route: RouteRule) -> RouteRule:
        """创建路由规则"""
        now = datetime.utcnow().isoformat()
        self.conn.execute("""
            INSERT OR REPLACE INTO dw_llm_routes
            (rule_id, name, scene, strategy, model_chain, max_retries, timeout_seconds,
            enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            route.rule_id, route.name, route.scene, route.strategy,
            json.dumps(route.model_chain), route.max_retries,
            route.timeout_seconds, int(route.enabled), now
        ))
        self.conn.commit()
        return route

    def get_route(self, rule_id: str) -> Optional[RouteRule]:
        """获取路由规则"""
        cursor = self.conn.execute(
            "SELECT * FROM dw_llm_routes WHERE rule_id = ?", (rule_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_route(row)

    def list_routes(self, scene: Optional[str] = None) -> List[RouteRule]:
        """列出路由规则"""
        query = "SELECT * FROM dw_llm_routes WHERE 1=1"
        params = []
        if scene:
            query += " AND scene = ?"
            params.append(scene)
        query += " ORDER BY created_at DESC"

        cursor = self.conn.execute(query, params)
        return [self._row_to_route(row) for row in cursor.fetchall()]

    def update_route(self, rule_id: str, updates: Dict[str, Any]) -> Optional[RouteRule]:  # noqa: E501
        """更新路由规则"""
        route = self.get_route(rule_id)
        if not route:
            return None

        set_clauses = []
        params = []
        for key, value in updates.items():
            if hasattr(route, key):
                set_clauses.append(f"{key} = ?")
                if key == "model_chain":
                    params.append(json.dumps(value))
                elif key == "enabled":
                    params.append(int(value))
                else:
                    params.append(value)

        if not set_clauses:
            return route

        params.append(rule_id)
        sql = f"UPDATE dw_llm_routes SET {', '.join(set_clauses)} WHERE rule_id = ?"
        self.conn.execute(sql, params)
        self.conn.commit()

        return self.get_route(rule_id)

    def delete_route(self, rule_id: str) -> bool:
        """删除路由规则"""
        cursor = self.conn.execute(
            "DELETE FROM dw_llm_routes WHERE rule_id = ?", (rule_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def _row_to_route(self, row: sqlite3.Row) -> RouteRule:
        """将数据库行转换为 RouteRule"""
        return RouteRule(
            rule_id=row["rule_id"],
            name=row["name"],
            scene=row["scene"],
            strategy=row["strategy"],
            model_chain=json.loads(row["model_chain"]),
            max_retries=row["max_retries"],
            timeout_seconds=row["timeout_seconds"],
            enabled=bool(row["enabled"]),
            created_at=datetime.fromisoformat(row["created_at"])
        )

    # 用量记录
    def create_usage_record(self, record: UsageRecord) -> UsageRecord:
        """创建用量记录"""
        now = datetime.utcnow().isoformat()
        self.conn.execute("""
            INSERT INTO dw_llm_usage
            (record_id, api_key_id, plugin_name, user_id, model_id, provider,
             input_tokens, output_tokens, total_tokens, input_cost_cents,
             output_cost_cents, total_cost_cents, cache_hit, latency_ms,
             status_code, scene, request_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.record_id, record.api_key_id, record.plugin_name,
            record.user_id, record.model_id, record.provider,
            record.input_tokens, record.output_tokens, record.total_tokens,
            record.input_cost_cents, record.output_cost_cents,
            record.total_cost_cents, int(record.cache_hit), record.latency_ms,
            record.status_code, record.scene, record.request_id, now
        ))
        self.conn.commit()
        return record

    def get_usage_records(self, limit: int = 100, offset: int = 0) -> List[UsageRecord]:
        """获取用量记录"""
        cursor = self.conn.execute(
            "SELECT * FROM dw_llm_usage ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
        return [self._row_to_usage(row) for row in cursor.fetchall()]

    def _row_to_usage(self, row: sqlite3.Row) -> UsageRecord:
        """将数据库行转换为 UsageRecord"""
        return UsageRecord(
            record_id=row["record_id"],
            api_key_id=row["api_key_id"],
            plugin_name=row["plugin_name"],
            user_id=row["user_id"],
            model_id=row["model_id"],
            provider=row["provider"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            total_tokens=row["total_tokens"],
            input_cost_cents=row["input_cost_cents"],
            output_cost_cents=row["output_cost_cents"],
            total_cost_cents=row["total_cost_cents"],
            cache_hit=bool(row["cache_hit"]),
            latency_ms=row["latency_ms"],
            status_code=row["status_code"],
            scene=row["scene"],
            request_id=row["request_id"],
            created_at=datetime.fromisoformat(row["created_at"])
        )

    # API Key 管理
    def create_key(self, key: KeyCredential) -> KeyCredential:
        """创建 API Key"""
        now = datetime.utcnow().isoformat()
        self.conn.execute("""
            INSERT INTO dw_llm_keys
            (key_id, key_prefix, key_hash, name, plugin_name, user_id,
             allowed_models, rate_limit_rpm, rate_limit_tpm, budget_cents,
             budget_period, used_cents, status, expires_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            key.key_id, key.key_prefix, key.key_hash, key.name,
            key.plugin_name, key.user_id, json.dumps(key.allowed_models),
            key.rate_limit_rpm, key.rate_limit_tpm, key.budget_cents,
            key.budget_period, key.used_cents, key.status,
            key.expires_at.isoformat() if key.expires_at else None,
            now, now
        ))
        self.conn.commit()
        return key

    def get_key(self, key_id: str) -> Optional[KeyCredential]:
        """获取 API Key"""
        cursor = self.conn.execute(
            "SELECT * FROM dw_llm_keys WHERE key_id = ?", (key_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_key(row)

    def get_key_by_hash(self, key_hash: str) -> Optional[KeyCredential]:
        """通过哈希获取 API Key"""
        cursor = self.conn.execute(
            "SELECT * FROM dw_llm_keys WHERE key_hash = ?", (key_hash,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_key(row)

    def list_keys(self, plugin_name: Optional[str] = None, status: Optional[str] = None) -> List[KeyCredential]:  # noqa: E501
        """列出 API Keys"""
        query = "SELECT * FROM dw_llm_keys WHERE 1=1"
        params = []
        if plugin_name:
            query += " AND plugin_name = ?"
            params.append(plugin_name)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"

        cursor = self.conn.execute(query, params)
        return [self._row_to_key(row) for row in cursor.fetchall()]

    def update_key(self, key_id: str, updates: Dict[str, Any]) -> Optional[KeyCredential]:  # noqa: E501
        """更新 API Key"""
        key = self.get_key(key_id)
        if not key:
            return None

        set_clauses = []
        params = []
        for key_name, value in updates.items():
            if hasattr(key, key_name):
                set_clauses.append(f"{key_name} = ?")
                if key_name == "allowed_models":
                    params.append(json.dumps(value))
                elif key_name == "expires_at":
                    params.append(value.isoformat() if value else None)
                else:
                    params.append(value)

        if not set_clauses:
            return key

        set_clauses.append("updated_at = ?")
        params.append(datetime.utcnow().isoformat())
        params.append(key_id)

        sql = f"UPDATE dw_llm_keys SET {', '.join(set_clauses)} WHERE key_id = ?"
        self.conn.execute(sql, params)
        self.conn.commit()

        return self.get_key(key_id)

    def delete_key(self, key_id: str) -> bool:
        """删除 API Key"""
        cursor = self.conn.execute(
            "DELETE FROM dw_llm_keys WHERE key_id = ?", (key_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def _row_to_key(self, row: sqlite3.Row) -> KeyCredential:
        """将数据库行转换为 KeyCredential"""
        return KeyCredential(
            key_id=row["key_id"],
            key_prefix=row["key_prefix"],
            key_hash=row["key_hash"],
            name=row["name"],
            plugin_name=row["plugin_name"],
            user_id=row["user_id"],
            allowed_models=json.loads(row["allowed_models"]),
            rate_limit_rpm=row["rate_limit_rpm"],
            rate_limit_tpm=row["rate_limit_tpm"],
            budget_cents=row["budget_cents"],
            budget_period=row["budget_period"],
            used_cents=row["used_cents"],
            status=row["status"],
            expires_at=datetime.fromisoformat(
                row["expires_at"]) if row["expires_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"])
        )

    # 预算策略管理
    def create_budget(self, policy: BudgetPolicy) -> BudgetPolicy:
        """创建预算策略"""
        now = datetime.utcnow().isoformat()
        self.conn.execute("""
            INSERT OR REPLACE INTO dw_llm_budgets
            (policy_id, name, scope, scope_id, limit_cents, period,
             action_on_exceed, current_usage_cents, reset_at, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            policy.policy_id, policy.name, policy.scope, policy.scope_id,
            policy.limit_cents, policy.period, policy.action_on_exceed,
            policy.current_usage_cents,
            policy.reset_at.isoformat() if policy.reset_at else None,
            int(policy.enabled), now
        ))
        self.conn.commit()
        return policy

    def get_budget(self, policy_id: str) -> Optional[BudgetPolicy]:
        """获取预算策略"""
        cursor = self.conn.execute(
            "SELECT * FROM dw_llm_budgets WHERE policy_id = ?", (policy_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_budget(row)

    def list_budgets(self, scope: Optional[str] = None, scope_id: Optional[str] = None) -> List[BudgetPolicy]:  # noqa: E501
        """列出预算策略"""
        query = "SELECT * FROM dw_llm_budgets WHERE 1=1"
        params = []
        if scope:
            query += " AND scope = ?"
            params.append(scope)
        if scope_id:
            query += " AND scope_id = ?"
            params.append(scope_id)
        query += " ORDER BY created_at DESC"

        cursor = self.conn.execute(query, params)
        return [self._row_to_budget(row) for row in cursor.fetchall()]

    def update_budget(self, policy_id: str, updates: Dict[str, Any]) -> Optional[BudgetPolicy]:  # noqa: E501
        """更新预算策略"""
        policy = self.get_budget(policy_id)
        if not policy:
            return None

        set_clauses = []
        params = []
        for key, value in updates.items():
            if hasattr(policy, key):
                set_clauses.append(f"{key} = ?")
                if key == "reset_at":
                    params.append(value.isoformat() if value else None)
                elif key == "enabled":
                    params.append(int(value))
                else:
                    params.append(value)

        if not set_clauses:
            return policy

        params.append(policy_id)
        sql = f"UPDATE dw_llm_budgets SET {', '.join(set_clauses)} WHERE policy_id = ?"
        self.conn.execute(sql, params)
        self.conn.commit()

        return self.get_budget(policy_id)

    def delete_budget(self, policy_id: str) -> bool:
        """删除预算策略"""
        cursor = self.conn.execute(
            "DELETE FROM dw_llm_budgets WHERE policy_id = ?", (policy_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def _row_to_budget(self, row: sqlite3.Row) -> BudgetPolicy:
        """将数据库行转换为 BudgetPolicy"""
        return BudgetPolicy(
            policy_id=row["policy_id"],
            name=row["name"],
            scope=row["scope"],
            scope_id=row["scope_id"],
            limit_cents=row["limit_cents"],
            period=row["period"],
            action_on_exceed=row["action_on_exceed"],
            current_usage_cents=row["current_usage_cents"],
            reset_at=datetime.fromisoformat(
                row["reset_at"]) if row["reset_at"] else None,
            enabled=bool(row["enabled"]),
            created_at=datetime.fromisoformat(row["created_at"])
        )

    # 审计日志
    def create_audit_log(self, action: str, actor_key_id: Optional[str] = None,
                        target_type: Optional[str] = None, target_id: Optional[str] = None,  # noqa: E501
                        detail: Optional[str] = None, ip: Optional[str] = None) -> str:
        """创建审计日志"""
        import uuid
        audit_id = uuid.uuid4().hex[:16]
        now = datetime.utcnow().isoformat()

        self.conn.execute("""
            INSERT INTO dw_llm_audit
            (audit_id, action, actor_key_id, target_type, target_id, detail, ip,
            created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (audit_id, action, actor_key_id, target_type, target_id, detail, ip, now))
        self.conn.commit()
        return audit_id

    def get_audit_logs(self, action: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:  # noqa: E501
        """获取审计日志"""
        query = "SELECT * FROM dw_llm_audit WHERE 1=1"
        params = []
        if action:
            query += " AND action = ?"
            params.append(action)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = self.conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    # 健康状态
    def update_health_status(self, model_id: str, status: str, latency_ms: int = 0, error_message: str = ""):  # noqa: E501
        """更新模型健康状态"""
        now = datetime.utcnow().isoformat()
        self.conn.execute("""
            INSERT OR REPLACE INTO dw_llm_health
            (model_id, status, latency_ms, last_check, error_message)
            VALUES (?, ?, ?, ?, ?)
        """, (model_id, status, latency_ms, now, error_message))
        self.conn.commit()

        # 同时更新模型表
        self.conn.execute("""
            UPDATE dw_llm_models SET health_status = ?, updated_at = ? WHERE model_id =
            ?
        """, (status, now, model_id))
        self.conn.commit()

    def get_health_status(self, model_id: str) -> Optional[Dict[str, Any]]:
        """获取模型健康状态"""
        cursor = self.conn.execute(
            "SELECT * FROM dw_llm_health WHERE model_id = ?", (model_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
