document.getElementById('executeBtn').addEventListener('click', async () => {
    const command = document.getElementById('commandInput').value;
    const log = document.getElementById('log');

    log.innerHTML += `<div>> ${command}</div>`;

    try {
        const response = await fetch('/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command })
        });
        const result = await response.json();
        log.innerHTML += `<div style="color: green">${result.message}</div>`;
        log.scrollTop = log.scrollHeight;
    } catch (error) {
        log.innerHTML += `<div style="color: red">Error: ${error.message}</div>`;
    }
});
