# Sequence Diagrams

## Workflow: 批量注册一个账号并调用 CPA helper

`batch_register_v2.main()` 对每个目标账号重启 Chrome、执行 `register_account()`，注册成功后以子进程调用 `gptfree_cpa_existing_account.py`。

```mermaid
sequenceDiagram
    participant CLI as batch_register_v2.main
    participant Chrome as restart_chrome_with_fingerprint
    participant Register as register_account
    participant Hero as HeroSMS API
    participant CDP as batch_register_v2.CDP
    participant ChatGPT as chatgpt.com/auth.openai.com
    participant Helper as gptfree_cpa_existing_account.py
    participant Accounts as accounts JSONL

    CLI->>Chrome: restart_chrome_with_fingerprint()
    Chrome-->>CLI: CDP ready / failed
    CLI->>Register: register_account()
    Register->>Hero: buy_number()
    Hero-->>Register: act_id, phone
    Register->>CDP: connect page websocket
    CDP->>ChatGPT: Page.navigate login/signup
    Register->>CDP: fill phone, password, profile
    Register->>Hero: get_sms(act_id)
    Hero-->>Register: sms_code
    Register->>CDP: submit sms_code
    Register->>Hero: finish_number(act_id)
    Register-->>CLI: phone/password/act_id
    CLI->>Helper: subprocess --phone --password --email-prefix
    Helper-->>CLI: returncode + output
    CLI->>Accounts: append JSONL record
```

### Walkthrough

1. **批次循环** — `batch_register_v2.main()` 从 `_args.count` 读取目标数量。
2. **Chrome 刷新** — `restart_chrome_with_fingerprint()` 删除旧 profile 并启动 CDP Chrome。
3. **号码购买** — `register_account()` 调 `buy_number()` 获取 HeroSMS activation。
4. **页面注册** — `CDP` 通过 `Page.navigate`、`Runtime.evaluate`、`Input.dispatchKeyEvent` 操作 ChatGPT/Auth 页面。
5. **短信验证** — `get_sms()` 轮询 HeroSMS `getStatus`，收到码后提交。
6. **Phase 2 导入** — 注册成功后 `main()` 用 `subprocess.run()` 调 `gptfree_cpa_existing_account.py`。
7. **结果记录** — 按 helper returncode/output 判断 `oauth_imported` 并写 JSONL。

## Workflow: 已有账号 CPA/Codex OAuth 导入

`gptfree_cpa_existing_account.run_oauth()` 获取 CPA OAuth state，打开 OpenAI 授权页，处理登录、邮箱验证码和 consent，最后回传 callback。

```mermaid
sequenceDiagram
    participant CLI as gptfree_cpa_existing_account.main
    participant CPA as CPA Management API
    participant CDP as gptfree_cpa_existing_account.CDP
    participant OpenAI as OpenAI Auth/OAuth UI
    participant Mail as cloud_mail_local.py
    participant State as oauth.json

    CLI->>CPA: generate_cpa_oauth()
    CPA-->>CLI: auth_url, state
    CLI->>State: save_oauth_json(oauth)
    CLI->>CDP: create_tab + connect websocket
    CDP->>OpenAI: navigate auth_url
    CDP->>OpenAI: choose account / phone login / password
    CLI->>Mail: create_or_reuse_cloud_mail_address()
    Mail-->>CLI: account_email
    CDP->>OpenAI: submit add-email
    CLI->>Mail: poll_latest_openai_otp()
    Mail-->>CLI: otp
    CDP->>OpenAI: submit otp + consent
    CDP-->>CLI: callback URL
    CLI->>CPA: POST /v0/management/oauth-callback
    CLI->>CPA: GET /v0/management/get-auth-status
```

### Walkthrough

