# Hermes Cron 自动注册任务

Job ID: `68def6c6cfab`  
Schedule: `*/5 * * * *`（每 5 分钟）  
Deliver: telegram, feishu  
Workdir: 本项目根目录

## 流程

1. **清理残留 Chrome**
   ```bash
   ps aux | grep 'chrome.*remote-debugging' | grep -v grep | awk '{print $2}' | xargs -r kill -9 2>/dev/null
   ```

2. **运行主脚本**
   ```bash
   set -a && source .env && set +a
   export GPTFREE_ALLOW_REAL_REGISTRATION=1
   python3 -u batch_register_v2.py 1
   ```

3. **判断结果**
   - 含 `✓ DONE!` → 成功，读 JSONL 最后一行，查余额，发通知
   - 含 `NO_NUMBERS` 或 `Failed to buy number` → 静默
   - 含 `OAuth failed, saved phone+password` → 进入兜底重试（步骤 5）
   - 脚本崩溃 → 找 act_id 取消号码，静默

4. **清理 Chrome**（同步骤 1）

5. **兜底重试（不买号）**

   如果注册成功但 OAuth 失败，读 JSONL 最后一条拿 phone 和 password，调 helper 重试：
   ```bash
   python3 -u gptfree_cpa_existing_account.py \
     --phone '{phone}' --password '{password}' \
     --email-prefix gptcpa{random8} --start-chrome --close-chrome --otp-timeout 120
   ```
   - helper 成功（输出含 "callback" 或 "ok"）→ 更新 JSONL，发成功通知
   - helper 失败 → 静默，下次 cron 自动再试
   - **绝不重新注册或买新号**，只重试 OAuth

6. **余额查询**（成功时）

   请求 `hero-sms.com` 的 `handler_api.php?action=getBalance`，返回格式 `ACCESS_BALANCE:数字`。

## 通知格式

```
✅ GPTFree +1

国家: {country}
号码: ****{last4}
邮箱: {cpa_email}
余额: ${balance}
```

- 兜底重试成功末尾加：`备注: 兜底重试成功`
- 余额查询失败：`余额: 查询失败`
- 余额低于 $0.50：`⚠️ 余额不足 $0.50`

## 规则

- 成功才通知，失败一律静默
- 所有 key 从 `.env` 读取，不硬编码
- Chrome 必须清理
- 兜底重试不买号
