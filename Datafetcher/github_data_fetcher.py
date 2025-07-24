import requests
import pandas as pd
from datetime import datetime, timedelta
import time
import json
import os
from dotenv import load_dotenv # 導入 load_dotenv
from sqlalchemy import create_engine, Column, String, Text, DateTime, JSON
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import JSONB # 使用 JSONB 可以更高效存儲JSON數據

# 載入 .env 檔案中的環境變數
load_dotenv()

# 從環境變數中取得資料庫URL
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set. Please create a .env file with DATABASE_URL.")

# SQLAlchemy 設定
Base = declarative_base()

class GithubCommitCache(Base):
    __tablename__ = 'github_commit_cache'
    id = Column(String, primary_key=True) # owner/repo
    repo_data = Column(JSONB, nullable=False) # 存放該 repo 的所有 commit cache

    def __repr__(self):
        return f"<GithubCommitCache(id='{self.id}')>"

# 初始化資料庫引擎和會話
engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine) # 建立資料表 (如果不存在)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# 快取函數
def _load_cache():
    """從 PostgreSQL 資料庫載入快取資料"""
    db = SessionLocal()
    try:
        # 查詢所有快取資料
        cached_repos = db.query(GithubCommitCache).all()
        cache_data = {}
        for repo_entry in cached_repos:
            cache_data[repo_entry.id] = repo_entry.repo_data
        return cache_data
    except Exception as e:
        print(f"Error loading cache from database: {e}")
        return {}
    finally:
        db.close()

def _save_cache(data):
    """將快取資料儲存到 PostgreSQL 資料庫"""
    db = SessionLocal()
    try:
        for repo_key, repo_data in data.items():
            # 檢查是否存在該 repo 的快取
            repo_entry = db.query(GithubCommitCache).filter(GithubCommitCache.id == repo_key).first()
            if repo_entry:
                # 更新現有快取
                repo_entry.repo_data = repo_data
            else:
                # 建立新快取
                new_entry = GithubCommitCache(id=repo_key, repo_data=repo_data)
                db.add(new_entry)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error saving cache to database: {e}")
    finally:
        db.close()

