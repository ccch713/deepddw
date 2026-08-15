# DDW Wallet 预付费钱包插件

> 问渠（K12 学习 SaaS）的支付与计费底座

## 功能

- **预付费钱包**：每个学生/作者一个余额账户（单位：分，禁止浮点）
- **充值**：微信支付（APIv3 Native）+ 支付宝（手机网站支付）
- **按量扣费**：学习时长、课件生成、语音交互（幂等键）
- **课件分成**：数理化 80%，英语口语 50%
- **退款**：余额原路退回（微信/支付宝）
- **流水查询**：家长端"每一分钱花得明明白白"

## API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/plugins/ddw_wallet/accounts` | 创建账户 |
| GET | `/api/v1/plugins/ddw_wallet/accounts/{user_id}` | 余额查询 |
| POST | `/api/v1/plugins/ddw_wallet/recharges` | 创建充值单 |
| POST | `/api/v1/plugins/ddw_wallet/recharges/notify/wechat` | 微信回调 |
| POST | `/api/v1/plugins/ddw_wallet/recharges/notify/alipay` | 支付宝回调 |
| GET | `/api/v1/plugins/ddw_wallet/recharges/{order_no}` | 充值单查询 |
| POST | `/api/v1/plugins/ddw_wallet/charges` | 按量扣费 |
| POST | `/api/v1/plugins/ddw_wallet/refunds` | 余额退款 |
| POST | `/api/v1/plugins/ddw_wallet/royalties` | 课件分成 |
| GET | `/api/v1/plugins/ddw_wallet/transactions` | 流水查询 |
| GET | `/api/v1/plugins/ddw_wallet/rates` | 计费规则 |

## 配置

所有密钥通过环境变量配置（`.env`，权限 600）：

```bash
DDW_WALLET_WECHAT_MCH_ID=1749100620
DDW_WALLET_WECHAT_APP_ID=wxXXXXXXXX
DDW_WALLET_WECHAT_API_V3_KEY=<32位密钥>
DDW_WALLET_WECHAT_PRIVATE_KEY=/path/apiclient_key.pem
DDW_WALLET_WECHAT_NOTIFY_URL=https://wenquedu.com/api/v1/plugins/ddw_wallet/recharges/notify/wechat
DDW_WALLET_ALIPAY_APP_ID=xxxxxxxx
DDW_WALLET_ALIPAY_PRIVATE_KEY=/path/alipay_private_key.pem
DDW_WALLET_ALIPAY_PUBLIC_KEY=/path/alipay_public_key.pem
DDW_WALLET_ALIPAY_NOTIFY_URL=https://wenquedu.com/api/v1/plugins/ddw_wallet/recharges/notify/alipay
```

## 开发

```bash
# 运行测试
pytest plugins/ddw_wallet/tests/ -v

# lint 检查
ruff check plugins/ddw_wallet/ --select=E,W,F
```

## 依赖

- `wechatpayv3` — 微信支付官方 Python SDK (APIv3)
- `python-alipay-sdk` — 支付宝 SDK
- `sqlalchemy>=2.0` — ORM
- `pydantic>=2.0` — 数据校验
- `fastapi` — Web 框架

## License

Apache-2.0
