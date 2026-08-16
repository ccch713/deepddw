#!/usr/bin/env bash
# deepDDW 自签 TLS 证书生成（P1-2）
# 用法: ./scripts/gen_self_signed_cert.sh [证书目录] [域名]
# 默认: data/tls/  cert CN=localhost, SAN 含 127.0.0.1/localhost
# 产出: cert.pem + key.pem（有效期 365 天；到期重跑本脚本续期）
# 依赖: openssl（macOS/Linux 自带）
set -euo pipefail

CERT_DIR="${1:-./data/tls}"
DOMAIN="${2:-localhost}"
mkdir -p "$CERT_DIR"

echo "[$(date +%H:%M:%S)] 生成自签证书 → $CERT_DIR（CN=$DOMAIN，1 年有效）"

openssl req -x509 -newkey rsa:2048 -sha256 -days 365 -nodes \
  -keyout "$CERT_DIR/key.pem" \
  -out "$CERT_DIR/cert.pem" \
  -subj "/CN=${DOMAIN}" \
  -addext "subjectAltName=DNS:${DOMAIN},DNS:localhost,IP:127.0.0.1" 2>/dev/null

chmod 600 "$CERT_DIR/key.pem"
echo "完成: $CERT_DIR/cert.pem + $CERT_DIR/key.pem"
echo "启用: config/deployment.yaml 设 security.tls.enabled=true + cert_file/key_file 指向上述路径，重启服务"
echo "续期: 1 年后重跑本脚本即可（覆盖同名文件，无需改配置）"
