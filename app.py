import json
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_socketio import SocketIO, emit, join_room, leave_room
import os
import sqlite3
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup
import re
from openai import OpenAI
from werkzeug.security import generate_password_hash, check_password_hash
from pyncm.apis import cloudsearch
from pyncm.apis.login import LoginViaAnonymousAccount

# Define the UTC+8 timezone
LoginViaAnonymousAccount()
JST = timezone(timedelta(hours=8))

DATABASE = 'chat.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_online BOOLEAN DEFAULT FALSE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname TEXT NOT NULL,
            message TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'text',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname TEXT UNIQUE NOT NULL,
            last_cleared_message_id INTEGER DEFAULT 0,
            FOREIGN KEY (nickname) REFERENCES users(nickname)
        )
    ''')
    conn.commit()
    conn.close()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

# OpenAI Client Configuration
# NOTE: You should ideally use environment variables for API keys
# For now, we'll use a placeholder. User needs to set this.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "sk-rgijapfapkddnnbbwftgcqycdniodxuxqibiwrtfnthxdaqw") 
# Use a base_url if using a proxy or a different provider compatible with OpenAI SDK
# Assuming SiliconFlow (siliconflow.cn) based on the model name "Qwen/Qwen2.5-7B-Instruct" commonly hosted there
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1")

client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
# Global storage for online users: {session_id: nickname}
online_users = {}

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"servers": []}

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/chat')
def chat():
    nickname = session.get('nickname')
    if not nickname:
        return redirect(url_for('index'))
    return render_template('chat.html', nickname=nickname)

@app.route('/api/servers')
def get_servers():
    config = load_config()
    return jsonify(config.get('servers', []))

@app.route('/api/check_nickname', methods=['POST'])
def check_nickname():
    data = request.json
    nickname = data.get('nickname')
    if not nickname:
        return jsonify({'valid': False, 'message': 'Nickname cannot be empty'})
    
    # Only check against currently online users (in-memory) for immediate feedback
    if nickname in online_users.values():
        return jsonify({'valid': False, 'message': 'Nickname already taken by an active user'})
    
    return jsonify({'valid': True})

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.json
        nickname = data.get('nickname')
        password = data.get('password')

        if not nickname or not password:
            return jsonify({'success': False, 'message': 'Nickname and password are required.'}), 400

        if len(password) < 6:
            return jsonify({'success': False, 'message': 'Password must be at least 6 characters long.'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE nickname = ?", (nickname,))
        existing_user = cursor.fetchone()
        if existing_user:
            conn.close()
            return jsonify({'success': False, 'message': 'Nickname already exists.'}), 409

        hashed_password = generate_password_hash(password)
        cursor.execute("INSERT INTO users (nickname, password_hash) VALUES (?, ?)", (nickname, hashed_password))
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Registration successful.'}), 201
    except Exception as e:
        print(f"Registration error: {e}")
        return jsonify({'success': False, 'message': 'An internal server error occurred during registration.'}), 500

@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.json
        nickname = data.get('nickname')
        password = data.get('password')

        if not nickname or not password:
            return jsonify({'success': False, 'message': 'Nickname and password are required.'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE nickname = ?", (nickname,))
        user = cursor.fetchone()

        if not user or not check_password_hash(user['password_hash'], password):
            conn.close()
            return jsonify({'success': False, 'message': 'Invalid nickname or password.'}), 401

        session['nickname'] = nickname
        return jsonify({'success': True, 'message': 'Login successful.', 'nickname': nickname}), 200
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'success': False, 'message': 'An internal server error occurred during login.'}), 500

@app.route('/api/history')
def get_history():
    nickname = session.get('nickname')
    if not nickname:
        return jsonify([]) # Or an error, depending on desired behavior

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get user's last_cleared_message_id
    cursor.execute("SELECT last_cleared_message_id FROM user_preferences WHERE nickname = ?", (nickname,))
    result = cursor.fetchone()
    last_cleared_message_id = result[0] if result else 0

    # Fetch messages with ID greater than last_cleared_message_id
    cursor.execute("SELECT nickname, message, type, timestamp FROM messages WHERE id > ? ORDER BY timestamp ASC LIMIT 100", (last_cleared_message_id,))
    history = cursor.fetchall()
    conn.close()
    return jsonify([dict(row) for row in history])

@app.route('/clear_history', methods=['POST'])
def clear_history():
    try:
        nickname = session.get('nickname')
        if not nickname:
            return jsonify({'success': False, 'message': 'User not logged in.'}), 401

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get the maximum message ID for the current user
        cursor.execute("SELECT MAX(id) FROM messages WHERE nickname = ?", (nickname,))
        max_message_id = cursor.fetchone()[0]
        if max_message_id is None: # No messages yet
            max_message_id = 0

        # Update or insert user's last_cleared_message_id
        cursor.execute(
            "INSERT INTO user_preferences (nickname, last_cleared_message_id) VALUES (?, ?) "
            "ON CONFLICT(nickname) DO UPDATE SET last_cleared_message_id = ?",
            (nickname, max_message_id, max_message_id)
        )
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Chat history cleared for current user.'})
    except Exception as e:
        print(f"Error clearing history: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print(f'Disconnect event triggered for SID: {request.sid}')
    nickname = online_users.pop(request.sid, None)
    if nickname:
        print(f'User {nickname} found in online_users. Attempting to set offline.')
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_online = FALSE WHERE nickname = ?", (nickname,))
        conn.commit()
        conn.close()
        print(f'User {nickname} is_online status set to FALSE in DB.')

        # Get all online users from DB for broadcasting
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT nickname, is_online FROM users")
        all_users_status = [{"nickname": row['nickname'], "is_online": bool(row['is_online'])} for row in cursor.fetchall()]
        conn.close()

        emit('user_left', {
            'nickname': nickname,
            'users': all_users_status
        }, broadcast=True)
        print(f'User {nickname} disconnected')

@socketio.on('join')
def handle_join(data):
    nickname = data.get('nickname')
    if not nickname:
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if nickname exists in the persistent users table and is not already online
    cursor.execute("SELECT * FROM users WHERE nickname = ?", (nickname,))
    user_db = cursor.fetchone()

    if not user_db:
        emit('error', {'message': 'Nickname not registered.'})
        conn.close()
        return

    # Update user's online status in DB
    cursor.execute("UPDATE users SET is_online = TRUE WHERE nickname = ?", (nickname,))
    conn.commit()
    conn.close()

    online_users[request.sid] = nickname
    join_room('chat_room')
    
    # Get all online users from DB for broadcasting
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nickname, is_online FROM users")
    all_users_status = [{"nickname": row['nickname'], "is_online": bool(row['is_online'])} for row in cursor.fetchall()]
    conn.close()

    emit('user_joined', {
        'nickname': nickname, 
        'users': all_users_status
    }, broadcast=True)
    
    # Send current user list to the new user
    emit('user_list', {'users': all_users_status})

    # Send chat history to the new user
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get user's last_cleared_message_id
    cursor.execute("SELECT last_cleared_message_id FROM user_preferences WHERE nickname = ?", (nickname,))
    result = cursor.fetchone()
    last_cleared_message_id = result[0] if result else 0

    cursor.execute("SELECT nickname, message, type, timestamp FROM messages WHERE id > ? ORDER BY timestamp ASC LIMIT 100", (last_cleared_message_id,))
    history = cursor.fetchall()
    conn.close()
    for msg_row in history:
        emit('message', {
            'nickname': msg_row['nickname'],
            'type': msg_row['type'],
            'payload': msg_row['message'],
            'original_msg': msg_row['message'], # For historical messages, original_msg is the message itself
            'timestamp': msg_row['timestamp']
        }, room=request.sid)

def get_weather(city):
    """
    使用 xxapi.cn 查询天气。
    city 可以是中文。
    """
    try:
        url = f"https://v2.xxapi.cn/api/weatherDetails?city={city}&key=ffe7411cac3574ad"
        headers = {
            'User-Agent': 'xiaoxiaoapi/1.0.0'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for HTTP errors
        data = response.json()

        if data['code'] == 200 and data.get('data'):
            response_data = data['data']
            city_name = response_data.get('city', city)
            
            daily_forecasts = response_data.get('data')

            if daily_forecasts and len(daily_forecasts) > 0:
                first_day_weather = daily_forecasts[0]

                if first_day_weather.get('real_time_weather') and len(first_day_weather['real_time_weather']) > 0:
                    real_time_info = first_day_weather['real_time_weather'][0]
                    weather = real_time_info.get('weather', '未知')
                    temperature = real_time_info.get('temperature', '未知')
                    humidity = real_time_info.get('humidity', '未知')
                    wind_dir = real_time_info.get('wind_dir', '未知')
                    wind_speed = real_time_info.get('wind_speed', '未知')

                    weather_payload = f"""
📍 **{city_name} 当前天气**
🌤 天气：{weather}
🌡 温度：{temperature}°C
💧 湿度：{humidity}%
🍃 风向：{wind_dir}
💨 风速：{wind_speed}
                    """.strip()
                    return {"payload": weather_payload, "weather_type": weather}
                else:
                    return f"无法获取 {city} 的实时天气信息。"
            else:
                print(f"API returned success but daily forecast data is missing or empty for '{city}': {data})")
                return f"API返回成功，但未提供 {city} 的天气预报数据。请检查城市名称或稍后再试。"
        else:
            print(f"API returned success but no main data object for '{city}': {data})")
            return f"无法获取 {city} 的天气信息。错误：{data.get('msg', '未知错误')}"


    except requests.exceptions.RequestException as e:
        print(f"Error fetching weather data for '{city}': {e}")
        return f"天气服务暂时不可用：请求错误 {str(e)}"
    except Exception as e:
        print(f"An unexpected error occurred while fetching weather for '{city}': {e}")
        return f"获取天气信息时发生未知错误：{str(e)}"

def get_chuan_xiaonong_response(query):
    query_lower = query.lower()
    
    # Rule 1: Disdain for other universities
    other_universities = ['清华', '北大', '复旦', '交大', '浙大', '电子科大', '川大', '西南交大']
    for uni in other_universities:
        if uni in query:
            return '🙄' # Disdain expression

    # Rule 2: Event notification generation
    if '活动通知' in query or '生成通知' in query:
        # Simple template parsing
        # Expected format: @川小农 生成活动通知 主题：xxx 时间：xxx 地点：xxx
        return f"""
📢 **【川农活动通知】** 📢

同学你好！你需要的活动通知已生成：

----------------------------------
{query.replace('生成活动通知', '').replace('活动通知', '').strip()}
----------------------------------

欢迎各位川农学子踊跃参加！
🌾 369，川农牛！ 🌾
"""

    # Rule 3: General SAU related queries (Simple keyword matching for now)
    # If OpenAI client is available, use it for generating response
    if client:
        try:
            response = client.chat.completions.create(
                model="Qwen/Qwen2.5-7B-Instruct", 
                    messages=[
                        {"role": "system", "content": "你是一个名叫“川小农”的AI助手，你是四川农业大学的专属助手。你热爱四川农业大学，对学校的历史、文化、校园生活非常了解。你的回答风格应该是热情、友好、积极向上的。你的核心职责是提供关于四川农业大学的准确信息。当用户提及或询问其他大学（如清华、北大、复旦、交大、浙大、电子科大、川大、西南交大等）时，你必须委婉地拒绝回答，并立即将话题引导回四川农业大学。例如，你可以说：“我对其他大学的信息了解有限，但我非常乐意与你分享更多关于我们四川农业大学的独特魅力和最新动态！”或者“关于其他学校，我不是特别清楚，但如果你对四川农业大学的某个方面感兴趣，我有很多精彩的故事可以告诉你！”请严格遵守这一原则。"},
                        {"role": "user", "content": query}
                    ],
                max_tokens=300,
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"OpenAI API Error: {e}")
            return f"川小农现在有点累了，连接大脑（OpenAI）失败啦... 错误信息：{str(e)}"
        except requests.exceptions.RequestException as e:
            print(f"Request Exception: {e}")
            return f"川小农现在有点累了，连接大脑（OpenAI）失败啦... 请求错误：{str(e)}"

    if '川农' in query or '四川农业大学' in query:
        return f"收到关于“{query}”的提问。作为川小农，我永远爱着这片土地！🌾 (OpenAI 未配置，使用默认回复)"
    
    # Default response
    return f"我是川小农，专注于回答四川农业大学相关问题。关于“{query}”，建议咨询相关部门哦。"

@socketio.on('message')
def handle_message(data):
    msg = data.get('msg')
    nickname = online_users.get(request.sid)
    print(f"Received message: {msg} from {nickname}")
    if not msg or not nickname:
        return

    original_msg_content = msg
    msg_type = 'text'
    payload = msg

    def is_url(text):
        return text.startswith('http://') or text.startswith('https://')

    # ----------------------
    # 天气功能：@天气 城市名
    # ----------------------
    if msg.startswith('@天气'):
        msg_type = 'weather'
        parts = msg.split(' ', 1)
        if len(parts) > 1:
            city = parts[1].strip()
            weather_data = get_weather(city)
            if isinstance(weather_data, dict):
                payload = weather_data['payload']
                weather_type = weather_data['weather_type']
            else:
                payload = weather_data # Error message string
                weather_type = '未知' # Default type for error messages
        else:
            payload = "❗ 用法：@天气 城市名，例如：@天气 上海"
    # ----------------------
    # 电影消息
    # ----------------------
    elif msg.startswith('@电影'):
        msg_type = 'movie'
        parts = msg.split(' ', 1)
        if len(parts) > 1:
            movie_input = parts[1].strip()
            if is_url(movie_input):
                payload = f"https://jx.xmflv.com/?url={movie_input}"
            else:
                direct_video_url = get_movie_resource_url(movie_input)
                payload = f"https://jx.xmflv.com/?url={direct_video_url}" if direct_video_url else ''
        else:
            payload = ''

    # ----------------------
    # 川小农 AI
    # ----------------------
    elif msg.startswith('@川小农'):
        msg_type = 'ai'
        parts = msg.split(' ', 1)
        query = parts[1] if len(parts) > 1 else "你好"
        payload = get_chuan_xiaonong_response(query)


    # ----------------------
    # 新闻功能：@新闻
    # ----------------------
    elif msg.startswith('@新闻'):
        news_data = get_news()
        msg_type = news_data['type'] # 'news' or 'text'
        payload = json.dumps(news_data['payload'], ensure_ascii=False) # Convert list of dicts to JSON string

    # ----------------------
    # 音乐功能：@音乐 音乐名
    # ----------------------
    elif msg.startswith('@音乐'):
        msg_type = 'music'
        parts = msg.split(' ', 1)
        if len(parts) > 1:
            music_query = parts[1].strip()
            music_data = search_music(music_query)
            if music_data['success']:
                payload = json.dumps(music_data, ensure_ascii=False)
            else:
                payload = music_data['message']
        else:
            payload = "❗ 用法：@音乐 音乐名，例如：@音乐 晴天"

    # ----------------------
    # 保存到数据库
    # ----------------------
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (nickname, message, type, timestamp) VALUES (?, ?, ?, ?)",
        (nickname, payload, msg_type, datetime.now(JST))
    )
    conn.commit()
    conn.close()

    # ----------------------
    # 广播用户原始消息
    # ----------------------
    emit('message', {
        'nickname': nickname,
        'type': msg_type,  # 使用原始消息类型
        'payload': payload,
        'original_msg': original_msg_content,
        'timestamp': datetime.now(JST).isoformat(),
        'weather_type': weather_type if msg_type == 'weather' else None
    }, broadcast=True)

    # ----------------------
    # 广播 AI 回复（如果是 AI）
    # ----------------------
    if msg_type == 'ai':
        emit('message', {
            'nickname': "川小农",
            'type': 'ai',
            'payload': payload,
            'original_msg': original_msg_content,
            'timestamp': datetime.now(JST).isoformat()
        }, broadcast=True)


def search_music(query):
    try:
        # 使用 pyncm 搜索音乐
        search_results = cloudsearch.GetSearchResult(keyword=query)
        print(f"pyncm search results: {search_results}")
        
        if search_results and search_results['result'] and search_results['result']['songs']:
            first_song = search_results['result']['songs'][0]
            print(f"First song data: {first_song}")
            song_name = first_song['name']
            artist_name = first_song['ar'][0]['name'] if first_song['ar'] else '未知歌手'
            song_id = first_song['id']
            is_unplayable = first_song.get('privilege', {}).get('st', 0) == -200 # 判断是否为不可播放歌曲
            print(f"Calculated is_unplayable: {is_unplayable}")
            
            # 获取歌曲播放链接
            play_url = f"https://music.163.com/song/media/outer/url?id={song_id}.mp3"
            print(f"Generated play URL: {play_url}")
            
            music_data = {
                "success": True,
                "song_name": song_name,
                "artist_name": artist_name,
                "play_url": play_url,
                "is_unplayable": is_unplayable
            }
            print(f"Music data sent to frontend: {music_data}")
            return music_data
        else:
            return {"success": False, "message": f"未找到与 '{query}' 相关的音乐。"}
    except Exception as e:
        print(f"Error searching music: {e}")
        return {"success": False, "message": f"搜索音乐时发生错误: {str(e)}"}

def get_movie_resource_url(movie_name):
    base_url = "https://www.libvio.link"
    search_query = movie_name.replace(' ', '+')
    search_url = f"{base_url}/search/?wd={search_query}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        # Step 1: Search for the movie
        print(f"Searching for movie: {movie_name} at {search_url}")
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find the first movie link
        movie_link_tag = soup.find('a', class_='fed-list-pics')
        if not movie_link_tag:
            print(f"No movie link found for {movie_name}")
            return None

        movie_page_url = base_url + movie_link_tag['href']
        print(f"Found movie page: {movie_page_url}")

        # Step 2: Go to the movie's page to find the video resource URL
        response = requests.get(movie_page_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # The actual video URL is often embedded in a script or a specific player element.
        # This part might need adjustment if the website's structure changes.
        # We'll look for a common pattern where the video source is in a script tag.
        # This is a common pattern for video sites using JavaScript players.
        
        # Attempt to find a script tag that contains 'player_data' or similar video info
        script_tags = soup.find_all('script')
        video_url = None
        for script in script_tags:
            if script.string and 'player_data' in script.string:
                # Extract JSON data from the script tag
                match = re.search(r'var player_data=(\{.*?\})', script.string)
                if match:
                    player_data_json = match.group(1)
                    player_data = json.loads(player_data_json)
                    # The actual video URL might be in 'url' or 'link' within player_data
                    video_url = player_data.get('url') or player_data.get('link')
                    if video_url:
                        print(f"Extracted video URL: {video_url}")
                        return video_url
        
        # Fallback: If not found in player_data, look for iframe src or video tag src
        if not video_url:
            iframe = soup.find('iframe', id='playleft') # Common ID for video iframes
            if iframe and iframe.get('src'):
                # This might be a relative URL or another embedded player page
                iframe_src = iframe['src']
                if iframe_src.startswith('//'):
                    iframe_src = 'https:' + iframe_src
                elif iframe_src.startswith('/'):
                    iframe_src = base_url + iframe_src
                
                print(f"Found iframe src: {iframe_src}")
                # If the iframe src is directly the video, return it.
                # Otherwise, we might need to fetch this iframe_src and parse again.
                # For simplicity, let's assume it's the direct resource or a playable link.
                return iframe_src

        print(f"Could not find direct video resource URL for {movie_name}")
        return None

    except requests.exceptions.RequestException as e:
        print(f"Error fetching movie data for {movie_name}: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while getting movie resource for {movie_name}: {e}")
        return None
        # Step 1: Search for the movie
        print(f"Searching for movie: {movie_name} at {search_url}")
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find the first movie link
        movie_link_tag = soup.find('a', class_='fed-list-pics')
        if not movie_link_tag:
            print(f"No movie link found for {movie_name}")
            return None

        movie_page_url = base_url + movie_link_tag['href']
        print(f"Found movie page: {movie_page_url}")

        # Step 2: Go to the movie's page to find the video resource URL
        response = requests.get(movie_page_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # The actual video URL is often embedded in a script or a specific player element.
        # This part might need adjustment if the website's structure changes.
        # We'll look for a common pattern where the video source is in a script tag.
        # This is a common pattern for video sites using JavaScript players.
        
        # Attempt to find a script tag that contains 'player_data' or similar video info
        script_tags = soup.find_all('script')
        video_url = None
        for script in script_tags:
            if script.string and 'player_data' in script.string:
                # Extract JSON data from the script tag
                match = re.search(r'var player_data=(\{.*?\})', script.string)
                if match:
                    player_data_json = match.group(1)
                    player_data = json.loads(player_data_json)
                    # The actual video URL might be in 'url' or 'link' within player_data
                    video_url = player_data.get('url') or player_data.get('link')
                    if video_url:
                        print(f"Extracted video URL: {video_url}")
                        return video_url
        
        # Fallback: If not found in player_data, look for iframe src or video tag src
        if not video_url:
            iframe = soup.find('iframe', id='playleft') # Common ID for video iframes
            if iframe and iframe.get('src'):
                # This might be a relative URL or another embedded player page
                iframe_src = iframe['src']
                if iframe_src.startswith('//'):
                    iframe_src = 'https:' + iframe_src
                elif iframe_src.startswith('/'):
                    iframe_src = base_url + iframe_src
                
                print(f"Found iframe src: {iframe_src}")
                # If the iframe src is directly the video, return it.
                # Otherwise, we might need to fetch this iframe_src and parse again.
                # For simplicity, let's assume it's the direct resource or a playable link.
                return iframe_src

        print(f"Could not find direct video resource URL for {movie_name}")
        return None

    except requests.exceptions.RequestException as e:
        print(f"Error fetching movie data for {movie_name}: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while getting movie resource for {movie_name}: {e}")
        return None
    
    try:  # pyright: ignore[reportUnreachable]
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        soup = BeautifulSoup(response.text, 'html.parser')
        movie_link_element = soup.find('a', class_='fed-list-pics')
        
        if movie_link_element:
            movie_page_url = base_url + movie_link_element['href']
            
            # Now fetch the movie page to find the direct video URL
            movie_page_response = requests.get(movie_page_url, headers=headers, timeout=10)
            movie_page_response.raise_for_status()
            movie_page_soup = BeautifulSoup(movie_page_response.text, 'html.parser')
            
            # Find the script tag that contains 'var vid ='
            script_tags = movie_page_soup.find_all('script')
            for script in script_tags:
                if script.string and 'var vid = ' in script.string:
                    # Extract the video URL using regex
                    import re
                    match = re.search(r"var vid = '(.+?)';", script.string)
                    if match:
                        direct_video_url = match.group(1)
                        print(f"Extracted direct video URL: {direct_video_url}")
                        return direct_video_url
            print(f"Could not extract direct video URL from {movie_page_url}")
            return ""
        else:
            print(f"No movie link found for '{movie_name}' on {search_url}")
            return ""
            
    except requests.exceptions.RequestException as e:
        print(f"Error fetching movie data for '{movie_name}': {e}")
        return ""
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return ""
    
    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        movie_link = soup.find('a', class_='fed-list-pics') 
        
        if movie_link and movie_link.get('href'):
            movie_page_url = base_url + movie_link.get('href')
            print(f"Found movie page URL: {movie_page_url}")
            
            # Now fetch the movie playback page to extract the direct video URL
            movie_page_response = requests.get(movie_page_url, headers=headers, timeout=10)
            movie_page_response.raise_for_status()
            
            movie_page_soup = BeautifulSoup(movie_page_response.text, 'html.parser')
            script_tags = movie_page_soup.find_all('script')
            
            for script in script_tags:
                if script.string and 'var vid = ' in script.string:
                    # Extract the video URL using regex
                    import re
                    match = re.search(r"var vid = '(.+?)';", script.string)
                    if match:
                        direct_video_url = match.group(1)
                        print(f"Extracted direct video URL: {direct_video_url}")
                        return direct_video_url
    except Exception as e:
        print(f"Error fetching movie resource URL: {e}")
        return None
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        movie_link = soup.find('a', class_='fed-list-pics') 
        
        if movie_link and movie_link.get('href'):
            movie_page_url = base_url + movie_link.get('href')
            print(f"Found movie page URL: {movie_page_url}")
            
            # Now fetch the movie playback page to extract the direct video URL
            movie_page_response = requests.get(movie_page_url, headers=headers, timeout=10)
            movie_page_response.raise_for_status()
            
            movie_page_soup = BeautifulSoup(movie_page_response.text, 'html.parser')
            script_tags = movie_page_soup.find_all('script')
            
            for script in script_tags:
                if script.string and 'var vid = ' in script.string:
                    # Extract the video URL using regex
                    import re
                    match = re.search(r"var vid = '(.+?)';", script.string)
                    if match:
                        direct_video_url = match.group(1)
                        print(f"Extracted direct video URL: {direct_video_url}")
                        return direct_video_url




def get_news():
    """
    使用 Whyta 新闻 API 获取国内新闻（含标题、图片和链接）。
    """
    API_KEY = "738b541a5f7a"
    url = f"https://whyta.cn/api/tx/guonei?key={API_KEY}&num=10"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('code') == 200 and data.get('result', {}).get('newslist'):
            news_payload = []
            for item in data['result']['newslist']:
                news_payload.append({
                    "title": item.get('title', '无标题'),
                    "picUrl": item.get('picUrl', ''),
                    "url": item.get('url', '')
                })
            return {"payload": news_payload, "type": "news"}
        else:
            return {"payload": "无法获取新闻信息。", "type": "text"}

    except requests.exceptions.RequestException as e:
        return {"payload": f"新闻服务暂时不可用：请求错误 {str(e)}", "type": "text"}
    except Exception as e:
        return {"payload": f"获取新闻信息时发生未知错误：{str(e)}", "type": "text"}


if __name__ == '__main__':
    init_db()
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
