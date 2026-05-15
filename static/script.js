const chatLog = document.getElementById("chat");
const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message");
const statusPill = document.getElementById("status");
const studentsBody = document.getElementById("students-body");
const studentForm = document.getElementById("student-form");
const notice = document.getElementById("notice");
const searchInput = document.getElementById("student-search");

let socket;
let sessionId = null;
let currentStudents = [];

function setStatus(text, state = "") {
    statusPill.textContent = text;
    statusPill.dataset.state = state;
}

function showNotice(text, state = "") {
    notice.textContent = text;
    notice.dataset.state = state;
    if (text) {
        window.clearTimeout(showNotice.timer);
        showNotice.timer = window.setTimeout(() => {
            notice.textContent = "";
            notice.dataset.state = "";
        }, 2800);
    }
}

function addMessage(text, role) {
    const item = document.createElement("article");
    item.className = `message ${role}`;
    item.textContent = text;
    chatLog.appendChild(item);
    chatLog.scrollTop = chatLog.scrollHeight;
}

function renderStudents(students) {
    currentStudents = Array.isArray(students) ? students : [];
    studentsBody.innerHTML = "";

    if (!currentStudents.length) {
        const empty = document.createElement("tr");
        empty.innerHTML = '<td colspan="4" class="empty">No students found</td>';
        studentsBody.appendChild(empty);
        return;
    }

    const rows = document.createDocumentFragment();
    currentStudents.forEach((student) => {
        const tr = document.createElement("tr");
        tr.dataset.id = student.id;
        tr.innerHTML = `
            <td><input class="cell-input" data-field="name" value="${escapeAttr(student.name)}" aria-label="Name"></td>
            <td><input class="cell-input roll-input" data-field="roll" type="number" min="0" value="${student.roll}" aria-label="Roll"></td>
            <td><input class="cell-input dept-input" data-field="dept" value="${escapeAttr(student.dept)}" aria-label="Department"></td>
            <td class="row-actions">
                <button type="button" class="save-row" title="Save student">Save</button>
                <button type="button" class="delete-row" title="Delete student">Delete</button>
            </td>
        `;
        rows.appendChild(tr);
    });
    studentsBody.appendChild(rows);
}

function escapeAttr(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll('"', "&quot;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
}

async function fetchStudents(query = "") {
    const url = query ? `/api/students?query=${encodeURIComponent(query)}` : "/api/students";
    try {
        const response = await fetch(url);
        const data = await response.json();
        renderStudents(data.students);
    } catch {
        showNotice("Could not load students.", "error");
    }
}

async function sendViaApi(message) {
    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message, session_id: sessionId }),
        });
        const data = await response.json();
        sessionId = data.session_id || sessionId;
        addMessage(data.reply || data.detail || "No response.", "agent");
        if (data.students) renderStudents(data.students);
    } catch {
        addMessage("API request failed.", "agent");
    }
}

function connectSocket() {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${scheme}://${location.host}/ws`);

    socket.addEventListener("open", () => setStatus("Live", "ok"));
    socket.addEventListener("message", (event) => {
        const data = JSON.parse(event.data);
        sessionId = data.session_id || sessionId;
        if (data.reply) addMessage(data.reply, "agent");
        if (data.students) renderStudents(data.students);
    });
    socket.addEventListener("close", () => setStatus("API fallback", "warn"));
    socket.addEventListener("error", () => setStatus("API fallback", "warn"));
}

chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = messageInput.value.trim();
    if (!message) return;

    addMessage(message, "user");
    messageInput.value = "";

    if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ message }));
    } else {
        await sendViaApi(message);
    }
});

studentForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
        name: event.target.name.value.trim(),
        roll: Number(event.target.roll.value),
        dept: event.target.dept.value.trim(),
    };

    const response = await fetch("/api/students", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
        showNotice(data.detail || "Could not add student.", "error");
        return;
    }
    studentForm.reset();
    renderStudents(data.students);
    showNotice("Student added.", "ok");
});

studentsBody.addEventListener("click", async (event) => {
    const row = event.target.closest("tr");
    if (!row?.dataset.id) return;

    if (event.target.classList.contains("delete-row")) {
        const response = await fetch(`/api/students/${row.dataset.id}`, { method: "DELETE" });
        const data = await response.json();
        if (!response.ok) {
            showNotice(data.detail || "Could not delete student.", "error");
            return;
        }
        renderStudents(data.students);
        showNotice("Student deleted.", "ok");
        return;
    }

    if (event.target.classList.contains("save-row")) {
        const payload = {};
        row.querySelectorAll(".cell-input").forEach((input) => {
            payload[input.dataset.field] = input.dataset.field === "roll" ? Number(input.value) : input.value.trim();
        });

        const response = await fetch(`/api/students/${row.dataset.id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) {
            showNotice(data.detail || "Could not save student.", "error");
            return;
        }
        renderStudents(data.students);
        showNotice("Student saved.", "ok");
    }
});

searchInput.addEventListener("input", () => {
    window.clearTimeout(searchInput.timer);
    searchInput.timer = window.setTimeout(() => fetchStudents(searchInput.value.trim()), 160);
});

connectSocket();
fetchStudents();
