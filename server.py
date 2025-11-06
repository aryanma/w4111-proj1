"""
Columbia's COMS W4111.001 Introduction to Databases
Stock Social Platform - Twitter-like application for stock discussion
"""
import os
import re
from sqlalchemy import *
from sqlalchemy.pool import NullPool
from flask import Flask, request, render_template, g, redirect, Response, abort, session, url_for

tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app = Flask(__name__, template_folder=tmpl_dir)
app.secret_key = 'your-secret-key-here-change-in-production'

# Database credentials
DATABASE_USERNAME = "ku2199"
DATABASE_PASSWRD = "037281"
DATABASE_HOST = "34.139.8.30"
DATABASEURI = f"postgresql://{DATABASE_USERNAME}:{DATABASE_PASSWRD}@{DATABASE_HOST}/proj1part2"

# Create database engine
engine = create_engine(DATABASEURI)

@app.before_request
def before_request():
    """Setup database connection for each request"""
    try:
        g.conn = engine.connect()
    except:
        print("Problem connecting to database")
        import traceback; traceback.print_exc()
        g.conn = None

@app.teardown_request
def teardown_request(exception):
    """Close database connection after each request"""
    try:
        g.conn.close()
    except Exception as e:
        pass

def get_current_user():
    """Get the currently logged in user from session"""
    return session.get('username')

def extract_stock_tickers(content):
    """Extract stock tickers from post content (format: $AAPL)"""
    return re.findall(r'\$([A-Z]{1,5})\b', content)

def extract_hashtags(content):
    """Extract hashtags from post content (format: #hashtag)"""
    return re.findall(r'#(\w+)', content)

@app.route('/')
def index():
    """Home page with post feed"""
    current_user = get_current_user()

    if not current_user:
        return render_template("index.html", current_user=None, posts=[])

    # Get recent posts with user information and stock mentions
    query = """
        SELECT DISTINCT p.post_id, p.content, p.created_at,
               u.username,
               STRING_AGG(DISTINCT pm.ticker, ',' ORDER BY pm.ticker) as tickers,
               CASE WHEN pl.user_id IS NOT NULL THEN TRUE ELSE FALSE END as user_liked,
               (SELECT COUNT(*) FROM post_like WHERE post_id = p.post_id) as like_count,
               (SELECT COUNT(*) FROM comment WHERE post_id = p.post_id) as comment_count
        FROM post p
        JOIN app_user u ON p.user_id = u.user_id
        LEFT JOIN post_mention pm ON p.post_id = pm.post_id
        LEFT JOIN post_like pl ON p.post_id = pl.post_id AND pl.user_id = (
            SELECT user_id FROM app_user WHERE username = :username
        )
        GROUP BY p.post_id, p.content, p.created_at, u.username, pl.user_id
        ORDER BY p.created_at DESC
        LIMIT 50
    """
    cursor = g.conn.execute(text(query), {"username": current_user})
    posts = []
    for row in cursor:
        posts.append({
            'post_id': row[0],
            'content': row[1],
            'created_at': row[2],
            'username': row[3],
            'tickers': row[4] or '',
            'user_liked': row[5],
            'like_count': row[6] or 0,
            'comment_count': row[7] or 0
        })
    cursor.close()

    return render_template("index.html", current_user=current_user, posts=posts)

@app.route('/select_user', methods=['GET', 'POST'])
def select_user():
    """User selection/login page"""
    if request.method == 'POST':
        username = request.form.get('username')
        if username:
            session['username'] = username
            return redirect('/')

    # Get all users
    query = "SELECT username, email FROM app_user ORDER BY username"
    cursor = g.conn.execute(text(query))
    users = []
    for row in cursor:
        users.append({'username': row[0], 'email': row[1]})
    cursor.close()

    return render_template("select_user.html", users=users, current_user=get_current_user())

@app.route('/logout')
def logout():
    """Logout current user"""
    session.pop('username', None)
    return redirect('/')

