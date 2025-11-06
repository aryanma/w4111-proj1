# Stock Social Platform - Project Part 3

A Twitter-like social platform for stock discussion built with Flask and PostgreSQL.

## Database Information
- **PostgreSQL Account**: ku2199
- **Database**: proj1part2 on 34.139.8.30

## Features Implemented

### All Entities and Relationships
1. **Users (app_user)**: View user profiles, follow/unfollow users
2. **Posts**: Create posts with stock mentions ($TICKER) and hashtags (#hashtag)
3. **Comments**: Comment on posts
4. **Likes (post_like)**: Like and unlike posts
5. **Stocks**: Browse all stocks, search stocks, view posts by stock ticker
6. **Stock Mentions (post_mention)**: Automatically link posts to stocks using $TICKER syntax
7. **Hashtags**: Automatically extract and create hashtags from posts using #hashtag syntax
8. **Follow Relationships**: Follow/unfollow other users

### Pages and Functionality

1. **Home Page (/)**:
   - View feed of all posts with stock mentions
   - Create new posts
   - Like/unlike posts
   - Must login (select user) to access full features

2. **User Selection (/select_user)**:
   - Simple login by selecting an existing user
   - No password required (as per project requirements)

3. **User Profile (/profile/<username>)**:
   - View user information and biography
   - See user statistics (post count, followers, following)
   - Follow/unfollow users
   - View all posts by the user

4. **Post Detail (/post/<post_id>)**:
   - View individual post with all comments
   - Add comments to posts
   - Like/unlike posts

5. **Browse Stocks (/stocks)**:
   - View all stocks in database
   - Search stocks by ticker or name
   - Link to view posts for each stock

6. **Stock Detail (/stock/<ticker>)**:
   - View stock information
   - See all posts mentioning this stock
   - See total mention count

7. **Trending Stocks (/trending)**:
   - Ranked list of stocks by number of mentions
   - Shows which stocks are most discussed

8. **Hashtags (/hashtags)**:
   - View all hashtags with usage counts
   - Automatically created when users include #hashtag in posts

9. **Hashtag Detail (/hashtag/<tag_id>)**:
   - View all posts tagged with specific hashtag

## Setup Instructions

### On Your Google Cloud VM:

1. SSH into your VM:
   ```bash
   ssh your-vm-name
   ```

2. Navigate to your project directory and pull the latest code:
   ```bash
   cd <projectname>
   git pull
   ```

3. Activate your virtual environment:
   ```bash
   source venv/bin/activate
   ```

4. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```

5. Run the server:
   ```bash
   python3 server.py
   ```

6. The application will be accessible at `http://<YOUR-VM-IP>:8111/`

### Keep Server Running (for mentor meeting):
```bash
screen
source venv/bin/activate
python3 server.py
# Press CTRL+A then D to detach
# Use "screen -r" to reattach later
```

## Interesting Database Operations

### 1. Home Feed with Aggregated Stock Mentions
**Page**: Home Page (/)

**What it does**: This query retrieves all posts with their associated data, aggregates all stock tickers mentioned in each post into a comma-separated string, and checks if the current user has liked each post.

**Database Operation**:
```sql
SELECT DISTINCT p.post_id, p.content, p.created_at, p.like_count, p.comment_count,
       u.username,
       STRING_AGG(DISTINCT pm.ticker, ',' ORDER BY pm.ticker) as tickers,
       CASE WHEN pl.user_id IS NOT NULL THEN TRUE ELSE FALSE END as user_liked
FROM post p
JOIN app_user u ON p.user_id = u.user_id
LEFT JOIN post_mention pm ON p.post_id = pm.post_id
LEFT JOIN post_like pl ON p.post_id = pl.post_id AND pl.user_id = :current_user_id
GROUP BY p.post_id, p.content, p.created_at, p.like_count, p.comment_count, u.username, pl.user_id
ORDER BY p.created_at DESC
```

**Why it's interesting**:
- Uses `STRING_AGG` to combine multiple stock mentions into a single field
- Performs a conditional check to see if the current user has liked the post
- Combines data from 4 different tables (post, app_user, post_mention, post_like)
- Efficiently handles the many-to-many relationship between posts and stocks
- The aggregation is necessary because a post can mention multiple stocks

### 2. Trending Stocks by Mention Count
**Page**: Trending Stocks (/trending)

**What it does**: Calculates which stocks are most frequently mentioned across all posts, providing insights into what the community is discussing most.

**Database Operation**:
```sql
SELECT s.ticker, s.name, s.sector, s.exchange, COUNT(pm.post_id) as mention_count
FROM stock s
LEFT JOIN post_mention pm ON s.ticker = pm.ticker
GROUP BY s.ticker, s.name, s.sector, s.exchange
HAVING COUNT(pm.post_id) > 0
ORDER BY mention_count DESC, s.ticker
LIMIT 50
```

**Why it's interesting**:
- Aggregates data across the entire database to calculate trending metrics
- Uses `COUNT` with `GROUP BY` to calculate mention frequency
- Uses `HAVING` clause to filter out stocks with no mentions
- Provides business intelligence insights (which stocks are most discussed)
- Demonstrates the relationship between stocks and posts through the post_mention junction table
- Results change dynamically as users create more posts
- Orders by popularity (mention_count) which is computed from relationships, not a stored value

## How Posts Interact with the Database

When a user creates a post:
1. Post content is inserted into the `post` table
2. Content is parsed with regex to extract stock tickers (e.g., $AAPL, $TSLA)
3. For each ticker found, the app checks if it exists in the `stock` table
4. Valid tickers create entries in the `post_mention` junction table
5. Content is also parsed for hashtags (e.g., #bullish, #earnings)
6. Hashtags are created or retrieved from `hashtag` table
7. Links are created in `post_hashtag` junction table

This automatic extraction and linking allows users to naturally write posts while the system builds relationships in the database, enabling powerful queries like trending analysis and filtered feeds.

## Implementation vs Original Proposal

### Implemented from Proposal:
- ✅ All entities (User, Post, Comment, Stock, Hashtag)
- ✅ All relationships (Follow, Post_like, Post_mention, Post_hashtag)
- ✅ User profiles with follow functionality
- ✅ Creating posts with stock mentions
- ✅ Commenting on posts
- ✅ Liking posts
- ✅ Viewing posts by stock ticker
- ✅ Trending stocks based on mentions
- ✅ Hashtag functionality
- ✅ Browse and search stocks

### Not Implemented:
- None - all proposed features have been implemented

### Additional Features (not in proposal):
- Stock search functionality
- Hashtag browsing and filtering
- User statistics (post count, follower count)
- Like/unlike toggle functionality
