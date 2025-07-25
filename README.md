# LuckySeven_backend

此目錄包含 LuckySeven 專案的後端服務。它負責：
- **數據獲取：** 從幣安和 GitHub 等來源檢索數據。
- **策略管理：** 實施和管理各種交易策略（例如：SMA、MACD、RSI）。
- **策略執行：** 運行交易策略。
- **回測：** 提供針對歷史數據回測交易策略的功能。
- **配置：** 管理應用程式設定。

主要組件包括：
- `app.py`：主應用程式入口點，公開各種 API 端點。
- `config.py`：應用程式配置。
- `strategy_runner.py`：在單獨的進程中執行交易策略。
- `Datafetcher/`：用於從外部來源獲取數據的模組。
- `Strategy/`：包含不同的交易策略實現。
- `Backtest/`：包含回測邏輯。
- `database.py`：集中式數據庫模型和會話管理。

## `app.py` API 端點

`app.py` 是核心 FastAPI 應用程式，提供以下 RESTful API 端點：

### 策略管理

-   **`POST /strategies`**
    -   **描述：** 將新的交易策略保存到數據庫中。
    -   **請求主體：** 包含 `name`、`code`、`symbol`、`currency`、`interval`、`initial_capital`、`commission_rate`、`slippage`、`risk_free_rate`、`github_owner`（可選）、`github_repo`（可選）的 JSON 對象。
    -   **響應：** `{"message": "Strategy saved successfully!", "strategy_id": new_strategy.id}` 或錯誤詳細信息。

-   **`GET /strategies`**
    -   **描述：** 檢索所有已保存交易策略的列表。
    -   **響應：** 已保存策略對象的列表。

-   **`DELETE /strategies/{strategy_id}`**
    -   **描述：** 根據 ID 刪除已保存的交易策略。如果策略當前正在運行，它將被停止，並且其相關的日誌/曲線將首先被刪除。
    -   **參數：** `strategy_id`（路徑參數，整數）。
    -   **響應：** `{"message": "Strategy deleted successfully!"}` 或錯誤詳細信息。

-   **`POST /strategies/{strategy_id}/start`**
    -   **描述：** 在新的、分離的進程中啟動已保存的交易策略。這允許策略在後台持續運行。
    -   **參數：** `strategy_id`（路徑參數，整數）。
    -   **響應：** `{"message": "Strategy started successfully!", "running_strategy_id": running_strategy.id, "pid": process.pid}` 或錯誤詳細信息。

-   **`POST /strategies/{strategy_id}/stop`**
    -   **描述：** 停止正在運行的交易策略，方法是終止其相關進程並從數據庫中刪除其運行記錄、交易日誌和權益曲線。
    -   **參數：** `strategy_id`（路徑參數，整數）。
    -   **響應：** `{"message": "Strategy stopped and removed successfully!"}` 或 `{"message": "Strategy is already stopped or was not running."}` 或錯誤詳細信息。

-   **`GET /strategies/{strategy_id}/status`**
    -   **描述：** 檢索運行中策略的當前狀態。
    -   **參數：** `strategy_id`（路徑參數，整數）。
    -   **響應：** `{"status": "running"|"stopped"|"error", "pid": pid, "started_at": datetime, "last_updated_at": datetime}`。

-   **`GET /strategies/{strategy_id}/trade_logs`**
    -   **描述：** 檢索特定運行策略的交易日誌。
    -   **參數：** `strategy_id`（路徑參數，整數）。
    -   **響應：** 交易日誌對象的列表。

-   **`GET /strategies/{strategy_id}/equity_curve`**
    -   **描述：** 檢索特定運行策略的權益曲線數據。
    -   **參數：** `strategy_id`（路徑參數，整數）。
    -   **響應：** 權益曲線數據點的列表。

### 數據獲取

-   **`GET /crypto_prices`**
    -   **描述：** 從幣安獲取歷史加密貨幣 K 線數據。
    -   **查詢參數：** `symbol`（例如：“BTC”）、`currency`（例如：“USDT”）、`interval`（例如：“1h”）、`start_date`（YYYY-MM-DD）、`end_date`（YYYY-MM-DD）。
    -   **響應：** 字典列表，每個字典代表一個 K 線蠟燭圖。

-   **`GET /trading_pairs`**
    -   **描述：** 根據交易量從幣安檢索前 N 個交易對（例如：BTCUSDT、ETHUSDT）的列表。
    -   **查詢參數：** `top_n`（可選，整數，默認值：1000）。
    -   **響應：** `{"pairs": ["BTC", "ETH", ...]}`。

-   **`GET /strategy_list`**
    -   **描述：** 列出 `Strategy/` 目錄中所有可用的策略文件（Python 腳本）。
    -   **響應：** `{"strategies": ["sma", "macd", ...]}`。

-   **`GET /strategy_code/{strategy_name}`**
    -   **描述：** 檢索特定策略文件的 Python 代碼內容。
    -   **參數：** `strategy_name`（路徑參數，字符串）。
    -   **響應：** `{"code": "print('strategy code here')"}` 或錯誤詳細信息。

### 回測

-   **`POST /run_backtest`**
    -   **描述：** 針對歷史數據運行給定策略代碼的回測。
    -   **請求主體：** 包含 `symbol`、`currency`、`interval`、`start_date`、`end_date`、`strategy_code`、`strategy_name`、`initial_capital`（可選）、`commission_rate`（可選）、`slippage`（可選）、`risk_free_rate`（可選）、`github_owner`（可選）、`github_repo`（可選）的 JSON 對象。
    -   **響應：** 包含回測指標和圖表數據（權益曲線、交易信號、價格序列）的 JSON 對象。