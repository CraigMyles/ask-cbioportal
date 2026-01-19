// State
let sessions = {};  // sessionId -> { ws, messages, currentMessageDiv, isStreaming }
let currentSessionId = null;
let chatHistory = [];  // Array of { id, title, timestamp, messages }
let shouldAutoScroll = true;

// Elements
const chatContainer = document.getElementById('chat-container');
const messagesDiv = document.getElementById('messages');
const welcomeScreen = document.getElementById('welcome-screen');
const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');
const statusDot = document.getElementById('status-dot');
const connectionStatus = document.getElementById('connection-status');
const chatHistoryDiv = document.getElementById('chat-history');

// Generate UUID
function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadChatHistory();
    setupScrollDetection();

    // Configure marked for markdown rendering
    marked.setOptions({
        highlight: function(code, lang) {
            if (lang && hljs.getLanguage(lang)) {
                return hljs.highlight(code, { language: lang }).value;
            }
            return hljs.highlightAuto(code).value;
        },
        breaks: true,
        gfm: true
    });

    // Start with a new chat if no history
    if (chatHistory.length === 0) {
        newChat();
    } else {
        // Load most recent chat
        loadChat(chatHistory[0].id);
    }
});

// Scroll detection
function setupScrollDetection() {
    chatContainer.addEventListener('scroll', () => {
        const threshold = 100;
        const position = chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight;
        shouldAutoScroll = position < threshold;
    });
}

// Session management
function getSession(sessionId) {
    if (!sessions[sessionId]) {
        sessions[sessionId] = {
            ws: null,
            messages: [],
            currentMessageDiv: null,
            isStreaming: false
        };
    }
    return sessions[sessionId];
}

function getCurrentSession() {
    return currentSessionId ? getSession(currentSessionId) : null;
}

// WebSocket management
function connectWebSocket(sessionId) {
    const session = getSession(sessionId);

    if (session.ws && session.ws.readyState === WebSocket.OPEN) {
        return; // Already connected
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    session.ws = new WebSocket(`${protocol}//${window.location.host}/ws/${sessionId}`);

    session.ws.onopen = () => {
        if (sessionId === currentSessionId) {
            statusDot.className = 'status-dot connected';
            connectionStatus.textContent = 'Connected';
        }
    };

    session.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(sessionId, data);
    };

    session.ws.onclose = () => {
        if (sessionId === currentSessionId) {
            statusDot.className = 'status-dot error';
            connectionStatus.textContent = 'Disconnected';
        }
        // Reconnect after delay
        setTimeout(() => {
            if (sessions[sessionId]) {
                connectWebSocket(sessionId);
            }
        }, 2000);
    };

    session.ws.onerror = () => {
        if (sessionId === currentSessionId) {
            statusDot.className = 'status-dot error';
            connectionStatus.textContent = 'Error';
        }
    };
}

function handleWebSocketMessage(sessionId, data) {
    const session = getSession(sessionId);
    const isCurrentSession = sessionId === currentSessionId;

    if (data.type === 'chunk') {
        if (!session.currentMessageDiv && isCurrentSession) {
            session.currentMessageDiv = addMessageToUI('', 'assistant');
        }
        // Store in session messages
        if (!session.pendingContent) session.pendingContent = '';
        session.pendingContent += data.content;

        if (isCurrentSession && session.currentMessageDiv) {
            appendToMessage(session.currentMessageDiv, data.content);
        }
    } else if (data.type === 'tool_call') {
        if (!session.currentMessageDiv && isCurrentSession) {
            session.currentMessageDiv = addMessageToUI('', 'assistant');
        }
        if (isCurrentSession && session.currentMessageDiv) {
            showToolCall(session.currentMessageDiv, data.name);
        }
    } else if (data.type === 'done') {
        // Save the complete message
        if (session.pendingContent) {
            session.messages.push({ role: 'assistant', content: session.pendingContent });
            session.pendingContent = '';
        }

        if (isCurrentSession && session.currentMessageDiv) {
            finalizeMessage(session.currentMessageDiv);
        }
        session.currentMessageDiv = null;
        session.isStreaming = false;

        if (isCurrentSession) {
            updateSendButton();
        }

        // Update sidebar to remove streaming indicator
        renderChatHistory();
        saveCurrentChat();
    } else if (data.type === 'error') {
        const errorMsg = `**Error:** ${data.content}`;
        if (session.pendingContent) {
            session.pendingContent += '\n\n' + errorMsg;
        } else {
            session.pendingContent = errorMsg;
        }

        if (isCurrentSession && session.currentMessageDiv) {
            appendToMessage(session.currentMessageDiv, '\n\n' + errorMsg);
            finalizeMessage(session.currentMessageDiv);
        }
        session.currentMessageDiv = null;
        session.isStreaming = false;

        if (isCurrentSession) {
            updateSendButton();
        }

        // Update sidebar to remove streaming indicator
        renderChatHistory();
    } else if (data.type === 'cleared') {
        session.messages = [];
        console.log('Session cleared:', sessionId);
    }

    if (isCurrentSession && shouldAutoScroll) {
        scrollToBottom();
    }
}