@app.route('/create_post', methods=['POST'])
def create_post():
    """Create a new post"""
    current_user = get_current_user()
    if not current_user:
        return redirect('/select_user')

    content = request.form.get('content', '').strip()
    if not content:
        return redirect('/')

    # Validate content length (database constraint: 5-500 characters)
    if len(content) < 5:
        session['error'] = 'Post must be at least 5 characters long'
        return redirect('/')
    if len(content) > 500:
        session['error'] = 'Post must be no more than 500 characters long'
        return redirect('/')

    # Get user_id
    cursor = g.conn.execute(text("SELECT user_id FROM app_user WHERE username = :username"),
                           {"username": current_user})
    user_row = cursor.fetchone()
    cursor.close()

    if not user_row:
        return redirect('/select_user')

    user_id = user_row[0]

    # Insert post
    insert_query = """
        INSERT INTO post (user_id, content, created_at)
        VALUES (:user_id, :content, NOW())
        RETURNING post_id
    """
    cursor = g.conn.execute(text(insert_query), {"user_id": user_id, "content": content})
    post_id = cursor.fetchone()[0]
    g.conn.commit()
    cursor.close()

    # Extract and insert stock mentions
    tickers = extract_stock_tickers(content)
    for ticker in set(tickers):  # Remove duplicates
        # Check if stock exists
        check_query = "SELECT ticker FROM stock WHERE ticker = :ticker"
        cursor = g.conn.execute(text(check_query), {"ticker": ticker})
        if cursor.fetchone():
            # Insert mention
            mention_query = """
                INSERT INTO post_mention (post_id, ticker)
                VALUES (:post_id, :ticker)
                ON CONFLICT DO NOTHING
            """
            g.conn.execute(text(mention_query), {"post_id": post_id, "ticker": ticker})
            g.conn.commit()
        cursor.close()

    # Extract and insert hashtags
    hashtags = extract_hashtags(content)
    for tag in set(hashtags):
        # Get or create hashtag
        check_tag = "SELECT tag_id FROM hashtag WHERE LOWER(tag) = LOWER(:tag)"
        cursor = g.conn.execute(text(check_tag), {"tag": tag})
        tag_row = cursor.fetchone()
        cursor.close()

        if tag_row:
            tag_id = tag_row[0]
        else:
            # Create new hashtag
            insert_tag = "INSERT INTO hashtag (tag) VALUES (:tag) RETURNING tag_id"
            cursor = g.conn.execute(text(insert_tag), {"tag": tag})
            tag_id = cursor.fetchone()[0]
            g.conn.commit()
            cursor.close()

        # Link post to hashtag
        link_query = """
            INSERT INTO post_hashtag (post_id, tag_id)
            VALUES (:post_id, :tag_id)
            ON CONFLICT DO NOTHING
        """
        g.conn.execute(text(link_query), {"post_id": post_id, "tag_id": tag_id})
        g.conn.commit()

    return redirect('/')

@app.route('/post/<int:post_id>')
def post_detail(post_id):
    """View a specific post with its comments"""
    current_user = get_current_user()

    # Get post details
    query = """
        SELECT p.post_id, p.content, p.created_at,
               u.username,
               STRING_AGG(DISTINCT pm.ticker, ',' ORDER BY pm.ticker) as tickers,
               CASE WHEN pl.user_id IS NOT NULL THEN TRUE ELSE FALSE END as user_liked,
               (SELECT COUNT(*) FROM post_like WHERE post_id = p.post_id) as like_count,
               (SELECT COUNT(*) FROM comment WHERE post_id = p.post_id) as comment_count
        FROM post p
        JOIN app_user u ON p.user_id = u.user_id
        LEFT JOIN post_mention pm ON p.post_id = pm.post_id
        LEFT JOIN post_like pl ON p.post_id = pl.post_id AND pl.user_id = (
            SELECT user_id FROM app_user WHERE username = :username
        )
        WHERE p.post_id = :post_id
        GROUP BY p.post_id, p.content, p.created_at, u.username, pl.user_id
    """
    cursor = g.conn.execute(text(query), {"post_id": post_id, "username": current_user or ''})
    row = cursor.fetchone()
    cursor.close()

    if not row:
        abort(404)

    post = {
        'post_id': row[0],
        'content': row[1],
        'created_at': row[2],
        'username': row[3],
        'tickers': row[4] or '',
        'user_liked': row[5],
        'like_count': row[6] or 0,
        'comment_count': row[7] or 0
    }

    # Get comments
    comment_query = """
        SELECT c.comment_id, c.content, c.created_at, u.username
        FROM comment c
        JOIN app_user u ON c.user_id = u.user_id
        WHERE c.post_id = :post_id
        ORDER BY c.created_at ASC
    """
    cursor = g.conn.execute(text(comment_query), {"post_id": post_id})
    comments = []
    for row in cursor:
        comments.append({
            'comment_id': row[0],
            'content': row[1],
            'created_at': row[2],
            'username': row[3]
        })
    cursor.close()

    return render_template("post_detail.html", post=post, comments=comments, current_user=current_user)