# 取得github commit數量
def get_github_commits(owner, repo, start_date, end_date, headers):
    print(f"\n--- Starting to fetch GitHub Commit data for {owner}/{repo} ---")

    cache = _load_cache()
    repo_key = f"{owner}/{repo}"
    if repo_key not in cache:
        cache[repo_key] = {} # Initialize cache for this repo

    repo_cache = cache[repo_key]

    requested_dates = set()
    current_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    while current_date <= end_date.replace(hour=0, minute=0, second=0, microsecond=0):
        requested_dates.add(current_date.strftime('%Y-%m-%d'))
        current_date += timedelta(days=1)

    available_dates = set(repo_cache.keys())

    missing_dates_str = sorted(list(requested_dates - available_dates))

    all_commits_for_range = []

    # Fetch missing data
    if missing_dates_str:
        
        # Group missing dates into contiguous blocks for API calls
        contiguous_blocks = []
        if missing_dates_str:
            current_block_start = datetime.strptime(missing_dates_str[0], '%Y-%m-%d')
            current_block_end = current_block_start
            for i in range(1, len(missing_dates_str)):
                date = datetime.strptime(missing_dates_str[i], '%Y-%m-%d')
                if date == current_block_end + timedelta(days=1):
                    current_block_end = date
                else:
                    contiguous_blocks.append((current_block_start, current_block_end))
                    current_block_start = date
                    current_block_end = date
            contiguous_blocks.append((current_block_start, current_block_end))

        for block_start, block_end in contiguous_blocks:
            
            # Expand search range slightly for API to ensure all commits are caught
            api_start_date = (block_start - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            api_end_date = (block_end + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999)

            since_date_str = api_start_date.isoformat(timespec='seconds') + 'Z'
            until_date_str = api_end_date.isoformat(timespec='seconds') + 'Z'

            page = 1
            per_page = 100
            
            try:
                while True:
                    url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page={per_page}&page={page}&since={since_date_str}&until={until_date_str}"
                    print(f"DEBUG(GitHub API): Request URL: {url}")
                    response = requests.get(url, headers=headers)
                    response.raise_for_status()

                    commits = response.json()
                    print(f"DEBUG(GitHub API): Received {len(commits)} commits for page {page}.")

                    if not commits:
                        print(f"DEBUG(GitHub API): No more commits found for page {page}, breaking loop.")
                        # If no commits are returned for a block, ensure all dates in that block are marked as checked
                        temp_date = block_start.replace(hour=0, minute=0, second=0, microsecond=0)
                        while temp_date <= block_end.replace(hour=0, minute=0, second=0, microsecond=0):
                            day_str = temp_date.strftime('%Y-%m-%d')
                            if day_str not in repo_cache: # Only add if not already present (e.g., from a previous page)
                                repo_cache[day_str] = [] # Mark as checked with no commits
                            temp_date += timedelta(days=1)
                        break

                    for commit in commits:
                        commit_date_str = commit['commit']['author']['date']
                        commit_date_obj = datetime.strptime(commit_date_str, '%Y-%m-%dT%H:%M:%SZ')
                        commit_day_str = commit_date_obj.strftime('%Y-%m-%d')
                        
                        # Only store commits within the requested block's date range
                        if block_start.replace(hour=0, minute=0, second=0, microsecond=0) <= commit_date_obj.replace(hour=0, minute=0, second=0, microsecond=0) <= block_end.replace(hour=0, minute=0, second=0, microsecond=0):
                            if commit_day_str not in repo_cache:
                                repo_cache[commit_day_str] = []
                            # Store the raw commit data or a simplified version
                            repo_cache[commit_day_str].append({
                                'date': commit_date_str, # Store as string for JSON
                                'message': commit['commit']['message']
                            })

                    if len(commits) < per_page:
                        # After fetching all pages for a block, ensure all dates in that block are marked as checked
                        temp_date = block_start.replace(hour=0, minute=0, second=0, microsecond=0)
                        while temp_date <= block_end.replace(hour=0, minute=0, second=0, microsecond=0):
                            day_str = temp_date.strftime('%Y-%m-%d')
                            if day_str not in repo_cache: # Only add if not already present (e.g., if no commits were found for this specific day)
                                repo_cache[day_str] = [] # Mark as checked with no commits
                            temp_date += timedelta(days=1)
                        break

                    page += 1
                    time.sleep(0.1) # Be kind to the API

            except requests.exceptions.HTTPError as e:
                print(f"Error: HTTP error occurred while fetching GitHub Commits: {e} (Status code: {response.status_code if 'response' in locals() else 'N/A'})")
                if 'response' in locals() and response.status_code == 404:
                    print("Please check if GitHub Owner and Repository names are correct.")
                elif 'response' in locals() and response.status_code == 403:
                    print(f"GitHub API rate limit might have been reached (Status code: {response.status_code}). Consider setting GITHUB_TOKEN.")
                # For now, return empty DataFrame on error for missing data
                return pd.DataFrame(columns=['date', 'message'])
            except requests.exceptions.RequestException as e:
                print(f"Error: Failed to connect to GitHub API: {e}")
                return pd.DataFrame(columns=['date', 'message'])
            except Exception as e:
                print(f"Error: An unknown error occurred while fetching GitHub Commits: {e}")
                return pd.DataFrame(columns=['date', 'message'])
    else:
        print("DEBUG(GitHub API): All requested dates are already in cache.")

    # Consolidate all commits for the requested range from cache
    current_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    while current_date <= end_date.replace(hour=0, minute=0, second=0, microsecond=0):
        day_str = current_date.strftime('%Y-%m-%d')
        if day_str in repo_cache:
            for commit_data in repo_cache[day_str]:
                # Convert date string back to datetime object for DataFrame
                commit_data_copy = commit_data.copy()
                commit_data_copy['date'] = datetime.strptime(commit_data_copy['date'], '%Y-%m-%dT%H:%M:%SZ')
                all_commits_for_range.append(commit_data_copy)
        current_date += timedelta(days=1)

    if not all_commits_for_range:
        print(f"Warning: No Commit data found for {owner}/{repo} within the specified date range ({start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}).")
        df = pd.DataFrame(columns=['date', 'message'])
    else:
        df = pd.DataFrame(all_commits_for_range)
        df['date'] = pd.to_datetime(df['date']).dt.floor('D') # Ensure date is floored to day
        # Filter to ensure strict adherence to requested start_date and end_date
        df = df[(df['date'] >= start_date.replace(hour=0, minute=0, second=0, microsecond=0)) &
                (df['date'] <= end_date.replace(hour=0, minute=0, second=0, microsecond=0))]
        print(f"Successfully consolidated {len(df)} GitHub Commit data points for the requested range.")

    _save_cache(cache) # Save the updated cache

    return df