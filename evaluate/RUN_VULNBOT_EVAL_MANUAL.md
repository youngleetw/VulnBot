# run_vulnbot_eval.py 使用手冊

本手冊說明如何使用 `evaluate/run_vulnbot_eval.py` 自動化執行 VulnBot 評估流程，包含：
- 環境重置（`run_eval.sh`）
- `vulnbot` 互動式輸入自動化（PTY 模擬人類輸入）
- 即時終端輸出 + 完整 log 落檔
- ANSI/control code 清洗

## 1. 腳本功能總覽

腳本會依序執行：
1. 呼叫 `/home/younglee/auto-pen-bench/run_eval.sh <level> <category> <vm_id>` 重置環境。
2. 執行 `uv run python cli.py vulnbot -m <max_interactions>`。
3. 互動式自動輸入：
   - `Do you want to continue from a previous session?` -> 自動輸入 `n`
   - `Please describe the penetration testing task.` -> 自動輸入 `games.json` 對應 task
   - `Please enter the name of the current session...` -> 自動送出 Enter（使用預設時間戳）
4. 將過程同步輸出到終端，並寫入 `evaluate/*.log`。

## 2. 指令格式

```bash
uv run python evaluate/run_vulnbot_eval.py [OPTIONS]
```

## 3. 參數與選項（完整）

`--level`（必要）
- 類型：`str`
- 說明：評估等級，例如 `real-world`、`in-vitro`

`--category`（必要）
- 類型：`str`
- 說明：類別，例如 `cve`、`web_security`、`access_control` 等

`--vm-id`（單機模式）
- 類型：`int`
- 說明：指定單一 VM，例如 `1`
- 注意：與 `--all-vms` 互斥，只能擇一

`--all-vms`（全機模式）
- 類型：旗標（bool）
- 說明：執行該 `level/category` 下所有 VM
- 注意：與 `--vm-id` 互斥，只能擇一

`--run-index`
- 類型：`int`
- 預設：`1`
- 說明：log 起始編號（檔名尾碼）
- 例：`--run-index 3 --run-count 2` 會生成 `_3.log`、`_4.log`

`--run-count`
- 類型：`int`
- 預設：`1`
- 說明：每台 VM 重複執行次數
- 限制：必須 `>= 1`

`--max-interactions`, `-m`
- 類型：`int`
- 預設：`6`
- 說明：傳給 `vulnbot` 的 `-m` 參數

`--repo-root`
- 類型：`str`（路徑）
- 預設：腳本自動推導之 VulnBot 根目錄
- 說明：VulnBot 專案根目錄

`--bench-reset-script`
- 類型：`str`（路徑）
- 預設：`/home/younglee/auto-pen-bench/run_eval.sh`
- 說明：重置環境腳本路徑

`--games-file`
- 類型：`str`（相對或絕對路徑）
- 預設：`games.json`
- 說明：任務來源檔案，依 `target=<level>_<category>_vm<id>` 取出 `task`

`-h`, `--help`
- 類型：旗標
- 說明：顯示說明

## 4. 參數組合規則

有效組合：
- 單機：`--vm-id <id>`
- 全機：`--all-vms`

無效組合：
- 同時給 `--vm-id` 與 `--all-vms`（互斥）
- 兩者都不給（需至少一種執行範圍）

## 5. Log 命名與輸出

Log 目錄：
- `evaluate/`

命名格式：
- `<level>_VM-<vm_id>_<run_index>.log`
- 例如：`real-world_VM-1_1.log`

輸出特性：
- 即時同步到終端（可看到腳本正在跑）
- 同步寫入 log
- log 內容已清洗 ANSI/control codes，較易閱讀
- 腳本自動記錄 `[AUTO]` 互動事件：
  - `[AUTO] continue_from_previous=n`
  - `[AUTO] task_input=...`
  - `[AUTO] session_name=<ENTER>`

## 6. 執行範例

### 範例 A：單一機器，跑 1 次

```bash
uv run python evaluate/run_vulnbot_eval.py \
  --level real-world \
  --category cve \
  --vm-id 1 \
  --run-count 1 \
  --run-index 1 \
  -m 6
```

輸出 log：
- `evaluate/real-world_VM-1_1.log`

### 範例 B：單一機器，連跑 3 次

```bash
uv run python evaluate/run_vulnbot_eval.py \
  --level real-world \
  --category cve \
  --vm-id 1 \
  --run-count 3 \
  --run-index 1 \
  -m 6
```

輸出 log：
- `evaluate/real-world_VM-1_1.log`
- `evaluate/real-world_VM-1_2.log`
- `evaluate/real-world_VM-1_3.log`

### 範例 C：整個類別全部 VM，各跑 1 次

```bash
uv run python evaluate/run_vulnbot_eval.py \
  --level real-world \
  --category cve \
  --all-vms \
  --run-count 1 \
  --run-index 1 \
  -m 6
```

輸出 log（依 `games.json` 實際 VM 列表）：
- `evaluate/real-world_VM-0_1.log`
- `evaluate/real-world_VM-1_1.log`
- ...

### 範例 D：整個類別全部 VM，各跑 2 次，從編號 5 開始

```bash
uv run python evaluate/run_vulnbot_eval.py \
  --level real-world \
  --category cve \
  --all-vms \
  --run-count 2 \
  --run-index 5 \
  -m 6
```

輸出 log（每台會有 `_5.log` 與 `_6.log`）：
- `evaluate/real-world_VM-0_5.log`
- `evaluate/real-world_VM-0_6.log`
- `evaluate/real-world_VM-1_5.log`
- `evaluate/real-world_VM-1_6.log`
- ...

### 範例 E：自訂路徑（repo、reset script、games 檔）

```bash
uv run python evaluate/run_vulnbot_eval.py \
  --level real-world \
  --category cve \
  --vm-id 1 \
  --repo-root /home/younglee/VulnBot \
  --bench-reset-script /home/younglee/auto-pen-bench/run_eval.sh \
  --games-file /home/younglee/VulnBot/games.json
```

## 7. 常見錯誤與排查

`ValueError: Use either --vm-id or --all-vms, not both`
- 原因：同時給了互斥選項
- 解法：只保留一個

`ValueError: Please set --vm-id for single machine run, or use --all-vms`
- 原因：沒有指定執行範圍
- 解法：補 `--vm-id` 或 `--all-vms`

`ValueError: --run-count must be >= 1`
- 原因：`--run-count` 小於 1
- 解法：改成 `1` 以上

`FileNotFoundError: games.json not found`
- 原因：`--games-file` 或 `--repo-root` 設定錯誤
- 解法：確認路徑存在

`RuntimeError: Reset script failed with exit code ...`
- 原因：`run_eval.sh` 執行失敗（docker/compose/參數）
- 解法：先手動執行 reset 指令確認環境

`RuntimeError: VulnBot exited abnormally with status ...`
- 原因：`vulnbot` 過程錯誤或被中斷
- 解法：查看對應 `evaluate/*.log` 的最後 100 行

## 8. 建議操作流程

1. 先跑單機 1 次確認互動流程、DB、LLM 設定無誤。
2. 再提高 `--run-count` 做穩定性測試。
3. 最後使用 `--all-vms` 跑完整類別。
4. 每次執行後檢查 log 中 `[AUTO]` 三行與 exit status。

