document.addEventListener('DOMContentLoaded', function() {
    const nicknameInput = document.getElementById('nickname');
    const passwordInput = document.getElementById('password');
    const confirmPasswordInput = document.getElementById('confirm-password');
    const serverSelect = document.getElementById('server');
    const loginBtn = document.getElementById('loginBtn');
    const registerBtn = document.getElementById('registerBtn');
    const errorMsg = document.getElementById('errorMsg');
    const showRegisterLink = document.getElementById('showRegister');
    const showLoginLink = document.getElementById('showLogin');
    const passwordGroup = document.getElementById('password-group');
    const confirmPasswordGroup = document.getElementById('confirm-password-group');

    let isRegisterMode = false;

    // Fetch servers and populate dropdown
    fetch('/api/servers')
        .then(response => response.json())
        .then(servers => {
            serverSelect.innerHTML = ''; // Clear existing options
            servers.forEach(server => {
                const option = document.createElement('option');
                option.value = server.url;
                option.textContent = server.name;
                serverSelect.appendChild(option);
            });
        })
        .catch(error => {
            console.error('Error fetching servers:', error);
            errorMsg.textContent = 'Failed to load server list.';
        });

    function showErrorMessage(message) {
        errorMsg.textContent = message;
        errorMsg.style.display = 'block';
    }

    function hideErrorMessage() {
        errorMsg.textContent = '';
        errorMsg.style.display = 'none';
    }

    function toggleFormMode(mode) {
        isRegisterMode = mode === 'register';
        if (isRegisterMode) {
            loginBtn.style.display = 'none';
            registerBtn.style.display = 'block';
            confirmPasswordGroup.style.display = 'block';
            showRegisterLink.parentElement.style.display = 'none';
            showLoginLink.parentElement.style.display = 'block';
        } else {
            loginBtn.style.display = 'block';
            registerBtn.style.display = 'none';
            confirmPasswordGroup.style.display = 'none';
            showRegisterLink.parentElement.style.display = 'block';
            showLoginLink.parentElement.style.display = 'none';
        }
        hideErrorMessage();
    }

    showRegisterLink.addEventListener('click', (e) => {
        e.preventDefault();
        toggleFormMode('register');
    });

    showLoginLink.addEventListener('click', (e) => {
        e.preventDefault();
        toggleFormMode('login');
    });

    loginBtn.addEventListener('click', function() {
        const nickname = nicknameInput.value.trim();
        const password = passwordInput.value;

        if (!nickname || !password) {
            showErrorMessage('Nickname and password are required.');
            return;
        }

        hideErrorMessage();

        fetch('/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ nickname: nickname, password: password })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Redirect to chat page with nickname
                window.location.href = '/chat';
            } else {
                showErrorMessage(data.message);
            }
        })
        .catch(error => {
            console.error('Login error:', error);
            showErrorMessage('An error occurred during login. Please try again.');
        });
    });

    registerBtn.addEventListener('click', function() {
        const nickname = nicknameInput.value.trim();
        const password = passwordInput.value;
        const confirmPassword = confirmPasswordInput.value;

        if (!nickname || !password || !confirmPassword) {
            showErrorMessage('All fields are required for registration.');
            return;
        }

        if (password.length < 6) {
            showErrorMessage('Password must be at least 6 characters long.');
            return;
        }

        if (password !== confirmPassword) {
            showErrorMessage('Passwords do not match.');
            return;
        }

        hideErrorMessage();

        fetch('/register', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ nickname: nickname, password: password })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showErrorMessage('Registration successful! You can now log in.');
                toggleFormMode('login'); // Switch to login mode after successful registration
            } else {
                showErrorMessage(data.message);
            }
        })
        .catch(error => {
            console.error('Registration error:', error);
            showErrorMessage('An error occurred during registration. Please try again.');
        });
    });

    // Initial state: show login form
    toggleFormMode('login');
});
