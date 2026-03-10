/* global state */
let lastSender = null;

const thread  = document.getElementById('thread');
const input   = document.getElementById('msg-input');
const sendBtn = document.getElementById('send-btn');

const WELCOME =
  "Hi! I'm your TfL assistant, connected live to the TfL Nexus MCP server.\n\n" +
  "Try asking me things like:\n" +
  "• \"Plan the fastest route from Paddington to Canary Wharf\"\n" +
  "• \"How crowded is the network right now?\"\n" +
  "• \"Generate a snapshot report of the network\"";

// ─── Utilities ────────────────────────────────────────────────────────────────

function nowLabel() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function scrollToBottom() {
  thread.scrollTop = thread.scrollHeight;
}

// ─── Rendering ────────────────────────────────────────────────────────────────

function addDateDivider(label) {
  const el = document.createElement('div');
  el.className = 'date-divider';
  el.textContent = label;
  thread.appendChild(el);
  lastSender = null; // always reset grouping after a divider
}

function addMessage(text, role) {
  const isMe = role === 'user';
  const wrap = document.createElement('div');
  wrap.classList.add('message', isMe ? 'me' : 'them');

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = text;

  const ts = document.createElement('span');
  ts.className = 'timestamp';
  ts.textContent = nowLabel();

  wrap.appendChild(bubble);
  wrap.appendChild(ts);
  thread.appendChild(wrap);

  lastSender = role;
  scrollToBottom();
  return wrap;
}

function showTyping() {
  const el = document.createElement('div');
  el.id = 'typing-indicator';
  el.className = 'typing';
  el.innerHTML = '<span></span><span></span><span></span>';
  thread.appendChild(el);
  scrollToBottom();
}

function hideTyping() {
  document.getElementById('typing-indicator')?.remove();
}

// ─── Input handling ───────────────────────────────────────────────────────────

input.addEventListener('input', () => {
  // auto-grow
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 110) + 'px';

  sendBtn.disabled = input.value.trim().length === 0;
});

input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!sendBtn.disabled) send();
  }
});

sendBtn.addEventListener('click', send);

// ─── Send ─────────────────────────────────────────────────────────────────────

async function send() {
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  input.style.height = 'auto';
  sendBtn.disabled = true;

  addMessage(text, 'user');
  showTyping();

  try {
    const res = await fetch('/api/message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });

    const data = await res.json();
    hideTyping();

    if (!res.ok || data.error) {
      addMessage(`⚠ ${data.error ?? 'Something went wrong. Please try again.'}`, 'assistant');
    } else {
      addMessage(data.content, 'assistant');
    }
  } catch {
    hideTyping();
    addMessage('Could not reach the server. Is TfL Nexus running on port 9000?', 'assistant');
  }
}

// ─── Init ─────────────────────────────────────────────────────────────────────

addDateDivider('Today');
addMessage(WELCOME, 'assistant');