@app.route('/like_post', methods=['POST'])
def like_post():
    """Like or unlike a post"""
    current_user = get_current_user()
    if not current_user:
        return redirect('/select_user')

    post_id = request.form.get('post_id')
    if not post_id:
        return redirect('/')

    # Get user_id
    cursor = g.conn.execute(text("SELECT user_id FROM app_user WHERE username = :username"),
                           {"username": current_user})
    user_row = cursor.fetchone()
    cursor.close()

    if not user_row:
        return redirect('/select_user')

    user_id = user_row[0]

    # Check if already liked
    check_query = "SELECT * FROM post_like WHERE user_id = :user_id AND post_id = :post_id"
    cursor = g.conn.execute(text(check_query), {"user_id": user_id, "post_id": post_id})
    already_liked = cursor.fetchone() is not None
    cursor.close()

    if already_liked:
        # Unlike
        delete_query = "DELETE FROM post_like WHERE user_id = :user_id AND post_id = :post_id"
        g.conn.execute(text(delete_query), {"user_id": user_id, "post_id": post_id})
    else:
        # Like
        insert_query = """
            INSERT INTO post_like (user_id, post_id, liked_at)
            VALUES (:user_id, :post_id, NOW())
        """
        g.conn.execute(text(insert_query), {"user_id": user_id, "post_id": post_id})

    g.conn.commit()

    # Redirect back to referrer or home
    return redirect(request.referrer or '/')

@app.route('/add_comment', methods=['POST'])
def add_comment():
    """Add a comment to a post"""
    current_user = get_current_user()
    if not current_user:
        return redirect('/select_user')

    post_id = request.form.get('post_id')
    content = request.form.get('content', '').strip()

    if not post_id or not content:
        return redirect('/')

    # Get user_id
    cursor = g.conn.execute(text("SELECT user_id FROM app_user WHERE username = :username"),
                           {"username": current_user})
    user_row = cursor.fetchone()
    cursor.close()

    if not user_row:
        return redirect('/select_user')

    user_id = user_row[0]

    # Insert comment
    insert_query = """
        INSERT INTO comment (post_id, user_id, content, created_at)
        VALUES (:post_id, :user_id, :content, NOW())
    """
    g.conn.execute(text(insert_query), {"post_id": post_id, "user_id": user_id, "content": content})
    g.conn.commit()

    return redirect(f'/post/{post_id}')

@app.route('/profile/<username>')
def profile(username):
    """View user profile"""
    current_user = get_current_user()

    # Get user info
    user_query = "SELECT user_id, username, email, biography FROM app_user WHERE username = :username"
    cursor = g.conn.execute(text(user_query), {"username": username})
    user_row = cursor.fetchone()
    cursor.close()

    if not user_row:
        abort(404)

    user = {
        'user_id': user_row[0],
        'username': user_row[1],
        'email': user_row[2],
        'biography': user_row[3]
    }

    # Get user stats
    stats_query = """
        SELECT
            (SELECT COUNT(*) FROM post WHERE user_id = :user_id) as post_count,
            (SELECT COUNT(*) FROM follow WHERE following_id = :user_id) as follower_count,
            (SELECT COUNT(*) FROM follow WHERE follower_id = :user_id) as following_count
    """
    cursor = g.conn.execute(text(stats_query), {"user_id": user['user_id']})
    stats_row = cursor.fetchone()
    cursor.close()

    stats = {
        'post_count': stats_row[0],
        'follower_count': stats_row[1],
        'following_count': stats_row[2]
    }

    # Check if current user is following this user
    is_following = False
    if current_user and current_user != username:
        follow_query = """
            SELECT * FROM follow
            WHERE follower_id = (SELECT user_id FROM app_user WHERE username = :current_user)
            AND following_id = :user_id
        """
        cursor = g.conn.execute(text(follow_query), {"current_user": current_user, "user_id": user['user_id']})
        is_following = cursor.fetchone() is not None
        cursor.close()

    # Get user's posts
    posts_query = """
        SELECT p.post_id, p.content, p.created_at,
               STRING_AGG(DISTINCT pm.ticker, ',' ORDER BY pm.ticker) as tickers,
               (SELECT COUNT(*) FROM post_like WHERE post_id = p.post_id) as like_count,
               (SELECT COUNT(*) FROM comment WHERE post_id = p.post_id) as comment_count
        FROM post p
        LEFT JOIN post_mention pm ON p.post_id = pm.post_id
        WHERE p.user_id = :user_id
        GROUP BY p.post_id, p.content, p.created_at
        ORDER BY p.created_at DESC
        LIMIT 50
    """
    cursor = g.conn.execute(text(posts_query), {"user_id": user['user_id']})
    posts = []
    for row in cursor:
        posts.append({
            'post_id': row[0],
            'content': row[1],
            'created_at': row[2],
            'tickers': row[3] or '',
            'like_count': row[4] or 0,
            'comment_count': row[5] or 0
        })
    cursor.close()

    return render_template("profile.html", user=user, stats=stats, is_following=is_following,
                          posts=posts, current_user=current_user)

