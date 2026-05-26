# Class Diagram

## 核心类型

当前项目只有两个显式类，且都叫 `CDP`：分别定义在 `batch_register_v2.py` 与 `gptfree_cpa_existing_account.py`。其他“类型”主要是函数返回的 dict 结构：Cloud Mail config、CPA OAuth payload、注册结果、监控 state。

```mermaid
classDiagram
    class BatchCDP {
        +ws
        +mid
        +send(method, params, timeout)
        +ev(expr, timeout)
        +url()
        +text(max_len)
        +fill_input(selector, text)
        +focus_and_type(selector, text)
        +click_submit_exact(values)
        +click_submit()
        +click_oauth_consent(rounds)
        +inject_fingerprint()
    }
    class ExistingAccountCDP {
        +ws
        +mid
        +send(method, params, timeout)
        +ev(expr, timeout)
        +url()
        +title()
        +text(n)
        +snapshot()
        +screenshot(path)
        +fill_visible_input(selector, value)
        +click_submit_exact(values)
    }
    class CloudMailConfig {
        +base_url
        +domain
        +admin_email
        +admin_password
    }
    class OAuthPayload {
        +url
        +state
        +raw
    }
    class RegistrationResult {
        +phone
        +password
        +act_id
    }
    class MonitorState {
        +proxy_idx
        +accounts_on_current_proxy
        +total_success
        +total_failed
        +total_wasted_numbers
    }

    BatchCDP --> RegistrationResult : register_account returns
    ExistingAccountCDP --> OAuthPayload : run_oauth consumes
    CloudMailConfig --> ExistingAccountCDP : OTP email flow
    CloudMailConfig --> BatchCDP : email OTP helper
    MonitorState --> RegistrationResult : batch output accounting
```

## Notes

- Mermaid 中的 `BatchCDP` 对应源码 `batch_register_v2.CDP`；`ExistingAccountCDP` 对应源码 `gptfree_cpa_existing_account.CDP`。
- `CloudMailConfig` 不是 Python class，而是 `cloud_mail_local.get_cloud_mail_config()` 返回的 dict。
- `OAuthPayload` 不是 Python class，而是 `gptfree_cpa_existing_account.generate_cpa_oauth()` 返回的 dict。
- `RegistrationResult` 不是 Python class，而是 `batch_register_v2.register_account()` 成功返回的 dict。
- `MonitorState` 不是 Python class，而是 `auto_batch_monitor.load_state()` / `save_state()` 读写的 JSON dict。
