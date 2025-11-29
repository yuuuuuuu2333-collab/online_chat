document.addEventListener('DOMContentLoaded', () => {
    const serverSelect = document.getElementById('server');
    const loginBtn = document.getElementById('loginBtn');
    const nicknameInput = document.getElementById('nickname');
    const errorMsg = document.getElementById('errorMsg');

    // Fetch servers from config
    fetch('/api/servers')
        .then(response => response.json())
        .then(servers => {
            servers.forEach(server => {
                const option = document.createElement('option');
                option.value = server.url;
                option.textContent = server.name;
                serverSelect.appendChild(option);
            });
        })
        .catch(err => {
            console.error('Failed to load servers:', err);
            errorMsg.textContent = 'Failed to load server list.';
            errorMsg.style.display = 'block';
        });

    loginBtn.addEventListener('click', async () => {
        const nickname = nicknameInput.value.trim();
        if (!nickname) {
            showError('Please enter a nickname.');
            return;
        }

        // Check nickname uniqueness
        try {
            const response = await fetch('/api/check_nickname', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ nickname })
            });
            const data = await response.json();

            if (data.valid) {
                // Redirect to chat page with nickname
                window.location.href = `/chat?nickname=${encodeURIComponent(nickname)}`;
            } else {
                showError(data.message);
            }
        } catch (err) {
            console.error('Error checking nickname:', err);
            showError('Network error. Please try again.');
        }
    });

    function showError(msg) {
        errorMsg.textContent = msg;
        errorMsg.style.display = 'block';
    }

    nicknameInput.addEventListener('input', () => {
        errorMsg.style.display = 'none';
    });
});
