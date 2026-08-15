"""DDW Talk A1 ASR - Plugin 入口.

按 SDK PluginBase 协议注册 FastAPI router。提供同步的 job 处理循环
（轻量线程池，避免对生产 ddw-ai-hub 主进程造成负担）。
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from sdk.plugin_base import PluginBase

from . import config
from .router import router, set_store

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """ddw_talk_a1_asr 插件.

    Lifecycle:
        - initialize() : 准备 store + 转写线程池
        - start()      : 启动后台 worker（从 audio_queue 拾取文件）
        - stop()       : 优雅关闭线程池
    """

    name = "ddw_talk_a1_asr"
    version = "0.1.0"
    description = "钉钉 Talk A1 录音采集 + Whisper 转写"

    def __init__(self, app: Any = None, config: Optional[dict] = None, manifest: Any = None, **kwargs) -> None:
        super().__init__(app, config)
        self._executor: Optional[ThreadPoolExecutor] = None
        self._store = None

    async def initialize(self) -> None:
        from .store import JobStore

        config.QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self._store = JobStore()
        set_store(self._store)
        self._executor = ThreadPoolExecutor(
            max_workers=config.MAX_CONCURRENT_JOBS,
            thread_name_prefix="ddw-talk-a1",
        )
        logger.info(
            "ddw_talk_a1_asr initialized: db=%s, max_workers=%d",
            config.DB_PATH,
            config.MAX_CONCURRENT_JOBS,
        )

    async def start(self) -> None:
        # FastAPI include_router 在 setup 阶段完成；start 阶段只需保留扩展点
        if self._executor is None:
            await self.initialize()
        logger.info("ddw_talk_a1_asr started")

    async def stop(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=False)
            self._executor = None
        logger.info("ddw_talk_a1_asr stopped")

    def setup(self) -> None:
        """Legacy SDK v1 注册方式：直接把 router 挂到 host app."""
        self._router = router
        if self.app is not None and hasattr(self.app, "include_router"):
            self.app.include_router(router)

    def submit_job(
        self,
        job_id: str,
        audio_path: str,
        doctor_id: Optional[str] = None,
        patient_name: Optional[str] = None,
        session_type: Optional[str] = None,
    ) -> None:
        """提交一个转写任务到线程池."""
        if self._executor is None:
            from .store import JobStore

            self._store = self._store or JobStore()
            self._executor = ThreadPoolExecutor(
                max_workers=config.MAX_CONCURRENT_JOBS,
                thread_name_prefix="ddw-talk-a1",
            )

        def _runner() -> None:
            assert self._store is not None
            try:
                self._store.update_status(job_id, "transcribing", progress=0.1)
                from .transcriber import TranscriptionError, transcribe_audio

                result = transcribe_audio(audio_path)
                self._store.save_result(
                    job_id=job_id,
                    full_text=result.full_text,
                    segments=result.segments,
                    duration_seconds=result.duration_seconds,
                    language=result.language,
                    model=result.model,
                )
            except (TranscriptionError, FileNotFoundError, RuntimeError) as e:
                logger.exception("transcribe failed: job=%s", job_id)
                self._store.update_status(job_id, "failed", error=str(e))
            except Exception as e:
                logger.exception("unexpected error: job=%s", job_id)
                self._store.update_status(job_id, "failed", error=f"unexpected: {e}")

        self._executor.submit(_runner)
