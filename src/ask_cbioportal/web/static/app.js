// State
let sessions = {};  // sessionId -> { ws, messages, currentMessageDiv, isStreaming }
let currentSessionId = null;
let chatHistory = [];  // Array of { id, title, timestamp, messages }
let shouldAutoScroll = true;
let selectedModel = localStorage.getItem('selectedModel') || 'GPT-OSS-120B';

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

    // Initialize model selector
    const modelSelect = document.getElementById('model-select');
    if (modelSelect) {
        modelSelect.value = selectedModel;
    }

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

    // Replace chart JSON blocks with loading placeholders during streaming
    // Pass the messageDiv to track loading start time for smooth spinner animation
    const displayContent = hideChartJsonDuringStreaming(messageDiv.rawContent, messageDiv);
    contentDiv.innerHTML = marked.parse(displayContent);
    contentDiv.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
}

// Hide raw chart JSON during streaming and show a loading placeholder instead
// The messageDiv parameter is used to track when loading started for smooth spinner animation
// We hide ALL chart blocks (complete or not) during streaming to prevent JSON flash
function hideChartJsonDuringStreaming(content, messageDiv) {
    // Match chart code blocks - handle both proper formatting (newline before ```)
    // and improper formatting (text directly before ```)
    // This regex matches ```chart followed by content until closing ``` or end of string
    const chartBlockRegex = /```chart\s*\n[\s\S]*?(?:```|$)/g;

    // First, fix improperly formatted chart blocks (no newline before ```)
    // Add a newline before ```chart if there isn't one
    let fixedContent = content.replace(/([^\n])```chart/g, '$1\n\n```chart');

    return fixedContent.replace(chartBlockRegex, (match) => {
        // Check if the block is complete (ends with ```)
        const isComplete = match.endsWith('```');

        // Track when loading started (if not already tracking)
        // This allows us to use a negative animation-delay to keep spinner smooth
        if (messageDiv && !messageDiv.chartLoadingStartTime) {
            messageDiv.chartLoadingStartTime = Date.now();
        }

        // Calculate elapsed time for smooth spinner animation
        // Using negative animation-delay makes the spinner appear continuous
        // even when the DOM element is recreated
        let animationDelay = '0s';
        if (messageDiv && messageDiv.chartLoadingStartTime) {
            const elapsed = (Date.now() - messageDiv.chartLoadingStartTime) / 1000;
            animationDelay = `-${elapsed}s`;
        }

        // Always show loading indicator during streaming - even for complete blocks
        // This prevents the brief flash of raw JSON before the chart renders
        // The actual chart will be rendered in finalizeMessage()
        const loadingText = isComplete ? 'Rendering chart...' : 'Generating chart...';

        return `
<div class="chart-loading" data-chart-complete="${isComplete}">
    <div class="chart-loading-spinner" style="animation-delay: ${animationDelay}"></div>
    <span class="chart-loading-text">${loadingText}</span>
</div>
`;
    });
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
        // Fix improperly formatted chart blocks (no newline before ```)
        const fixedContent = messageDiv.rawContent.replace(/([^\n])```chart/g, '$1\n\n```chart');
        contentDiv.innerHTML = marked.parse(fixedContent);
        contentDiv.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
        renderCharts(contentDiv);
        styleDownloadLinks(contentDiv);
    }
}

