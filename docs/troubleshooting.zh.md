# 排障指南

这份文档记录常见启动、配置和运行问题。排查时建议先跑不触网检查，再跑真实注册。

## 1. 基础自检

```bash
python3 -m py_compile *.py
PYTHONPATH=. pytest -q
```

如果这里失败，先修本地 Python 环境或依赖。

## 2. 环境变量未配置

常见表现：

- 提示 `HEROSMS_API_KEY` 为空
- CPA 请求提示 management key missing
- Sub2API 登录失败
- Cloud Mail 无法获取 token

处理方式：

```bash
cp .env.example .env
set -a
source .env
set +a
```

然后确认当前 shell 已读到变量：

```bash
python3 - <<'PY'
import os
for key in [
    'HEROSMS_API_KEY',
    'GPTFREE_PANEL_MODE',
    'GPTFREE_CPA_URL',
    'GPTFREE_CPA_MANAGEMENT_KEY',
    'GPTFREE_CLOUD_MAIL_URL',
    'GPTFREE_EMAIL_DOMAIN',
]:
    print(key, 'set' if os.environ.get(key) else 'missing')
PY
```

## 3. Chrome / CDP 连接失败

常见表现：

- 访问 `http://127.0.0.1:9336/json/list` 失败
- 没有 page target
- websocket 连接失败

检查：

```bash
curl -sS http://127.0.0.1:${GPTFREE_CDP_PORT:-9336}/json/list
```

如果没有返回 JSON，需要先启动带 remote debugging 的 Chrome/Chromium。

## 4. HeroSMS 买号失败

常见原因：

- `HEROSMS_API_KEY` 不正确
- 当前国家无库存
- `GPTFREE_HEROSMS_MAX_PRICE` 太低
- 服务代码不支持当前目标

建议先用脚本自己的日志判断，不要用购买接口做库存探测，避免误买号码。

## 5. 收不到短信验证码

常见原因：

- OpenAI 拒绝该号码段
- 短信服务商没有收到码
- 等待时间太短
- 页面提交失败，实际没有触发短信

建议：

- 看页面是否进入验证码输入页
- 看 HeroSMS `getStatus` 轮询日志
- 超时后确认激活是否被取消

## 6. Cloud Mail 邮箱验证码失败

常见原因：

- 邮箱没有创建成功
- API token 获取失败
- OpenAI 邮件延迟
- HTML 里存在多个 6 位数字，提取到了错误值

建议检查：

- Cloud Mail API base URL 是否正确
- 管理员邮箱/密码是否正确
- `GPTFREE_EMAIL_DOMAIN` 是否是收信域名

## 7. CPA 导入失败

常见原因：

- `GPTFREE_CPA_URL` 不可访问
- `GPTFREE_CPA_MANAGEMENT_KEY` 不正确
- OAuth callback state 不匹配
- OpenAI consent 页面没有成功点击

建议先检查 CPA 管理接口是否能返回 auth URL，再看 callback 和 status 结果。

## 8. Sub2API 导入失败

常见原因：

- 管理员账号密码错误
- `redirect_uri` 和面板配置不一致
- exchange-code 失败
- 创建账号接口字段不兼容

建议先跑：

```bash
python3 gptfree_sub2api_dry_run.py
```

## 9. 真实注册前检查清单

- [ ] `python3 -m py_compile *.py` 通过
- [ ] `PYTHONPATH=. pytest -q` 通过
- [ ] `.env` 已配置
- [ ] Chrome/CDP 可访问
- [ ] 短信服务余额和库存确认
- [ ] 邮箱服务可创建并收信
- [ ] CPA 或 Sub2API 面板可访问
- [ ] 已设置 `GPTFREE_ALLOW_REAL_REGISTRATION=1`