1. **OAuth URL** — `generate_cpa_oauth()` 调 CPA `/v0/management/codex-auth-url`。
2. **state 保存** — `save_oauth_json()` 写入 `DEFAULT_STATE_DIR/oauth.json`。
3. **浏览器会话** — `create_tab()` 创建新 tab，`CDP.send()` 启用 Page/Runtime/Network。
4. **登录路径** — `run_oauth()` 根据页面 URL/text 调 `click_account_card()`、`fill_visible_input()`、`click_submit_exact()`。
5. **邮箱验证码** — add-email 或 email-verification 页面触发 `poll_latest_openai_otp()`。
6. **callback 处理** — `callback_parts()` 解析 code/state，`cpa_request()` POST callback 并查询 status。

## Workflow: Cloud Mail 创建邮箱并拉取验证码

Cloud Mail 基础客户端在 `cloud_mail_local.py` 中；上层 OpenAI OTP 筛选在 `batch_register_v2.py` 和 `gptfree_cpa_existing_account.py` 中各自实现。

```mermaid
sequenceDiagram
    participant Caller as batch/helper caller
    participant Config as get_cloud_mail_config
    participant Token as get_cloud_mail_token
    participant MailAPI as Cloud Mail API
    participant Inbox as get_cloud_mail_messages
    participant Parser as extract_openai_code

    Caller->>Config: get_cloud_mail_config()
    Config-->>Caller: base_url/domain/admin
    Caller->>Token: get_cloud_mail_token(config)
    Token->>MailAPI: POST /api/public/genToken
    MailAPI-->>Token: token/accessToken
    Caller->>MailAPI: create_cloud_mail_address()
    MailAPI-->>Caller: address
    loop until timeout
        Caller->>Inbox: get_cloud_mail_messages(address)
        Inbox->>MailAPI: POST /api/public/emailList
        MailAPI-->>Inbox: message list
        Caller->>Parser: extract_openai_code(message)
        Parser-->>Caller: code or None
    end
```

### Walkthrough

1. **配置读取** — `get_cloud_mail_config()` 合并本地 env 文件和 `CLOUD_MAIL_*` 环境变量。
2. **鉴权** — `get_cloud_mail_token()` 调 `/api/public/genToken`。
3. **创建地址** — `create_cloud_mail_address()` 调 `/api/public/addUser`。
4. **邮件轮询** — `get_cloud_mail_messages()` 调 `/api/public/emailList`。
5. **OpenAI OTP 解析** — 上层 `extract_openai_code()` 先检查 OpenAI/ChatGPT/verification 上下文，再返回 6 位码。

## Workflow: 库存监控触发批量注册

`auto_batch_monitor.main()` 无限循环，按库存、代理和批次结果更新状态。

```mermaid
sequenceDiagram
    participant Monitor as auto_batch_monitor.main
    participant Hero as HeroSMS API
    participant Mihomo as Mihomo API
    participant Batch as batch_register_v2.py subprocess
    participant Log as ~/auto_batch_logs
    participant State as ~/auto_batch_state.json

    Monitor->>State: load_state()
    loop forever
        Monitor->>Hero: check_stock()
        Hero-->>Monitor: country,count,price
        Monitor->>Mihomo: switch_proxy(proxy)
        Mihomo-->>Monitor: selected IP/log
        Monitor->>Batch: run_batch(batch,country)
        Batch-->>Log: streamed stdout
        Batch-->>Monitor: FINAL line / returncode
        Monitor->>Monitor: parse success/failed/wasted
        Monitor->>State: save_state(state)
    end
```

### Walkthrough

1. **状态加载** — `load_state()` 读取代理索引和累计统计。
2. **库存预览** — `check_stock_country()` 通过非购买接口读取 HeroSMS 可用价格档。
3. **代理切换** — `switch_proxy()` 对非 direct 代理调用 Mihomo `GLOBAL`。
4. **批次执行** — `run_batch()` 子进程启动 `batch_register_v2.py` 并实时写日志。
5. **失败控制** — 如果 `wasted > 0`，`main()` 停止循环。