// Style download links as buttons
function styleDownloadLinks(container) {
    // Find all links that point to /api/download/
    const downloadLinks = container.querySelectorAll('a[href^="/api/download/"]');

    downloadLinks.forEach(link => {
        // Skip if already styled
        if (link.classList.contains('download-btn')) return;

        // Get the link text and href
        const text = link.textContent;
        const href = link.getAttribute('href');

        // Create a styled download button
        const btn = document.createElement('a');
        btn.href = href;
        btn.className = 'download-btn';
        btn.download = ''; // Trigger download behavior
        btn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            <span>${text.replace(/^📥\s*/, '')}</span>
        `;

        // Replace the original link with the styled button
        link.replaceWith(btn);
    });
}

// Chart rendering with Plotly
function renderCharts(container) {
    // Find code blocks with 'chart' language
    const codeBlocks = container.querySelectorAll('pre code');
    codeBlocks.forEach((block, index) => {
        const isChartByClass = block.className.includes('chart') ||
                               block.className.includes('language-chart');
        const content = block.textContent.trim();
        const looksLikeChartJson = content.startsWith('{') &&
                                    (content.includes('"data"') || content.includes('"type"'));

        if (!isChartByClass && !looksLikeChartJson) return;

        try {
            const chartConfig = JSON.parse(content);
            const pre = block.parentElement;

            // Create wrapper for chart and controls
            const chartWrapper = document.createElement('div');
            chartWrapper.className = 'chart-wrapper';

            // Create chart container with explicit height for Plotly
            const chartContainer = document.createElement('div');
            chartContainer.className = 'chart-container';
            chartContainer.id = `chart-${Date.now()}-${index}`;

            // Create controls (view code button)
            const chartControls = document.createElement('div');
            chartControls.className = 'chart-controls';
            chartControls.innerHTML = `
                <button class="chart-code-btn" onclick="toggleChartCode(this)" title="View/Copy chart data">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="16 18 22 12 16 6"></polyline>
                        <polyline points="8 6 2 12 8 18"></polyline>
                    </svg>
                    <span>View Code</span>
                </button>
            `;

            // Create hidden code block
            const codeBlock = document.createElement('div');
            codeBlock.className = 'chart-code-block hidden';
            codeBlock.innerHTML = `
                <div class="chart-code-header">
                    <span>Chart Configuration (JSON)</span>
                    <button class="copy-code-btn" onclick="copyChartCode(this)" title="Copy to clipboard">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                        </svg>
                        Copy
                    </button>
                </div>
                <pre class="chart-code-content"><code>${escapeHtml(JSON.stringify(chartConfig, null, 2))}</code></pre>
            `;

            chartWrapper.appendChild(chartContainer);
            chartWrapper.appendChild(chartControls);
            chartWrapper.appendChild(codeBlock);

            // Replace code block with chart wrapper
            pre.replaceWith(chartWrapper);

            // Determine chart height based on content
            const hasRotatedLabels = chartConfig.layout?.xaxis?.tickangle &&
                                     Math.abs(chartConfig.layout.xaxis.tickangle) > 0;
            const numLabels = chartConfig.data?.[0]?.x?.length || chartConfig.data?.[0]?.labels?.length || 0;
            const maxLabelLength = Math.max(...(chartConfig.data?.[0]?.x || chartConfig.data?.[0]?.labels || []).map(l => String(l).length), 0);

            // Calculate dynamic bottom margin based on labels
            let bottomMargin = 80;
            if (hasRotatedLabels && numLabels > 0) {
                // Estimate needed space for rotated labels
                bottomMargin = Math.min(180, 80 + maxLabelLength * 4);
            }

            // Calculate dynamic height
            const chartHeight = 380 + (bottomMargin > 80 ? bottomMargin - 80 : 0);

            // Dark theme layout with auto-sizing
            const hasSingleTrace = chartConfig.data && chartConfig.data.length === 1;
            const isPieChart = chartConfig.data?.[0]?.type === 'pie';

            const darkLayout = {
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(0,0,0,0)',
                font: { color: '#ececec', family: '-apple-system, BlinkMacSystemFont, sans-serif', size: 12 },
                margin: { t: 60, r: 40, b: bottomMargin, l: 70 },
                height: chartHeight,
                showlegend: !hasSingleTrace || isPieChart,
                legend: {
                    font: { color: '#ececec', size: 11 },
                    bgcolor: 'rgba(0,0,0,0)'
                },
                // Apply layout from config but ensure our margins take precedence for critical items
                ...chartConfig.layout,
                xaxis: {
                    ...chartConfig.layout?.xaxis,
                    automargin: true,  // Let Plotly auto-adjust margins
                    tickfont: { size: 10 },
                    title: {
                        ...chartConfig.layout?.xaxis?.title,
                        standoff: 20  // Add space between axis and title
                    }
                },
                yaxis: {
                    ...chartConfig.layout?.yaxis,
                    automargin: true,
                    tickfont: { size: 10 }
                },
                title: {
                    ...chartConfig.layout?.title,
                    font: { size: 14, color: '#ececec' },
                    y: 0.95,  // Position title higher
                    yanchor: 'top'
                }
            };

            // Set container height dynamically
            chartContainer.style.height = `${chartHeight + 40}px`;

            const config = {
                responsive: true,
                displayModeBar: 'hover',
                modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
                displaylogo: false,
                modeBarPosition: 'top-right'
            };

            Plotly.newPlot(chartContainer.id, chartConfig.data, darkLayout, config);
        } catch (e) {
            console.error('Failed to render chart:', e);
        }
    });
}

// Toggle chart code visibility
function toggleChartCode(button) {
    const wrapper = button.closest('.chart-wrapper');
    const codeBlock = wrapper.querySelector('.chart-code-block');
    const isHidden = codeBlock.classList.contains('hidden');

    codeBlock.classList.toggle('hidden');
    button.querySelector('span').textContent = isHidden ? 'Hide Code' : 'View Code';
}

// Copy chart code to clipboard
function copyChartCode(button) {
    const codeBlock = button.closest('.chart-code-block');
    const code = codeBlock.querySelector('code').textContent;

    navigator.clipboard.writeText(code).then(() => {
        const originalText = button.innerHTML;
        button.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            Copied!
        `;
        setTimeout(() => {
            button.innerHTML = originalText;
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy:', err);
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
            // Fix improperly formatted chart blocks (no newline before ```)
            const fixedContent = msg.content.replace(/([^\n])```chart/g, '$1\n\n```chart');
            contentDiv.innerHTML = marked.parse(fixedContent);
            contentDiv.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
            renderCharts(contentDiv);
            styleDownloadLinks(contentDiv);
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

    session.ws.send(JSON.stringify({ question: content, model: selectedModel }));
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

// Model selection - saves choice and sends with each message
function changeModel() {
    const select = document.getElementById('model-select');
    selectedModel = select.value;
    localStorage.setItem('selectedModel', selectedModel);
    console.log('Model changed to:', selectedModel);
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