// UI Message handling
function addMessageToUI(content, role) {
    welcomeScreen.classList.add('hidden');

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    const avatarText = role === 'user' ? 'Y' : 'A';

    messageDiv.innerHTML = `
        <div class="message-inner">
            <div class="message-avatar">${avatarText}</div>
            <div class="message-content">${role === 'user' ? escapeHtml(content) : ''}</div>
        </div>
    `;

    messagesDiv.appendChild(messageDiv);

    if (role === 'assistant' && !content) {
        const contentDiv = messageDiv.querySelector('.message-content');
        contentDiv.innerHTML = `
            <div class="typing-indicator">
                <span></span><span></span><span></span>
            </div>
        `;
    }

    return messageDiv;
}

function appendToMessage(messageDiv, content) {
    const contentDiv = messageDiv.querySelector('.message-content');

    const typingIndicator = contentDiv.querySelector('.typing-indicator');
    if (typingIndicator) typingIndicator.remove();

    const toolCalls = contentDiv.querySelectorAll('.tool-call');
    toolCalls.forEach(tc => tc.remove());

    if (!messageDiv.rawContent) messageDiv.rawContent = '';
    messageDiv.rawContent += content;

    contentDiv.innerHTML = marked.parse(messageDiv.rawContent);
    contentDiv.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
}

