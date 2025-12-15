// static/script.js

const urlInput = document.getElementById('youtube-url');
const statusArea = document.getElementById('status-area');
const statusMessage = document.getElementById('status-message');
const downloadLinkDiv = document.getElementById('download-link');
const finalLink = document.getElementById('final-link');
const mp3Button = document.getElementById('btn-mp3');
const mp4Button = document.getElementById('btn-mp4');

let checkStatusInterval = null;

function setStatus(message, className = 'info') {
    statusMessage.textContent = message;
    statusArea.className = `status-box ${className}`;
}

function disableButtons(disabled) {
    mp3Button.disabled = disabled;
    mp4Button.disabled = disabled;
    urlInput.disabled = disabled;
}

function startDownload(format) {
    const url = urlInput.value.trim();
    if (!url || !url.startsWith('http')) {
        setStatus('⚠️ Por favor, ingresa una URL de YouTube válida.', 'error');
        return;
    }

    // 1. Ocultar enlace anterior y deshabilitar botones
    downloadLinkDiv.style.display = 'none';
    disableButtons(true);
    setStatus(`⏳ Iniciando descarga de ${format.toUpperCase()}...`, 'pending');

    // 2. Llamada a la API para iniciar la descarga
    fetch('/download_start', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ url: url, format: format })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            setStatus('🚀 Descarga en progreso... ¡No cierres esta pestaña!', 'pending');
            const downloadId = data.download_id;
            
            // 3. Iniciar polling para verificar el estado
            checkStatusInterval = setInterval(() => checkStatus(downloadId), 3000); // Revisar cada 3 segundos

        } else {
            setStatus(`❌ Error al iniciar: ${data.message}`, 'error');
            disableButtons(false);
        }
    })
    .catch(error => {
        setStatus(`🚨 Error de conexión con el servidor: ${error.message}`, 'error');
        disableButtons(false);
    });
}

function checkStatus(downloadId) {
    fetch(`/download_status/${downloadId}`)
    .then(response => response.json())
    .then(data => {
        if (data.status === 'complete') {
            clearInterval(checkStatusInterval);
            const filename = data.filename;
            const size = data.size || 'Tamaño desconocido';

            setStatus(`✅ ¡LISTO! (${size})`, 'success');
            
            // 4. Mostrar el enlace de descarga final
            finalLink.href = `/get_file/${filename}`;
            finalLink.download = filename; // Fuerza el nombre del archivo
            finalLink.textContent = `Descargar ${filename} (${size})`;
            downloadLinkDiv.style.display = 'block';

            disableButtons(false);
            
            // 5. Limpiar URL para una nueva descarga
            urlInput.value = '';

        } else if (data.status === 'error') {
            clearInterval(checkStatusInterval);
            setStatus(`❌ ERROR: ${data.message || 'Error desconocido'}`, 'error');
            disableButtons(false);

        } else if (data.status === 'downloading') {
            setStatus('🔄 Descargando y convirtiendo... Por favor, espere.', 'pending');
        }
        // Si el estado es 'pending' (aún no se crea el archivo de estado) o 'downloading', sigue esperando.
    })
    .catch(error => {
        clearInterval(checkStatusInterval);
        setStatus(`🚨 Error de comunicación: ${error.message}`, 'error');
        disableButtons(false);
    });
}