# LuckySeven 後端服務

此目錄包含 LuckySeven 專案的後端服務。它負責處理數據獲取、策略管理、策略執行和回測等核心功能。

## 主要功能

*   **數據獲取**：從幣安 (Binance) 獲取加密貨幣市場數據（K 線數據、交易對），並從 GitHub 獲取專案提交 (commit) 數據。
*   **策略管理**：允許用戶保存、檢索、更新和刪除交易策略。
*   **策略執行**：支援實時運行交易策略，並監控其狀態、交易日誌和權益曲線。實時策略會在獨立的進程中運行，以避免阻塞主應用程式。
*   **回測**：提供強大的回測功能，讓用戶能夠在歷史數據上測試其交易策略的表現，並生成詳細的績效報告和圖表。
*   **數據持久化**：使用 SQLAlchemy 將策略配置、運行狀態、交易日誌、權益曲線和 GitHub 提交緩存數據持久化到 PostgreSQL 數據庫中。

## 技術棧

*   **Web 框架**：FastAPI
*   **ASGI 服務器**：Uvicorn
*   **進程管理**：Python `multiprocessing` 模組
*   **數據庫**：PostgreSQL (通過 SQLAlchemy ORM)
*   **數據處理**：Pandas, NumPy
*   **數據獲取**：Requests (用於 API 請求), Python-Binance
*   **環境管理**：python-dotenv

## 目錄結構

*   `app.py`：FastAPI 應用程式的主入口點，整合了各個路由模組。
*   `config.py`：應用程式的通用配置，包括 GitHub 相關設定和預定義的加密貨幣列表。
*   `database.py`：定義了所有數據庫模型 (SavedStrategy, RunningStrategy, TradeLog, EquityCurve, GithubCommitCache) 和數據庫連接設置。
*   `routers/`：定義了 API 的路由，將不同的功能模組化。
    *   `strategy_router.py`：處理策略相關的 API 端點，如保存、啟動、停止和查詢策略狀態。
    *   `data_router.py`：處理數據相關的 API 端點，如獲取加密貨幣價格和交易對。
    *   `misc_router.py`：處理其他雜項 API 端點，如獲取策略列表和策略代碼。
*   `Datafetcher/`：包含用於從外部來源（如幣安和 GitHub）獲取數據的模組。
    *   `binance_data_fetcher.py`：負責從幣安 API 獲取 K 線數據和交易對。
    *   `github_data_fetcher.py`：負責從 GitHub API 獲取專案提交數據。
*   `Strategy/`：包含各種交易策略的實現，例如 `sma.py` (簡單移動平均), `macd.py` (移動平均收斂/發散), `rsi.py` (相對強弱指數), `commit_sma.py` (結合 GitHub 提交數據的 SMA 策略), `smartmoney.py`。
*   `Backtest/`：包含回測邏輯。
    *   `backtest.py`：實現了回測引擎，用於模擬交易並計算績效指標。

## API 端點

`app.py` 是核心 FastAPI 應用程式，提供以下 RESTful API 端點：

### 策略管理

*   **`POST /strategies`**
    *   **描述**：將新的交易策略保存到數據庫中。
    *   **請求主體**：包含 `name`、`code`、`symbol`、`currency`、`interval`、`initial_capital`、`commission_rate`、`slippage`、`risk_free_rate`、`github_owner`（可選）、`github_repo`（可選）的 JSON 對象。
    *   **響應**：`{"message": "Strategy saved successfully!", "strategy_id": new_strategy.id}` 或錯誤詳細信息。

*   **`GET /strategies`**
    *   **描述**：檢索所有已保存交易策略的列表。
    *   **響應**：已保存策略對象的列表。

*   **`DELETE /strategies/{strategy_id}`**
    *   **描述**：根據 ID 刪除已保存的交易策略。如果策略當前正在運行，它將被停止，並且其相關的日誌/曲線將首先被刪除。
    *   **參數**：`strategy_id`（路徑參數，整數）。
    *   **響應**：`{"message": "Strategy deleted successfully!"}` 或錯誤詳細信息。

*   **`POST /strategies/{strategy_id}/start`**
    *   **描述**：在獨立的 Python 進程中啟動已保存的交易策略。這允許策略在後台持續運行。
    *   **參數**：`strategy_id`（路徑參數，整數）。
    *   **響應**：`{"message": "Strategy started successfully!", "running_strategy_id": running_strategy.id, "pid": process.pid}` 或錯誤詳細信息。

*   **`POST /strategies/{strategy_id}/stop`**
    *   **描述**：停止正在運行的交易策略，方法是將其狀態設置為 "stopped"，並從數據庫中刪除其運行記錄、交易日誌和權益曲線。相關進程會被終止。
    *   **參數**：`strategy_id`（路徑參數，整數）。
    *   **響應**：`{"message": "Strategy stopped and removed successfully!"}` 或 `{"message": "Strategy is already stopped or was not running."}` 或錯誤詳細信息。