@app.route('/follow', methods=['POST'])
def follow():
    """Follow or unfollow a user"""
    current_user = get_current_user()
    if not current_user:
        return redirect('/select_user')

    target_username = request.form.get('username')
    if not target_username or target_username == current_user:
        return redirect('/')

    # Get user IDs
    cursor = g.conn.execute(text("SELECT user_id FROM app_user WHERE username = :username"),
                           {"username": current_user})
    current_user_row = cursor.fetchone()
    cursor.close()

    cursor = g.conn.execute(text("SELECT user_id FROM app_user WHERE username = :username"),
                           {"username": target_username})
    target_user_row = cursor.fetchone()
    cursor.close()

    if not current_user_row or not target_user_row:
        return redirect('/')

    current_user_id = current_user_row[0]
    target_user_id = target_user_row[0]

    # Check if already following
    check_query = "SELECT * FROM follow WHERE follower_id = :follower_id AND following_id = :following_id"
    cursor = g.conn.execute(text(check_query), {"follower_id": current_user_id, "following_id": target_user_id})
    already_following = cursor.fetchone() is not None
    cursor.close()

    if already_following:
        # Unfollow
        delete_query = "DELETE FROM follow WHERE follower_id = :follower_id AND following_id = :following_id"
        g.conn.execute(text(delete_query), {"follower_id": current_user_id, "following_id": target_user_id})
    else:
        # Follow
        insert_query = """
            INSERT INTO follow (follower_id, following_id, followed_at)
            VALUES (:follower_id, :following_id, NOW())
        """
        g.conn.execute(text(insert_query), {"follower_id": current_user_id, "following_id": target_user_id})

    g.conn.commit()

    return redirect(f'/profile/{target_username}')

@app.route('/stocks')
def stocks():
    """Browse all stocks with search"""
    current_user = get_current_user()
    search_query = request.args.get('search', '').strip()

    if search_query:
        query = """
            SELECT ticker, name, sector, exchange
            FROM stock
            WHERE LOWER(ticker) LIKE LOWER(:search) OR LOWER(name) LIKE LOWER(:search)
            ORDER BY ticker
        """
        cursor = g.conn.execute(text(query), {"search": f"%{search_query}%"})
    else:
        query = "SELECT ticker, name, sector, exchange FROM stock ORDER BY ticker"
        cursor = g.conn.execute(text(query))

    stocks = []
    for row in cursor:
        stocks.append({
            'ticker': row[0],
            'name': row[1],
            'sector': row[2],
            'exchange': row[3]
        })
    cursor.close()

    return render_template("stocks.html", stocks=stocks, search_query=search_query, current_user=current_user)

@app.route('/stock/<ticker>')
def stock_detail(ticker):
    """View posts mentioning a specific stock"""
    current_user = get_current_user()

    # Get stock info
    stock_query = "SELECT ticker, name, sector, exchange FROM stock WHERE ticker = :ticker"
    cursor = g.conn.execute(text(stock_query), {"ticker": ticker})
    stock_row = cursor.fetchone()
    cursor.close()

    if not stock_row:
        abort(404)

    stock = {
        'ticker': stock_row[0],
        'name': stock_row[1],
        'sector': stock_row[2],
        'exchange': stock_row[3]
    }

    # Get mention count
    count_query = "SELECT COUNT(*) FROM post_mention WHERE ticker = :ticker"
    cursor = g.conn.execute(text(count_query), {"ticker": ticker})
    mention_count = cursor.fetchone()[0]
    cursor.close()

    # Get posts mentioning this stock
    posts_query = """
        SELECT p.post_id, p.content, p.created_at,
               u.username,
               CASE WHEN pl.user_id IS NOT NULL THEN TRUE ELSE FALSE END as user_liked,
               (SELECT COUNT(*) FROM post_like WHERE post_id = p.post_id) as like_count,
               (SELECT COUNT(*) FROM comment WHERE post_id = p.post_id) as comment_count
        FROM post p
        JOIN app_user u ON p.user_id = u.user_id
        JOIN post_mention pm ON p.post_id = pm.post_id
        LEFT JOIN post_like pl ON p.post_id = pl.post_id AND pl.user_id = (
            SELECT user_id FROM app_user WHERE username = :username
        )
        WHERE pm.ticker = :ticker
        ORDER BY p.created_at DESC
        LIMIT 100
    """
    cursor = g.conn.execute(text(posts_query), {"ticker": ticker, "username": current_user or ''})
    posts = []
    for row in cursor:
        posts.append({
            'post_id': row[0],
            'content': row[1],
            'created_at': row[2],
            'username': row[3],
            'user_liked': row[4],
            'like_count': row[5] or 0,
            'comment_count': row[6] or 0
        })
    cursor.close()

    return render_template("stock_detail.html", stock=stock, mention_count=mention_count,
                          posts=posts, current_user=current_user)