function showToolCall(messageDiv, toolName) {
    const contentDiv = messageDiv.querySelector('.message-content');

    const typingIndicator = contentDiv.querySelector('.typing-indicator');
    if (typingIndicator) typingIndicator.remove();

    const existingToolCalls = contentDiv.querySelectorAll('.tool-call');
    existingToolCalls.forEach(tc => tc.remove());

    const toolCallDiv = document.createElement('div');
    toolCallDiv.className = 'tool-call';
    toolCallDiv.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
        </svg>
        Calling ${toolName}...
    `;
    contentDiv.appendChild(toolCallDiv);
}

function finalizeMessage(messageDiv) {
    const contentDiv = messageDiv.querySelector('.message-content');

    const toolCalls = contentDiv.querySelectorAll('.tool-call');
    toolCalls.forEach(tc => tc.remove());

    const typingIndicator = contentDiv.querySelector('.typing-indicator');
    if (typingIndicator) typingIndicator.remove();

    if (messageDiv.rawContent) {
        contentDiv.innerHTML = marked.parse(messageDiv.rawContent);
        contentDiv.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
        renderCharts(contentDiv);
    }
}

// Chart rendering
function renderCharts(container) {
    // Find code blocks with 'chart' language
    const codeBlocks = container.querySelectorAll('pre code.language-chart');
    codeBlocks.forEach((block, index) => {
        try {
            const chartConfig = JSON.parse(block.textContent);
            const pre = block.parentElement;

            // Create chart container
            const chartContainer = document.createElement('div');
            chartContainer.className = 'chart-container';
            chartContainer.style.cssText = 'max-width: 500px; margin: 16px 0; background: var(--bg-secondary); padding: 16px; border-radius: 8px;';

            const canvas = document.createElement('canvas');
            canvas.id = `chart-${Date.now()}-${index}`;
            chartContainer.appendChild(canvas);

            // Replace code block with chart
            pre.replaceWith(chartContainer);

            // Apply dark theme defaults
            const config = {
                ...chartConfig,
                options: {
                    ...chartConfig.options,
                    responsive: true,
                    plugins: {
                        ...chartConfig.options?.plugins,
                        legend: {
                            ...chartConfig.options?.plugins?.legend,
                            labels: {
                                color: '#ececec',
                                ...chartConfig.options?.plugins?.legend?.labels
                            }
                        },
                        title: {
                            ...chartConfig.options?.plugins?.title,
                            color: '#ececec'
                        }
                    },
                    scales: chartConfig.type === 'pie' || chartConfig.type === 'doughnut' ? undefined : {
                        x: {
                            ticks: { color: '#b4b4b4' },
                            grid: { color: '#3a3a3a' },
                            ...chartConfig.options?.scales?.x
                        },
                        y: {
                            ticks: { color: '#b4b4b4' },
                            grid: { color: '#3a3a3a' },
                            ...chartConfig.options?.scales?.y
                        }
                    }
                }
            };

            new Chart(canvas, config);
        } catch (e) {
            console.error('Failed to render chart:', e);
        }
    });
}

function renderMessages(messages) {
    messagesDiv.innerHTML = '';

    if (messages.length === 0) {
        welcomeScreen.classList.remove('hidden');
        return;
    }

    welcomeScreen.classList.add('hidden');

    messages.forEach(msg => {
        const messageDiv = addMessageToUI(msg.content, msg.role);
        if (msg.role === 'assistant') {
            messageDiv.rawContent = msg.content;
            const contentDiv = messageDiv.querySelector('.message-content');
            contentDiv.innerHTML = marked.parse(msg.content);
            contentDiv.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
            renderCharts(contentDiv);
        }
    });

    scrollToBottom();
}

// Send message
function sendMessage() {
    const session = getCurrentSession();
    if (!session) return;

    const content = messageInput.value.trim();
    if (!content || session.isStreaming || !session.ws || session.ws.readyState !== WebSocket.OPEN) return;

    // Add to UI and session
    addMessageToUI(content, 'user');
    session.messages.push({ role: 'user', content: content });

    messageInput.value = '';
    autoResize(messageInput);

    session.isStreaming = true;
    shouldAutoScroll = true;
    updateSendButton();
    renderChatHistory();  // Show streaming indicator in sidebar

    session.ws.send(JSON.stringify({ question: content }));
    scrollToBottom();

    // Update chat title if this is the first message
    updateChatTitle();
}

function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
}

function updateSendButton() {
    const session = getCurrentSession();
    sendBtn.disabled = session ? session.isStreaming : true;
}

// Prompts
function usePrompt(button) {
    const text = button.querySelector('.prompt-text').textContent;
    messageInput.value = text;
    autoResize(messageInput);
    messageInput.focus();
}

// Chat management
function newChat() {
    // Save current chat first
    saveCurrentChat();

    // Create new session
    const sessionId = generateUUID();
    currentSessionId = sessionId;

    // Initialize session
    const session = getSession(sessionId);
    session.messages = [];

    // Add to history
    const chatData = {
        id: sessionId,
        title: 'New Chat',
        timestamp: Date.now(),
        messages: []
    };
    chatHistory.unshift(chatData);

    // Connect WebSocket
    connectWebSocket(sessionId);

    // Clear UI
    messagesDiv.innerHTML = '';
    welcomeScreen.classList.remove('hidden');
    messageInput.value = '';
    messageInput.focus();

    updateSendButton();
    renderChatHistory();
    saveChatHistoryToStorage();
}

function loadChat(chatId) {
    // Save current chat first
    saveCurrentChat();

    // Find chat in history
    const chat = chatHistory.find(c => c.id === chatId);
    if (!chat) {
        console.error('Chat not found:', chatId);
        return;
    }

    currentSessionId = chatId;

    // Restore session
    const session = getSession(chatId);
    // Only restore messages from storage if session doesn't have them already
    // (session.messages might have more recent data if streaming was happening)
    if (session.messages.length === 0 && chat.messages && chat.messages.length > 0) {
        session.messages = chat.messages;
    }

    // Connect WebSocket if needed
    connectWebSocket(chatId);

    // Render completed messages
    renderMessages(session.messages);

    // If this session is still streaming, recreate the streaming message UI
    if (session.isStreaming && session.pendingContent) {
        // Create a new message div for the streaming content
        session.currentMessageDiv = addMessageToUI('', 'assistant');
        session.currentMessageDiv.rawContent = session.pendingContent;
        const contentDiv = session.currentMessageDiv.querySelector('.message-content');
        contentDiv.innerHTML = marked.parse(session.pendingContent);
        contentDiv.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
        scrollToBottom();
    } else if (session.isStreaming) {
        // Streaming but no content yet - show typing indicator
        session.currentMessageDiv = addMessageToUI('', 'assistant');
    }

    // Update UI
    updateSendButton();
    renderChatHistory();
}

function saveCurrentChat() {
    if (!currentSessionId) return;

    const session = getSession(currentSessionId);
    const chatIndex = chatHistory.findIndex(c => c.id === currentSessionId);

    if (chatIndex >= 0) {
        chatHistory[chatIndex].messages = session.messages;
        chatHistory[chatIndex].timestamp = Date.now();
    }

    saveChatHistoryToStorage();
}

function updateChatTitle() {
    const session = getCurrentSession();
    if (!session || session.messages.length === 0) return;

    const firstUserMessage = session.messages.find(m => m.role === 'user');
    if (!firstUserMessage) return;

    const chatIndex = chatHistory.findIndex(c => c.id === currentSessionId);
    if (chatIndex >= 0) {
        const title = firstUserMessage.content.substring(0, 40);
        chatHistory[chatIndex].title = title + (title.length >= 40 ? '...' : '');
        renderChatHistory();
    }
}

function deleteChat(chatId, event) {
    event.stopPropagation();

    // Remove from history
    chatHistory = chatHistory.filter(c => c.id !== chatId);

    // Close WebSocket if exists
    if (sessions[chatId] && sessions[chatId].ws) {
        sessions[chatId].ws.close();
    }
    delete sessions[chatId];

    // If deleting current chat, switch to another or create new
    if (chatId === currentSessionId) {
        if (chatHistory.length > 0) {
            loadChat(chatHistory[0].id);
        } else {
            newChat();
        }
    }

    renderChatHistory();
    saveChatHistoryToStorage();
}

// Chat history persistence
function loadChatHistory() {
    try {
        const saved = localStorage.getItem('askCbioportalChats');
        if (saved) {
            chatHistory = JSON.parse(saved);
            renderChatHistory();
        }
    } catch (e) {
        console.error('Failed to load chat history:', e);
        chatHistory = [];
    }
}

function saveChatHistoryToStorage() {
    try {
        // Keep only last 50 chats
        chatHistory = chatHistory.slice(0, 50);
        localStorage.setItem('askCbioportalChats', JSON.stringify(chatHistory));
    } catch (e) {
        console.error('Failed to save chat history:', e);
    }
}

function renderChatHistory() {
    chatHistoryDiv.innerHTML = chatHistory.map(chat => {
        const session = sessions[chat.id];
        const isStreaming = session && session.isStreaming;
        return `
        <div class="chat-history-item ${chat.id === currentSessionId ? 'active' : ''} ${isStreaming ? 'streaming' : ''}"
             onclick="loadChat('${chat.id}')"
             title="${escapeHtml(chat.title)}">
            ${isStreaming ? '<span class="streaming-indicator"></span>' : ''}
            <span class="chat-title">${escapeHtml(chat.title)}</span>
            <button class="delete-chat-btn" onclick="deleteChat('${chat.id}', event)" title="Delete chat">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M18 6L6 18M6 6l12 12"/>
                </svg>
            </button>
        </div>
    `}).join('');
}

// Model selection (placeholder for future implementation)
function changeModel() {
    const select = document.getElementById('model-select');
    const model = select.value;
    console.log('Model changed to:', model);
    // Would need backend support to actually change models mid-session
}

// Utilities
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}
