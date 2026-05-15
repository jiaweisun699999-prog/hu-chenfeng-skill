const chatMessages = document.getElementById('chatMessages');
const chatForm = document.getElementById('chatForm');
const messageInput = document.getElementById('messageInput');

let messages = [];

function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function appendUserMessage(content) {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message user-message glass-message';
    msgDiv.innerHTML = `<div class="message-content">${content}</div>`;
    chatMessages.appendChild(msgDiv);
    scrollToBottom();
    
    messages.push({ role: 'user', content: content });
}

function appendAssistantMessagePlaceholder() {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message assistant-message glass-message';
    msgDiv.id = 'current-assistant-msg';
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content typing-container';
    
    // Initial typing indicator
    contentDiv.innerHTML = `
        <div class="typing-indicator">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        </div>
    `;
    
    msgDiv.appendChild(contentDiv);
    chatMessages.appendChild(msgDiv);
    scrollToBottom();
    
    return msgDiv;
}

chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const content = messageInput.value.trim();
    if (!content) return;
    
    messageInput.value = '';
    messageInput.disabled = true;
    
    appendUserMessage(content);
    
    const assistantMsgDiv = appendAssistantMessagePlaceholder();
    const contentContainer = assistantMsgDiv.querySelector('.message-content');
    
    let fullResponse = "";
    
    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ messages: messages })
        });
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let isFirstChunk = true;
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const dataStr = line.substring(6);
                    if (dataStr === '[DONE]') break;
                    
                    try {
                        const data = JSON.parse(dataStr);
                        if (data.content) {
                            if (isFirstChunk) {
                                contentContainer.innerHTML = '';
                                isFirstChunk = false;
                            }
                            fullResponse += data.content;
                            // Basic markdown rendering to keep line breaks
                            const renderedHTML = marked.parse(fullResponse);
                            contentContainer.innerHTML = renderedHTML;
                            scrollToBottom();
                        } else if (data.error) {
                            contentContainer.innerHTML = `<span style="color: #ef4444;">Error: ${data.error}</span>`;
                        }
                    } catch (err) {
                        console.error('JSON parse error:', err);
                    }
                }
            }
        }
        
        messages.push({ role: 'assistant', content: fullResponse });
        
    } catch (error) {
        contentContainer.innerHTML = `<span style="color: #ef4444;">网络连接失败。请确保后端服务正常运行。</span>`;
        console.error(error);
    } finally {
        messageInput.disabled = false;
        messageInput.focus();
        scrollToBottom();
    }
});