*   **`GET /strategies/{strategy_id}/status`**
    *   **描述**：檢索運行中策略的當前狀態。
    *   **參數**：`strategy_id`（路徑參數，整數）。
    *   **響應**：`{"status": "running"|"stopped"|"error", "pid": pid, "started_at": datetime, "last_updated_at": datetime}`。

*   **`GET /strategies/{strategy_id}/trade_logs`**
    *   **描述**：檢索特定運行策略的交易日誌。
    *   **參數**：`strategy_id`（路徑參數，整數）。
    *   **響應**：交易日誌對象的列表。

*   **`GET /strategies/{strategy_id}/equity_curve`**
    *   **描述**：檢索特定運行策略的權益曲線數據。
    *   **參數**：`strategy_id`（路徑參數，整數）。
    *   **響應**：權益曲線數據點的列表。

### 數據獲取

*   **`GET /crypto_prices`**
    *   **描述**：從幣安獲取歷史加密貨幣 K 線數據。
    *   **查詢參數**：`symbol`（例如：“BTC”）、`currency`（例如：“USDT”）、`interval`（例如：“1h”）、`start_date`（YYYY-MM-DD）、`end_date`（YYYY-MM-DD）。
    *   **響應**：字典列表，每個字典代表一個 K 線蠟燭圖。

*   **`GET /trading_pairs`**
    *   **描述**：根據交易量從幣安檢索前 N 個交易對（例如：BTCUSDT、ETHUSDT）的列表。
    *   **查詢參數**：`top_n`（可選，整數，默認值：1000）。
    *   **響應**：`{"pairs": ["BTC", "ETH", ...]}`。

*   **`GET /strategy_list`**
    *   **描述**：列出 `Strategy/` 目錄中所有可用的策略文件（Python 腳本）。
    *   **響應**：`{"strategies": ["sma", "macd", ...]}`。

*   **`GET /strategy_code/{strategy_name}`**
    *   **描述**：檢索特定策略文件的 Python 代碼內容。
    *   **參數**：`strategy_name`（路徑參數，字符串）。
    *   **響應**：`{"code": "print('strategy code here')"}` 或錯誤詳細信息。

### 回測

*   **`POST /run_backtest`**
    *   **描述**：針對歷史數據運行給定策略代碼的回測。回測會同步執行並返回結果。
    *   **請求主體**：包含 `symbol`、`currency`、`interval`、`start_date`、`end_date`、`strategy_code`、`strategy_name`、`initial_capital`（可選）、`commission_rate`（可選）、`slippage`（可選）、`risk_free_rate`（可選）、`github_owner`（可選）、`github_repo`（可選）的 JSON 對象。
    *   **響應**：包含回測指標和圖表數據（權益曲線、交易信號、價格序列）的 JSON 對象。

## 環境變量配置

在運行後端服務之前，您需要配置以下環境變量。請在 `LuckySeven_backend/` 目錄下創建一個 `.env` 文件，並填寫以下內容：

```dotenv
DATABASE_URL="postgresql://user:password@host:port/database_name"
GITHUB_TOKEN="your_github_personal_access_token" # 可選，用於獲取 GitHub 提交數據，建議設置以避免 API 速率限制
```

*   `DATABASE_URL`：您的 PostgreSQL 數據庫連接字符串。
*   `GITHUB_TOKEN`：您的 GitHub 個人訪問令牌。如果您計劃使用 `commit_sma` 策略或頻繁獲取 GitHub 數據，強烈建議設置此令牌以避免 GitHub API 的速率限制。

## 如何運行後端

1.  **安裝依賴**：
    ```bash
    pip install -r requirements.txt
    ```
2.  **配置環境變量**：
    在 `LuckySeven_backend/` 目錄下創建 `.env` 文件並填寫上述環境變量。
3.  **啟動 PostgreSQL 服務**：
    確保您的 PostgreSQL 數據庫正在運行。
4.  **運行數據庫遷移 (如果需要)**：
    首次運行時，`database.py` 中的 `Base.metadata.create_all(engine)` 會自動創建數據表。
5.  **啟動 FastAPI 應用**：
    在 `LuckySeven_backend/` 目錄下打開終端，運行：
    ```bash
    uvicorn app:app --host 0.0.0.0 --port 8000 --reload
    ```
    這將啟動 FastAPI 服務器，默認在 `http://0.0.0.0:8000` 上運行。`--reload` 選項會在代碼更改時自動重啟服務器（僅適用於開發環境）。

現在，後端服務已準備就緒，可以接收來自前端的請求。