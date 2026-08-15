# deepDDW 0.1 — 网关（FastAPI + MCP 双协议 + 知识库/记忆）容器
# 使用: docker compose -f deepddw-compose.yml up -d --build
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 依赖层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY core ./core
COPY sdk ./sdk
COPY plugins ./plugins
COPY frontend ./frontend
COPY config ./config
COPY conftest.py pytest.ini requirements.txt VERSION ./

# 数据目录（挂载卷）
RUN mkdir -p /app/data && chmod -R a+rw /app/data

EXPOSE 8500

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=15s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8500/health')"

CMD ["python", "-m", "uvicorn", "core.main:app", "--host", "0.0.0.0", "--port", "8500"]
