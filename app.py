import os
import uuid
import logging
from flask import Flask, render_template, request, send_file, after_this_request
import yt_dlp

# Configuración de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Carpeta temporal para descargas en Render/Docker
DOWNLOAD_FOLDER = '/tmp/downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    video_url = request.form.get('url')
    if not video_url:
        return "Por favor, ingresa una URL válida.", 400

    download_id = str(uuid.uuid4())[:8]
    output_filename = f"audio_{download_id}"
    output_path = os.path.join(DOWNLOAD_FOLDER, output_filename)

    # CONFIGURACIÓN "ANTI-BLOQUEO" PARA YT-DLP
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path,
        'quiet': False,
        'no_warnings': False,
        # Engañamos a YouTube simulando ser un cliente móvil
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios'],
                'player_skip_bundle_check': True,
            }
        },
        # User-Agent real para evitar ser detectado como bot de servidor
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    try:
        logger.info(f"Iniciando descarga: {download_id} | URL: {video_url}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        final_file_path = f"{output_path}.mp3"

        if os.path.exists(final_file_path):
            @after_this_request
            def cleanup(response):
                try:
                    os.remove(final_file_path)
                    logger.info(f"Archivo eliminado: {final_file_path}")
                except Exception as e:
                    logger.error(f"Error al limpiar archivo: {e}")
                return response

            return send_file(
                final_file_path,
                as_attachment=True,
                download_name="tu_musica.mp3",
                mimetype="audio/mpeg"
            )
        else:
            return "Error: El archivo MP3 no se generó correctamente.", 500

    except Exception as e:
        logger.error(f"Error crítico: {str(e)}")
        return f"❌ Error de descarga: {str(e)}", 500

if __name__ == '__main__':
    # Usar puerto 8000 para Docker
    app.run(host='0.0.0.0', port=8000)
