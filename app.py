import json
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
import os
import sqlite3
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup
import re

# Define the UTC+8 timezone
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
            nickname TEXT UNIQUE NOT NULL
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

client = True
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
    nickname = request.args.get('nickname')
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

@app.route('/api/history')
def get_history():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nickname, message, type, timestamp FROM messages ORDER BY timestamp ASC LIMIT 100") # Get last 100 messages
    history = cursor.fetchall()
    conn.close()
    return jsonify([dict(row) for row in history])

@app.route('/clear_history', methods=['POST'])
def clear_history():
    try:
        if os.path.exists(DATABASE):
            os.remove(DATABASE)
        init_db() # Re-initialize the database after clearing
        return jsonify({'success': True, 'message': 'Chat history cleared and database re-initialized.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    nickname = online_users.pop(request.sid, None)
    if nickname:
        emit('user_left', {'nickname': nickname, 'users': list(online_users.values())}, broadcast=True)
        print(f'User {nickname} disconnected')

@socketio.on('join')
def handle_join(data):
    nickname = data.get('nickname')
    if not nickname:
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if nickname is already in the persistent users table
    cursor.execute("SELECT * FROM users WHERE nickname = ?", (nickname,))
    existing_user_db = cursor.fetchone()

    # Check if nickname is already in the current online users (in-memory)
    if nickname in online_users.values():
        emit('error', {'message': 'Nickname already taken by an active user'})
        conn.close()
        return

    # If not online, check if it exists in the persistent users table
    cursor.execute("SELECT * FROM users WHERE nickname = ?", (nickname,))
    existing_user_db = cursor.fetchone()

    if not existing_user_db:
        # Add user to persistent storage if not already there
        cursor.execute("INSERT INTO users (nickname) VALUES (?)", (nickname,))
        conn.commit()
    conn.close()

    online_users[request.sid] = nickname
    join_room('chat_room')
    
    emit('user_joined', {
        'nickname': nickname, 
        'users': list(online_users.values())
    }, broadcast=True)
    
    # Send current user list to the new user
    emit('user_list', {'users': list(online_users.values())})

    # Send chat history to the new user
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nickname, message, type, timestamp FROM messages ORDER BY timestamp ASC LIMIT 100")
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
    if not msg or not nickname:
        return

    original_msg_content = msg
    msg_type = 'text'
    payload = msg

    def is_url(text):
        return text.startswith('http://') or text.startswith('https://')

    # ----------------------
    # 电影消息
    # ----------------------
    if msg.startswith('@电影'):
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
        'payload': payload if msg_type == 'movie' else original_msg_content,
        'original_msg': original_msg_content,
        'timestamp': datetime.now(JST).isoformat()
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



def get_movie_resource_url(movie_name):
    base_url = "https://www.libvio.link"
    search_query = movie_name.replace(' ', '+')
    search_url = f"{base_url}/search/?wd={search_query}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
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



if __name__ == '__main__':
    init_db()
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
