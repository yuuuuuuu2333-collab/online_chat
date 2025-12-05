document.addEventListener('DOMContentLoaded', () => {
    // Connect to SocketIO
    const socket = io({ path: '/socket.io' });
    
    const messageInput = document.getElementById('messageInput');
    const sendBtn = document.getElementById('sendBtn');
    const messagesContainer = document.getElementById('messages');
    const userList = document.getElementById('userList');
    const sidebar = document.getElementById('sidebar');
    const menuToggle = document.getElementById('menuToggle');
    const emojiBtn = document.getElementById('emojiBtn');
    const emojiPicker = document.getElementById('emojiPicker');
    const closeSidebarBtn = document.getElementById('closeSidebarBtn');

    // Join room
    socket.emit('join', { nickname: CURRENT_NICKNAME });

    // Socket Events
    socket.on('connect', () => {
        console.log('Connected to server');
    });

    socket.on('user_list', (data) => {
        updateUserList(data.users);
    });

    socket.on('user_joined', (data) => {
        appendSystemMessage(`${data.nickname} joined the room.`);
        updateUserList(data.users);
    });

    socket.on('user_left', (data) => {
        appendSystemMessage(`${data.nickname} left the room.`);
        updateUserList(data.users);
    });

    socket.on('message', (data) => {
        appendMessage(data);
    });

    socket.on('error', (data) => {
        alert(data.message);
        window.location.href = '/';
    });

    // UI Interactions
    sendBtn.addEventListener('click', sendMessage);
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    menuToggle.addEventListener('click', () => {
        sidebar.classList.toggle('active');
    });

    if (closeSidebarBtn) {
        closeSidebarBtn.addEventListener('click', () => {
            sidebar.classList.remove('active');
        });
    }

    // Close sidebar when clicking outside on mobile
    document.addEventListener('click', (e) => {
        if (window.innerWidth <= 768 && 
            !sidebar.contains(e.target) && 
            !menuToggle.contains(e.target) &&
            sidebar.classList.contains('active')) {
            sidebar.classList.remove('active');
        }
    });

    const clearHistoryBtn = document.getElementById('clearHistoryBtn');
    if (clearHistoryBtn) {
        clearHistoryBtn.addEventListener('click', () => {
            if (confirm('Are you sure you want to clear all chat history? This action cannot be undone.')) {
                fetch('/clear_history', { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            alert('Chat history cleared!');
                            messagesContainer.innerHTML = ''; // Clear messages from UI
                        } else {
                            alert('Failed to clear chat history: ' + data.message);
                        }
                    })
                    .catch(error => {
                        console.error('Error clearing history:', error);
                        alert('An error occurred while clearing history.');
                    });
            }
        });
    }

    emojiBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        emojiPicker.style.display = emojiPicker.style.display === 'none' ? 'flex' : 'none';
    });

    emojiPicker.addEventListener('click', (e) => {
        if (e.target.tagName === 'SPAN') {
            messageInput.value += e.target.textContent;
            emojiPicker.style.display = 'none';
            messageInput.focus();
        }
    });

    document.addEventListener('click', (e) => {
        if (!emojiPicker.contains(e.target) && e.target !== emojiBtn) {
            emojiPicker.style.display = 'none';
        }
    });

    // Functions
   function sendMessage() {
    const msg = messageInput.value.trim();
    if (msg) {

        // ① 正常发送聊天消息（保持不动）
        socket.emit('message', { msg });
        messageInput.value = '';

        // ② 🔥 如果需要 AI 回复，则额外通知后端
        if (msg.includes('@川小农')) {
            socket.emit('ai_request', { msg });
        }
    }
}

    function updateUserList(users) {
        userList.innerHTML = '';
        users.forEach(user => {
            const li = document.createElement('li');
            li.innerHTML = `<span class="user-status ${user.is_online ? 'online' : 'offline'}"></span>${user.nickname}`;
            if (user.nickname === CURRENT_NICKNAME) {
                li.classList.add('self');
                li.innerHTML += ' (You)';
            }
            userList.appendChild(li);
        });
    }

    function appendMessage(data) {
        const div = document.createElement('div');
        div.classList.add('message');
        div.classList.add(data.nickname === CURRENT_NICKNAME ? 'own' : 'other');

        const meta = document.createElement('span');
        meta.classList.add('meta');
        meta.textContent = data.nickname;
        if (data.timestamp) {
            const date = new Date(data.timestamp);
            const formatter = new Intl.DateTimeFormat('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false, // Use 24-hour format
                timeZone: 'Asia/Shanghai' // Explicitly set timezone to UTC+8
            });
            const formattedDateTime = formatter.format(date);
            meta.textContent += ` at ${formattedDateTime}`;
        }
        div.appendChild(meta);

        const content = document.createElement('div');
        content.classList.add('message-content');

        if (data.type === 'movie') {
            const iframeContainer = document.createElement('div');
            iframeContainer.classList.add('iframe-container');

            const iframe = document.createElement('iframe');
            iframe.src = data.payload;
            iframe.allowFullscreen = true;
            iframe.frameBorder = '0';
            iframeContainer.appendChild(iframe);
            content.appendChild(iframeContainer);
        } else if (data.type === 'ai') {
            // AI response
            // Convert newlines to <br> for better display
            const formattedPayload = data.payload.replace(/\n/g, '<br>');
            content.innerHTML = `<strong>🤖 川小农:</strong><br>${formattedPayload}`;
        } else if (data.type === 'weather') {
            // Weather response
            const formattedPayload = data.payload.replace(/\n/g, '<br>');
            content.innerHTML = `<strong>☁️ 天气:</strong><br>${formattedPayload}`;
            if (data.weather_type) {
                setWeatherBackground(data.weather_type);
            }
        } else {
            content.textContent = data.payload;
        }

        div.appendChild(content);
        messagesContainer.appendChild(div);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function appendSystemMessage(msg) {
        const div = document.createElement('div');
        div.style.textAlign = 'center';
        div.style.color = '#888';
        div.style.fontSize = '0.8rem';
        div.style.margin = '10px 0';
        div.textContent = msg;
        messagesContainer.appendChild(div);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function setWeatherBackground(weatherType) {
        const body = document.body;
        // Remove any existing weather classes
        body.classList.remove('weather-sunny', 'weather-cloudy', 'weather-rainy', 'weather-snowy');

        switch (weatherType) {
            case '晴天':
                body.classList.add('weather-sunny');
                break;
            case '多云':
            case '阴':
                body.classList.add('weather-cloudy');
                break;
            case '雨':
            case '小雨':
            case '中雨':
            case '大雨':
            case '暴雨':
                body.classList.add('weather-rainy');
                break;
            case '雪':
            case '小雪':
            case '中雪':
            case '大雪':
            case '暴雪':
                body.classList.add('weather-snowy');
                break;
            default:
                // Default background or no specific weather background
                break;
        }
    }
});