@app.route('/trending')
def trending():
    """View trending stocks by mention count"""
    current_user = get_current_user()

    query = """
        SELECT s.ticker, s.name, s.sector, s.exchange, COUNT(pm.post_id) as mention_count
        FROM stock s
        LEFT JOIN post_mention pm ON s.ticker = pm.ticker
        GROUP BY s.ticker, s.name, s.sector, s.exchange
        HAVING COUNT(pm.post_id) > 0
        ORDER BY mention_count DESC, s.ticker
        LIMIT 50
    """
    cursor = g.conn.execute(text(query))
    trending_stocks = []
    for row in cursor:
        trending_stocks.append({
            'ticker': row[0],
            'name': row[1],
            'sector': row[2],
            'exchange': row[3],
            'mention_count': row[4]
        })
    cursor.close()

    return render_template("trending.html", trending_stocks=trending_stocks, current_user=current_user)

@app.route('/hashtags')
def hashtags():
    """View all hashtags"""
    current_user = get_current_user()

    query = """
        SELECT h.tag_id, h.tag, h.description, COUNT(ph.post_id) as post_count
        FROM hashtag h
        LEFT JOIN post_hashtag ph ON h.tag_id = ph.tag_id
        GROUP BY h.tag_id, h.tag, h.description
        ORDER BY post_count DESC, h.tag
    """
    cursor = g.conn.execute(text(query))
    hashtags = []
    for row in cursor:
        hashtags.append({
            'tag_id': row[0],
            'tag': row[1],
            'description': row[2],
            'post_count': row[3]
        })
    cursor.close()

    return render_template("hashtags.html", hashtags=hashtags, current_user=current_user)

@app.route('/hashtag/<int:tag_id>')
def hashtag_detail(tag_id):
    """View posts with a specific hashtag"""
    current_user = get_current_user()

    # Get hashtag info
    hashtag_query = "SELECT tag_id, tag, description FROM hashtag WHERE tag_id = :tag_id"
    cursor = g.conn.execute(text(hashtag_query), {"tag_id": tag_id})
    hashtag_row = cursor.fetchone()
    cursor.close()

    if not hashtag_row:
        abort(404)

    hashtag = {
        'tag_id': hashtag_row[0],
        'tag': hashtag_row[1],
        'description': hashtag_row[2]
    }

    # Get posts with this hashtag
    posts_query = """
        SELECT p.post_id, p.content, p.created_at,
               u.username,
               CASE WHEN pl.user_id IS NOT NULL THEN TRUE ELSE FALSE END as user_liked,
               (SELECT COUNT(*) FROM post_like WHERE post_id = p.post_id) as like_count,
               (SELECT COUNT(*) FROM comment WHERE post_id = p.post_id) as comment_count
        FROM post p
        JOIN app_user u ON p.user_id = u.user_id
        JOIN post_hashtag ph ON p.post_id = ph.post_id
        LEFT JOIN post_like pl ON p.post_id = pl.post_id AND pl.user_id = (
            SELECT user_id FROM app_user WHERE username = :username
        )
        WHERE ph.tag_id = :tag_id
        ORDER BY p.created_at DESC
        LIMIT 100
    """
    cursor = g.conn.execute(text(posts_query), {"tag_id": tag_id, "username": current_user or ''})
    posts = []
    for row in cursor:
        posts.append({
            'post_id': row[0],
            'content': row[1],
            'created_at': row[2],
            'username': row[3],
            'user_liked': row[4],
            'like_count': row[5] or 0,
            'comment_count': row[6] or 0
        })
    cursor.close()

    return render_template("hashtag_detail.html", hashtag=hashtag, posts=posts, current_user=current_user)

if __name__ == "__main__":
    import click

    @click.command()
    @click.option('--debug', is_flag=True)
    @click.option('--threaded', is_flag=True)
    @click.argument('HOST', default='0.0.0.0')
    @click.argument('PORT', default=8111, type=int)
    def run(debug, threaded, host, port):
        """
        This function handles command line parameters.
        Run the server using:
            python server.py
        """
        HOST, PORT = host, port
        print("running on %s:%d" % (HOST, PORT))
        app.run(host=HOST, port=PORT, debug=debug, threaded=threaded)

    run()
