// King of the CADstle App Logic
const chatContainer = document.getElementById('chat-container');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const directBtn = document.getElementById('directBtn');
const statusDiv = document.getElementById('connectionStatus');

function addMessage(text, type, fileUrl = null, imageUrl = null) {
    const msg = document.createElement('div');
    msg.className = `message ${type}-message`;

    if (text) {
        const textDiv = document.createElement('div');
        textDiv.innerText = text;
        msg.appendChild(textDiv);
    }

    if (imageUrl) {
        const img = document.createElement('img');
        img.src = imageUrl;
        img.style.width = '100%';
        img.style.marginTop = '10px';
        img.style.borderRadius = '4px';
        msg.appendChild(img);
    }

    if (fileUrl) {
        const link = document.createElement('a');
        link.href = fileUrl;
        link.className = 'download-btn';
        link.innerText = '⬇ Download Print-Ready STL';
        link.download = fileUrl.split('/').pop();
        msg.appendChild(link);

        // Auto-load into slicer
        if (window.loadSTL) window.loadSTL(fileUrl);
    }

    chatContainer.appendChild(msg);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    return msg;
}

async function checkHealth() {
    try {
        const res = await fetch('/health');
        const data = await res.json();
        if (data.status === 'healthy') {
            statusDiv.innerText = '👑 KING IS CONNECTED';
            statusDiv.style.color = '#ffcc00';
        } else {
            statusDiv.innerText = '👑 KING IS ISOLATED';
            statusDiv.style.color = '#ff4444';
        }
    } catch (e) {
        statusDiv.innerText = '👑 KINGDOM IS UNREACHABLE';
    }
}

setInterval(checkHealth, 10000);
checkHealth();

async function handleCommand(isDirect = false) {
    const text = userInput.value.trim();
    if (!text) return;

    addMessage(text, 'user');
    userInput.value = '';

    const aiMsg = addMessage('', 'ai');
    aiMsg.innerHTML = '<div style="display: flex; align-items: center; gap: 10px;"><div class="loading"></div> The King is designing...</div>';

    try {
        const endpoint = isDirect ? '/execute' : '/agent';
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: text })
        });
        const result = await response.json();

        aiMsg.innerHTML = ''; // Clear loading
        if (result.status === 'success') {
            addMessage(result.message, 'ai', result.file, result.image);
        } else {
            addMessage('The King encountered an error: ' + result.message, 'ai');
        }
    } catch (error) {
        aiMsg.innerText = 'The Kingdom is in turmoil: ' + error.message;
    }
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

sendBtn.addEventListener('click', () => handleCommand(false));
directBtn.addEventListener('click', () => handleCommand(true));

userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleCommand(false);
    }
});
