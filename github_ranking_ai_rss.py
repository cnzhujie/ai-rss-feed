import asyncio
from datetime import datetime, timezone, timedelta
from feedgen.feed import FeedGenerator
import aiohttp
import csv
import io
import os
from collections import defaultdict


class GithubRankingAIRSSGenerator:
    def __init__(self):
        self.base_url = "https://github.com/yuxiaopeng/Github-Ranking-AI"
        self.csv_base_url = "https://raw.githubusercontent.com/yuxiaopeng/Github-Ranking-AI/main/Data/github-ranking-{date}.csv"
        self.rss_dir = "rss"
        self.rss_file = os.path.join(self.rss_dir, "github_ranking_ai_rss.xml")
        self.top_n = 10

    def get_csv_url(self, date):
        date_str = date.strftime("%Y-%m-%d")
        return self.csv_base_url.format(date=date_str)

    async def fetch_csv(self, date):
        url = self.get_csv_url(date)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        content = await response.text()
                        print(f"Fetched CSV for {date.strftime('%Y-%m-%d')}")
                        return self.parse_csv(content)
                    else:
                        print(f"Failed to fetch CSV for {date.strftime('%Y-%m-%d')}: {response.status}")
                        return {}
        except Exception as e:
            print(f"Error fetching CSV for {date.strftime('%Y-%m-%d')}: {e}")
            return {}

    def parse_csv(self, content):
        repos_by_item = defaultdict(dict)
        reader = csv.DictReader(io.StringIO(content))
        
        for row in reader:
            repo_url = row.get('repo_url', '')
            if not repo_url:
                continue
            
            rank = int(row.get('rank', 0))
            item = row.get('item', '')
            
            if rank > self.top_n:
                continue
            
            repos_by_item[item][repo_url] = {
                'rank': rank,
                'item': item,
                'repo_name': row.get('repo_name', ''),
                'stars': int(row.get('stars', '0').replace(',', '')),
                'forks': int(row.get('forks', '0').replace(',', '')),
                'language': row.get('language', ''),
                'repo_url': repo_url,
                'username': row.get('username', ''),
                'description': row.get('description', ''),
            }
        
        return repos_by_item

    def compare_and_generate_updates(self, today_data, yesterday_data):
        updates = []
        
        all_items = set(today_data.keys()) | set(yesterday_data.keys())
        
        for item in sorted(all_items):
            today_repos = today_data.get(item, {})
            yesterday_repos = yesterday_data.get(item, {})
            
            print(f"\n  [{item}] Comparing top {self.top_n}...")
            
            for repo_url, today_repo in today_repos.items():
                yesterday_repo = yesterday_repos.get(repo_url)
                
                if yesterday_repo is None:
                    change_info = f"🆕 NEW ENTRY - Ranked #{today_repo['rank']} in {item}"
                    updates.append({
                        'repo': today_repo,
                        'change_info': change_info,
                        'is_new': True,
                        'rank_change': 0,
                        'item': item
                    })
                    print(f"    NEW: {today_repo['repo_name']} entered at #{today_repo['rank']}")
                else:
                    changes = []
                    has_change = False
                    
                    prev_rank = yesterday_repo.get('rank', 0)
                    rank_change = prev_rank - today_repo['rank']
                    
                    if rank_change > 0:
                        changes.append(f"📈 Rank: #{prev_rank} → #{today_repo['rank']} (↑{rank_change})")
                        has_change = True
                    elif rank_change < 0:
                        changes.append(f"📉 Rank: #{prev_rank} → #{today_repo['rank']} (↓{abs(rank_change)})")
                        has_change = True
                    
                    prev_stars = yesterday_repo.get('stars', 0)
                    stars_change = today_repo['stars'] - prev_stars
                    
                    if abs(stars_change) > 1000:
                        if stars_change > 0:
                            changes.append(f"⭐ Stars: {prev_stars:,} → {today_repo['stars']:,} (+{stars_change:,})")
                            has_change = True
                        elif stars_change < 0:
                            changes.append(f"⭐ Stars: {prev_stars:,} → {today_repo['stars']:,} ({stars_change:,})")
                            has_change = True
                    
                    if has_change and changes:
                        change_info = " | ".join(changes)
                        updates.append({
                            'repo': today_repo,
                            'change_info': change_info,
                            'is_new': False,
                            'rank_change': rank_change,
                            'item': item
                        })
        
        return updates

    def create_feed(self):
        feed = FeedGenerator()
        feed.title('GitHub AI Ranking Changes (Top 10)')
        feed.link(href=self.base_url, rel='alternate')
        feed.description('Track changes in GitHub AI repository rankings (Top 10 per category)')
        feed.language('en')
        feed.link(href='https://raw.githubusercontent.com/cnzhujie/ai-rss-feed/main/rss/github_ranking_ai_rss.xml', rel='self')
        
        return feed

    def generate_rss(self, updates):
        feed = self.create_feed()
        
        sorted_updates = sorted(updates, key=lambda x: (x['item'], not x['is_new'], -x['rank_change'], x['repo']['rank']))
        
        for update in sorted_updates:
            repo = update['repo']
            change_info = update['change_info']
            
            description = f"{change_info}\n\n{repo['description']}"
            if repo.get('language'):
                description += f"\n\nLanguage: {repo['language']}"
            description += f"\n\nCategory: {repo['item']}"
            description += f"\nStars: {repo['stars']:,} | Forks: {repo['forks']:,}"
            
            entry = feed.add_entry()
            entry.title(f"[{repo['item']}] {repo['repo_name']}")
            entry.link(href=repo['repo_url'])
            entry.pubDate(datetime.now(timezone.utc))
            entry.description(description)
            entry.guid(repo['repo_url'], permalink=True)
        
        rss_content = feed.rss_str(pretty=True)
        return rss_content


async def main():
    generator = GithubRankingAIRSSGenerator()
    
    today = datetime.now(timezone.utc)
    yesterday = today - timedelta(days=1)
    
    print(f"Fetching today's CSV ({today.strftime('%Y-%m-%d')})...")
    today_data = await generator.fetch_csv(today)
    
    print(f"\nFetching yesterday's CSV ({yesterday.strftime('%Y-%m-%d')})...")
    yesterday_data = await generator.fetch_csv(yesterday)
    
    today_count = sum(len(repos) for repos in today_data.values())
    yesterday_count = sum(len(repos) for repos in yesterday_data.values())
    
    print(f"\nToday: {today_count} repos in {len(today_data)} categories (top {generator.top_n})")
    print(f"Yesterday: {yesterday_count} repos in {len(yesterday_data)} categories (top {generator.top_n})")
    
    if not today_data:
        print("\nNo data fetched, skipping RSS generation")
        return
    
    print("\nComparing data by category...")
    updates = generator.compare_and_generate_updates(today_data, yesterday_data)
    
    print(f"\nFound {len(updates)} updates")
    
    if updates:
        print("\nGenerating RSS feed...")
        rss_content = generator.generate_rss(updates)
        
        os.makedirs(generator.rss_dir, exist_ok=True)
        
        with open(generator.rss_file, 'wb') as f:
            f.write(rss_content)
        
        print(f"RSS feed saved to {generator.rss_file}")
    else:
        print("\nNo changes detected, skipping RSS generation")
    
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
