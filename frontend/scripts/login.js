async function authRequest(path, data) {
    const status = await (await fetch('/auth/status', {cache: 'no-store'})).json();
    const response = await fetch(path, {method: 'POST', headers: {
        'Content-Type': 'application/json', 'X-Recetario-Request': '1',
        'X-CSRF-Token': status.csrf || ''
    }, body: JSON.stringify(data)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'No se pudo iniciar sesión');
}
document.getElementById('login').addEventListener('submit', async event => {
    event.preventDefault();
    const input = document.getElementById('password');
    try {
        await authRequest('/auth/login', {password: input.value});
        location.assign('/');
    } catch (error) {
        document.getElementById('status').textContent = error.message;
    } finally { input.value = ''; }
});
document.getElementById('logout').addEventListener('click', async () => {
    try {
        await authRequest('/auth/logout', {});
        document.getElementById('status').textContent = 'Sesión cerrada';
    } catch (error) { document.getElementById('status').textContent = error.message; }
});
