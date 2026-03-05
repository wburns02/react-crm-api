(function() {
  'use strict';

  var API_BASE = window.MAC_CHAT_API || 'https://react-crm-api-production.up.railway.app';
  var STORAGE_KEY = 'mac_chat_conversation_id';
  var STORAGE_VISITOR_KEY = 'mac_chat_visitor_name';
  var POLL_INTERVAL = 3000;
  var BRAND_COLOR = '#16a34a';
  var BRAND_DARK = '#15803d';
  var FONT_STACK = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';

  // Base64 notification sound (short beep)
  var NOTIFICATION_SOUND = 'data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YVoGAACAgoSDhYaIiYuMjo+RkpSVl5iamZubnJycnJybm5qamZiXlpSTkZCOjYuKiIeGhIOCgYB/fn18e3p6eXl5eXl5ent7fH1+f4GCg4WGiImLjI6PkZKUlZeYmpudnp+goaGioqKioaGgnp2cm5mYlpWTkY+OjIuJiIaFg4KBf359fHt6eXl4eHh4eXl6e3x9fn+BgoOFhoiJi42Oj5GTlJaXmZqcnZ6foKChoaKioqGhoJ+enZuamJeVlJKQj42Mi4mIhoWDgoF/fn18e3p5eXh4eHh4eXl6e3x9f3+BgoSFhoiJi42Oj5GTlJaYmZqcnZ6foKChoaKioqGhoJ+enZuamJeVlJKQj42Mi4mHhoWDgoF/fn18e3p5eXh4eHh5eXp7fH1+f4GCg4WGiImLjI6PkZKUlZeYmpucnZ6foKChoqKioqKhoJ+enZuamJeVk5KQj42Mi4mIhoWDgoB/fn18e3p5eXh4eHh5eXp7fH1+f4GCg4WGiImLjI6PkZKUlZeYmpucnZ6foKGhoqKioqGhoJ+enZybmZiWlZOSkI+NjIuJiIaFg4KBf359fHt6eXl4eHl5eXp7e3x9fn+BgoOFhoiJi4yOj5GSlJWXmJqbnJ2en5+goaGioqKioaGgn56dnJuZmJaVk5KQj42MiomIhoWEgoGAf359fHt6eXl5eXl5enp7fH1+f4CBgoSFh4iKi42Oj5GSlJWXmJqbnJ2enp+goKGhoaGhoaCfnp2cm5qYl5aUk5GQjo2LiomHhoWEgoGAf359fHt6enl5eXl5enp7fH1+f4CBg4SFh4iKi4yOj5CSkpSVl5iZmpucnZ6en5+goKChoaGhoKCfnp2cm5qZl5aVk5KQj42MiomIh4WEg4KBgH9+fXx7enp5eXl5eXp6e3x9fn9/gYKDhYaHiYqLjY6PkZKTlZaXmZqbnJ2dnp+fn6CgoKGhoaGgn5+enZ2bmpkA';

  var state = {
    open: false,
    conversationId: localStorage.getItem(STORAGE_KEY),
    visitorName: localStorage.getItem(STORAGE_VISITOR_KEY) || '',
    messages: [],
    lastMessageTs: null,
    pollTimer: null,
    unreadCount: 0,
    connected: true
  };

  // Inject CSS
  var style = document.createElement('style');
  style.textContent = [
    '.mac-chat-widget *,.mac-chat-widget *::before,.mac-chat-widget *::after{box-sizing:border-box;margin:0;padding:0;}',
    '.mac-chat-widget{font-family:' + FONT_STACK + ';font-size:14px;line-height:1.4;position:fixed;bottom:20px;right:20px;z-index:999999;}',
    '.mac-chat-bubble{width:60px;height:60px;border-radius:50%;background:' + BRAND_COLOR + ';color:#fff;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:28px;box-shadow:0 4px 12px rgba(0,0,0,0.25);transition:transform 0.2s,box-shadow 0.2s;position:relative;}',
    '.mac-chat-bubble:hover{transform:scale(1.08);box-shadow:0 6px 18px rgba(0,0,0,0.3);}',
    '.mac-chat-badge{position:absolute;top:-4px;right:-4px;background:#ef4444;color:#fff;border-radius:50%;width:22px;height:22px;font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center;border:2px solid #fff;display:none;}',
    '.mac-chat-badge.mac-chat-visible{display:flex;}',
    '.mac-chat-window{display:none;flex-direction:column;width:380px;height:500px;background:#fff;border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,0.2);overflow:hidden;position:absolute;bottom:72px;right:0;opacity:0;transform:translateY(10px) scale(0.95);transition:opacity 0.25s ease,transform 0.25s ease;}',
    '.mac-chat-window.mac-chat-open{display:flex;opacity:1;transform:translateY(0) scale(1);}',
    '.mac-chat-header{background:' + BRAND_COLOR + ';color:#fff;padding:14px 16px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;}',
    '.mac-chat-header-title{font-size:15px;font-weight:600;}',
    '.mac-chat-header-status{font-size:11px;opacity:0.85;margin-top:2px;}',
    '.mac-chat-close{background:none;border:none;color:#fff;font-size:22px;cursor:pointer;padding:0 4px;line-height:1;opacity:0.8;transition:opacity 0.15s;}',
    '.mac-chat-close:hover{opacity:1;}',
    '.mac-chat-body{flex:1;overflow-y:auto;padding:16px;background:#f9fafb;display:flex;flex-direction:column;gap:8px;}',
    '.mac-chat-msg{max-width:80%;padding:10px 14px;border-radius:16px;font-size:13px;line-height:1.45;word-wrap:break-word;position:relative;}',
    '.mac-chat-msg-visitor{align-self:flex-end;background:' + BRAND_COLOR + ';color:#fff;border-bottom-right-radius:4px;}',
    '.mac-chat-msg-agent{align-self:flex-start;background:#e5e7eb;color:#1f2937;border-bottom-left-radius:4px;}',
    '.mac-chat-msg-system{align-self:center;background:transparent;color:#9ca3af;font-size:12px;font-style:italic;text-align:center;padding:4px 8px;}',
    '.mac-chat-msg-time{font-size:10px;opacity:0.6;margin-top:4px;display:block;}',
    '.mac-chat-msg-visitor .mac-chat-msg-time{text-align:right;}',
    '.mac-chat-msg-agent .mac-chat-msg-time{text-align:left;}',
    '.mac-chat-typing{align-self:flex-start;color:#9ca3af;font-size:12px;font-style:italic;padding:4px 0;}',
    '.mac-chat-footer{display:flex;border-top:1px solid #e5e7eb;background:#fff;padding:8px;gap:8px;flex-shrink:0;}',
    '.mac-chat-input{flex:1;border:1px solid #d1d5db;border-radius:20px;padding:8px 14px;font-size:13px;font-family:' + FONT_STACK + ';outline:none;resize:none;max-height:80px;transition:border-color 0.15s;}',
    '.mac-chat-input:focus{border-color:' + BRAND_COLOR + ';}',
    '.mac-chat-input::placeholder{color:#9ca3af;}',
    '.mac-chat-send{width:36px;height:36px;border-radius:50%;background:' + BRAND_COLOR + ';color:#fff;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0;transition:background 0.15s;}',
    '.mac-chat-send:hover{background:' + BRAND_DARK + ';}',
    '.mac-chat-send:disabled{background:#d1d5db;cursor:not-allowed;}',
    '.mac-chat-form{padding:24px;display:flex;flex-direction:column;gap:14px;flex:1;overflow-y:auto;background:#f9fafb;}',
    '.mac-chat-form-title{font-size:16px;font-weight:600;color:#1f2937;text-align:center;margin-bottom:4px;}',
    '.mac-chat-form-subtitle{font-size:13px;color:#6b7280;text-align:center;margin-bottom:8px;}',
    '.mac-chat-form label{font-size:12px;font-weight:600;color:#374151;display:block;margin-bottom:4px;}',
    '.mac-chat-form-field{display:flex;flex-direction:column;}',
    '.mac-chat-form input{border:1px solid #d1d5db;border-radius:8px;padding:10px 12px;font-size:13px;font-family:' + FONT_STACK + ';outline:none;transition:border-color 0.15s;}',
    '.mac-chat-form input:focus{border-color:' + BRAND_COLOR + ';}',
    '.mac-chat-form-btn{background:' + BRAND_COLOR + ';color:#fff;border:none;border-radius:8px;padding:12px;font-size:14px;font-weight:600;cursor:pointer;font-family:' + FONT_STACK + ';transition:background 0.15s;}',
    '.mac-chat-form-btn:hover{background:' + BRAND_DARK + ';}',
    '.mac-chat-form-btn:disabled{background:#d1d5db;cursor:not-allowed;}',
    '.mac-chat-error{color:#ef4444;font-size:12px;text-align:center;padding:4px;}',
    '.mac-chat-conn-status{text-align:center;padding:6px;font-size:11px;color:#f59e0b;background:#fffbeb;border-bottom:1px solid #fef3c7;display:none;}',
    '.mac-chat-conn-status.mac-chat-visible{display:block;}',
    '@media (max-width:480px){',
    '  .mac-chat-window.mac-chat-open{width:100vw;height:100vh;bottom:0;right:0;border-radius:0;position:fixed;top:0;left:0;}',
    '  .mac-chat-widget .mac-chat-bubble{bottom:10px;right:10px;}',
    '}'
  ].join('\n');
  document.head.appendChild(style);

  // Build DOM
  var widget = document.createElement('div');
  widget.className = 'mac-chat-widget';
  widget.innerHTML = [
    '<button class="mac-chat-bubble" aria-label="Open chat">',
    '  <span style="margin-top:-2px">&#x1F4AC;</span>',
    '  <span class="mac-chat-badge">0</span>',
    '</button>',
    '<div class="mac-chat-window">',
    '  <div class="mac-chat-header">',
    '    <div>',
    '      <div class="mac-chat-header-title">MAC Septic - Live Chat</div>',
    '      <div class="mac-chat-header-status">We typically reply within minutes</div>',
    '    </div>',
    '    <button class="mac-chat-close" aria-label="Close chat">&times;</button>',
    '  </div>',
    '  <div class="mac-chat-conn-status">Connection error, retrying...</div>',
    '  <div class="mac-chat-form" id="mac-chat-start-form">',
    '    <div class="mac-chat-form-title">Start a Conversation</div>',
    '    <div class="mac-chat-form-subtitle">We\'re here to help with all your septic needs.</div>',
    '    <div class="mac-chat-form-field">',
    '      <label for="mac-chat-name">Name *</label>',
    '      <input type="text" id="mac-chat-name" placeholder="Your name" required>',
    '    </div>',
    '    <div class="mac-chat-form-field">',
    '      <label for="mac-chat-email">Email</label>',
    '      <input type="email" id="mac-chat-email" placeholder="you@example.com">',
    '    </div>',
    '    <div class="mac-chat-form-field">',
    '      <label for="mac-chat-phone">Phone</label>',
    '      <input type="tel" id="mac-chat-phone" placeholder="(555) 123-4567">',
    '    </div>',
    '    <div class="mac-chat-error" id="mac-chat-form-error"></div>',
    '    <button class="mac-chat-form-btn" id="mac-chat-start-btn">Start Chat</button>',
    '  </div>',
    '  <div class="mac-chat-body" id="mac-chat-messages" style="display:none;"></div>',
    '  <div class="mac-chat-footer" id="mac-chat-footer" style="display:none;">',
    '    <input class="mac-chat-input" id="mac-chat-msg-input" placeholder="Type a message..." maxlength="2000">',
    '    <button class="mac-chat-send" id="mac-chat-send-btn" aria-label="Send">&#x27A4;</button>',
    '  </div>',
    '</div>'
  ].join('\n');
  document.body.appendChild(widget);

  // References
  var bubble = widget.querySelector('.mac-chat-bubble');
  var badge = widget.querySelector('.mac-chat-badge');
  var chatWindow = widget.querySelector('.mac-chat-window');
  var closeBtn = widget.querySelector('.mac-chat-close');
  var startForm = widget.querySelector('#mac-chat-start-form');
  var messagesArea = widget.querySelector('#mac-chat-messages');
  var footer = widget.querySelector('#mac-chat-footer');
  var msgInput = widget.querySelector('#mac-chat-msg-input');
  var sendBtn = widget.querySelector('#mac-chat-send-btn');
  var startBtn = widget.querySelector('#mac-chat-start-btn');
  var nameInput = widget.querySelector('#mac-chat-name');
  var emailInput = widget.querySelector('#mac-chat-email');
  var phoneInput = widget.querySelector('#mac-chat-phone');
  var formError = widget.querySelector('#mac-chat-form-error');
  var connStatus = widget.querySelector('.mac-chat-conn-status');

  // Audio
  var notifAudio = new Audio(NOTIFICATION_SOUND);

  function playNotification() {
    try { notifAudio.play().catch(function() {}); } catch(e) {}
  }

  // API helpers
  function apiCall(method, path, body) {
    var opts = {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      credentials: 'omit'
    };
    if (body) opts.body = JSON.stringify(body);
    return fetch(API_BASE + path, opts).then(function(res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      state.connected = true;
      connStatus.classList.remove('mac-chat-visible');
      return res.json();
    }).catch(function(err) {
      state.connected = false;
      connStatus.classList.add('mac-chat-visible');
      throw err;
    });
  }

  function formatTime(ts) {
    if (!ts) return '';
    var d = new Date(ts);
    if (isNaN(d.getTime())) return '';
    var now = new Date();
    var timeStr = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    if (d.toDateString() !== now.toDateString()) {
      timeStr = d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + timeStr;
    }
    return timeStr;
  }

  function renderMessage(msg) {
    var div = document.createElement('div');
    var senderType = msg.sender_type || 'system';
    div.className = 'mac-chat-msg mac-chat-msg-' + senderType;
    var content = (msg.content || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>');
    div.innerHTML = content + '<span class="mac-chat-msg-time">' + formatTime(msg.created_at || msg.timestamp) + '</span>';
    return div;
  }

  function renderMessages() {
    messagesArea.innerHTML = '';
    if (state.messages.length === 0) {
      var welcome = document.createElement('div');
      welcome.className = 'mac-chat-msg mac-chat-msg-system';
      welcome.textContent = 'Welcome! How can we help you today?';
      messagesArea.appendChild(welcome);
    }
    state.messages.forEach(function(msg) {
      messagesArea.appendChild(renderMessage(msg));
    });
    messagesArea.scrollTop = messagesArea.scrollHeight;
  }

  function showChatView() {
    startForm.style.display = 'none';
    messagesArea.style.display = 'flex';
    footer.style.display = 'flex';
    renderMessages();
    msgInput.focus();
  }

  function showStartForm() {
    startForm.style.display = 'flex';
    messagesArea.style.display = 'none';
    footer.style.display = 'none';
    state.conversationId = null;
    state.messages = [];
    state.lastMessageTs = null;
    localStorage.removeItem(STORAGE_KEY);
  }

  // Start conversation
  function startConversation() {
    var name = nameInput.value.trim();
    if (!name) {
      formError.textContent = 'Please enter your name.';
      return;
    }
    formError.textContent = '';
    startBtn.disabled = true;
    startBtn.textContent = 'Connecting...';

    apiCall('POST', '/api/v2/chat/conversations', {
      visitor_name: name,
      visitor_email: emailInput.value.trim() || null,
      visitor_phone: phoneInput.value.trim() || null,
      page_url: window.location.href,
      user_agent: navigator.userAgent
    }).then(function(data) {
      state.conversationId = data.conversation_id || data.id;
      state.visitorName = name;
      localStorage.setItem(STORAGE_KEY, state.conversationId);
      localStorage.setItem(STORAGE_VISITOR_KEY, name);
      state.messages = data.messages || [];
      updateLastTs();
      showChatView();
      startPolling();
    }).catch(function() {
      formError.textContent = 'Connection error. Please try again.';
    }).finally(function() {
      startBtn.disabled = false;
      startBtn.textContent = 'Start Chat';
    });
  }

  // Send message
  function sendMessage() {
    var text = msgInput.value.trim();
    if (!text || !state.conversationId) return;

    msgInput.value = '';
    sendBtn.disabled = true;

    // Optimistic render
    var optimistic = { content: text, sender_type: 'visitor', created_at: new Date().toISOString() };
    state.messages.push(optimistic);
    renderMessages();

    apiCall('POST', '/api/v2/chat/conversations/' + state.conversationId + '/messages', {
      content: text,
      sender_type: 'visitor'
    }).then(function(data) {
      // Replace optimistic with server response
      state.messages[state.messages.length - 1] = data;
      updateLastTs();
      renderMessages();
    }).catch(function() {
      // Mark failed
      optimistic.content += ' (failed to send)';
      renderMessages();
    }).finally(function() {
      sendBtn.disabled = false;
      msgInput.focus();
    });
  }

  function updateLastTs() {
    if (state.messages.length > 0) {
      var last = state.messages[state.messages.length - 1];
      state.lastMessageTs = last.created_at || last.timestamp || null;
    }
  }

  // Poll for new messages
  function pollMessages() {
    if (!state.conversationId || !state.open) return;
    var url = '/api/v2/chat/conversations/' + state.conversationId + '/messages';
    if (state.lastMessageTs) {
      url += '?after=' + encodeURIComponent(state.lastMessageTs);
    }
    apiCall('GET', url).then(function(data) {
      var newMsgs = Array.isArray(data) ? data : (data.messages || []);
      if (newMsgs.length > 0) {
        // Filter duplicates
        var existingIds = {};
        state.messages.forEach(function(m) { if (m.id) existingIds[m.id] = true; });
        var added = false;
        newMsgs.forEach(function(m) {
          if (!m.id || !existingIds[m.id]) {
            // On first load (no lastMessageTs set initially), replace all
            if (!state.lastMessageTs && state.messages.length === 0) {
              state.messages.push(m);
              added = true;
            } else if (m.id && !existingIds[m.id]) {
              state.messages.push(m);
              existingIds[m.id] = true;
              added = true;
              if (m.sender_type === 'agent') {
                playNotification();
                if (!state.open) {
                  state.unreadCount++;
                  updateBadge();
                }
              }
            }
          }
        });
        if (added) {
          updateLastTs();
          renderMessages();
        }
      }
    }).catch(function(err) {
      // If 404, conversation is gone
      if (err.message && err.message.indexOf('404') !== -1) {
        stopPolling();
        showStartForm();
      }
    });
  }

  function startPolling() {
    stopPolling();
    state.pollTimer = setInterval(pollMessages, POLL_INTERVAL);
  }

  function stopPolling() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  function updateBadge() {
    if (state.unreadCount > 0) {
      badge.textContent = state.unreadCount > 9 ? '9+' : state.unreadCount;
      badge.classList.add('mac-chat-visible');
    } else {
      badge.classList.remove('mac-chat-visible');
    }
  }

  // Open / Close
  function openChat() {
    state.open = true;
    chatWindow.classList.add('mac-chat-open');
    bubble.style.display = 'none';
    state.unreadCount = 0;
    updateBadge();

    if (state.conversationId) {
      showChatView();
      startPolling();
    } else {
      showStartForm();
      if (state.visitorName) nameInput.value = state.visitorName;
    }
  }

  function closeChat() {
    state.open = false;
    chatWindow.classList.remove('mac-chat-open');
    bubble.style.display = 'flex';
    stopPolling();
  }

  // Load existing conversation on init
  function loadExisting() {
    if (!state.conversationId) return;

    apiCall('GET', '/api/v2/chat/conversations/' + state.conversationId + '/messages').then(function(data) {
      var msgs = Array.isArray(data) ? data : (data.messages || []);
      state.messages = msgs;
      updateLastTs();
      // Check if conversation is closed
      if (data.status === 'closed') {
        showStartForm();
        localStorage.removeItem(STORAGE_KEY);
        return;
      }
    }).catch(function() {
      // Conversation not found or error - reset
      state.conversationId = null;
      localStorage.removeItem(STORAGE_KEY);
    });
  }

  // Event listeners
  bubble.addEventListener('click', openChat);
  closeBtn.addEventListener('click', closeChat);

  startBtn.addEventListener('click', startConversation);
  nameInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') startConversation();
  });

  sendBtn.addEventListener('click', sendMessage);
  msgInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Close on Escape
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && state.open) closeChat();
  });

  // Init
  loadExisting();

})();
