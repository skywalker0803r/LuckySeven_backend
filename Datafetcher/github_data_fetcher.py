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

# 取得github commit數量
def get_github_commits(owner, repo, start_date, end_date, headers):
    print(f"\n--- Starting to fetch GitHub Commit data for {owner}/{repo} ---")

    all_commits_for_range = []
            
    # Expand search range slightly for API to ensure all commits are caught
    api_start_date = (start_date - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    api_end_date = (end_date + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999)

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
                break

            for commit in commits:
                commit_date_str = commit['commit']['author']['date']
                commit_date_obj = datetime.strptime(commit_date_str, '%Y-%m-%dT%H:%M:%SZ')
                commit_day_str = commit_date_obj.strftime('%Y-%m-%d')
                
                # Only store commits within the requested block's date range
                if start_date.replace(hour=0, minute=0, second=0, microsecond=0) <= commit_date_obj.replace(hour=0, minute=0, second=0, microsecond=0) <= end_date.replace(hour=0, minute=0, second=0, microsecond=0):
                    all_commits_for_range.append({
                        'date': commit_date_str, # Store as string for JSON
                        'message': commit['commit']['message']
                    })

            if len(commits) < per_page:
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
    # else: # Removed
    #     print("DEBUG(GitHub API): All requested dates are already in cache.") # Removed

    # Consolidate all commits for the requested range from cache # Removed
    # current_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0) # Removed
    # while current_date <= end_date.replace(hour=0, minute=0, second=0, microsecond=0): # Removed
    #     day_str = current_date.strftime('%Y-%m-%d') # Removed
    #     if day_str in repo_cache: # Removed
    #         for commit_data in repo_cache[day_str]: # Removed
    #             # Convert date string back to datetime object for DataFrame # Removed
    #             commit_data_copy = commit_data.copy() # Removed
    #             commit_data_copy['date'] = datetime.strptime(commit_data_copy['date'], '%Y-%m-%dT%H:%M:%SZ') # Removed
    #             all_commits_for_range.append(commit_data_copy) # Removed
    #     current_date += timedelta(days=1) # Removed

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

    # _save_cache(cache) # Save the updated cache # Removed

    return df
