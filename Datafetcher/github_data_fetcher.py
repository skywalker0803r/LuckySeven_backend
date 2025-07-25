import requests
import pandas as pd
from datetime import datetime, timedelta
import time
import json
import os
from dotenv import load_dotenv # 導入 load_dotenv

# Import database components
from database import SessionLocal # Removed GithubCommitCache

# 載入 .env 檔案中的環境變數
load_dotenv()
