import os
import threading
import uuid
import time
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import shutil
import logging

# ============================================
# CONFIGURACION DEL ENTORNO
# ============================================

# 1. Configuración de Log para mejor depuración
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 2. Rutas para el entorno de la nube (Render)
BASE_DIR = Path(__file__).resolve().parent
# Usaremos /tmp para descargas temporales, ya que es el directorio recomendado
# y a menudo el único con permisos de escritura en entornos de nube gratuitos.
DOWNLOADS_DIR = Path('/tmp') / 'downloads'

# 3. Proxy: NULO por defecto en entornos de nube
PROXY = os.getenv('PROXY', None) 

app = Flask(__name__)
app.config['DOWNLOADS_DIR'] = DOWNLOADS_DIR

# Lock para operaciones thread-safe
status_lock = threading.Lock()

# Crear carpeta de descargas en /tmp
try:
    DOWNLOADS_DIR.mkdir(exist_ok=True, parents=True)
    logger.info(f"Carpeta de descargas (temporal): {DOWNLOADS_DIR}")
except Exception as e:
    logger.error(f"Error CRÍTICO creando carpeta de descargas: {e}")

# ============================================
# LIMPIEZA AUTOMATICA
# ============================================
# Limpia archivos más antiguos de 1 hora
def cleanup_old_files():
    try:
        current_time = time.time()
        deleted_count = 0
        for file in DOWNLOADS_DIR.glob('*'):
            # El tiempo de modificación (st_mtime) puede fallar con /tmp en algunos hosts
            # Pero intentaremos borrar todo lo que no sea reciente.
            if file.is_file() and (current_time - file.stat().st_mtime > 3600): 
                file.unlink()
                deleted_count += 1
        
        if deleted_count > 0:
            logger.info(f"Archivos eliminados en limpieza: {deleted_count}")
    except Exception as e:
        logger.error(f"Error en limpieza: {e}")

# ============================================
# FUNCION DE DESCARGA
# ============================================
def download_media_threaded(download_id, url, format_type):
    # Usamos el directorio temporal
    status_file = DOWNLOADS_DIR / f'{download_id}_status.txt'
    extension = 'mp3' if format_type == 'mp3' else 'mp4'
    final_filepath = DOWNLOADS_DIR / f'{download_id}_media.{extension}'
    
    # yt-dlp creará su propio archivo temporal, solo necesitamos el nombre base
    temp_filepath_base = DOWNLOADS_DIR / f'{download_id}_temp'

    def update_status(status, message=None, filename=None, size=None):
        with status_lock:
            content = f"status: {status}"
            if message:
                content += f"\nmessage: {message}"
            if filename:
                content += f"\nfilename: {filename}"
            if size:
                content += f"\nsize: {size}"
            status_file.write_text(content)

    update_status("downloading")
    logger.info(f"Iniciando descarga: {download_id} | Formato: {format_type}")

    ydl_opts = {
        'format': 'bestaudio/best' if format_type == 'mp3' else 'bestvideo+bestaudio/best',
        'outtmpl': str(temp_filepath_base),
        'quiet': True, # Silenciamos el output para que los logs sean más limpios
        'no_warnings': True,
        'noplaylist': True,
        'ignoreerrors': False,
        'proxy': PROXY,
        'geo_bypass': True,
    }
    
    # Postprocesamiento para MP3
    if format_type == 'mp3':
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    
    # ⚠️ CRÍTICO: Comprobación de FFmpeg para la conversión a MP3
    if format_type == 'mp3' and not shutil.which('ffmpeg'):
        error_msg = "FFmpeg no encontrado. No se puede convertir a MP3."
        logger.error(error_msg)
        update_status("error", message=error_msg)
        return

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'Sin título')
            logger.info(f"Descarga completada (yt-dlp): {title}")

        # yt-dlp guarda el archivo final con extensión (ej: id_temp.mp3)
        # Necesitamos encontrar el archivo recién creado.
        downloaded_files = list(DOWNLOADS_DIR.glob(f'{download_id}_temp*'))
        
        if not downloaded_files:
            raise FileNotFoundError("Archivo final de descarga no encontrado.")

        source_file = downloaded_files[0]
        
        # Renombramos al nombre final limpio (id_media.mp3/mp4)
        shutil.move(str(source_file), str(final_filepath))
        
        file_size = final_filepath.stat().st_size / (1024 * 1024)
        logger.info(f"Archivo final creado: {final_filepath.name} ({file_size:.2f} MB)")
        
        update_status(
            "complete",
            filename=final_filepath.name,
            size=f"{file_size:.2f} MB"
        )
        
    except yt_dlp.utils.DownloadError as e:
        error_msg = f"Error de descarga (URL inválida o problema con yt-dlp): {str(e)}"
        logger.error(f"ERROR: {error_msg}")
        update_status("error", message=error_msg)
    except Exception as e:
        error_msg = f"Error inesperado durante el proceso: {str(e)}"
        logger.error(f"ERROR: {error_msg}")
        update_status("error", message=error_msg)
    finally:
        # Limpieza de archivos temporales de yt-dlp si quedan
        for temp_file in DOWNLOADS_DIR.glob(f'{download_id}_temp*'):
            try:
                temp_file.unlink()
            except:
                pass


# ============================================
# RUTAS DE FLASK
# ============================================

@app.route("/")
def index():
    cleanup_old_files()
    return render_template("index.html")

@app.route("/download_start", methods=["POST"])
def download_start():
    # ... (El código de esta función es igual, solo cambia 'print' por 'logger.info')
    try:
        data = request.get_json()
        if not data:
             return jsonify({"success": False, "message": "Datos no proporcionados"}), 400
        
        url = data.get("url")
        format_type = data.get("format", "mp3")

        if not url:
             return jsonify({"success": False, "message": "URL no proporcionada"}), 400
        
        if format_type not in ['mp3', 'mp4']:
            format_type = 'mp3'

        download_id = str(uuid.uuid4())[:8]
        
        logger.info(f"Nueva descarga: ID={download_id}, URL={url[:50]}..., Formato={format_type}")
        
        thread = threading.Thread(
            target=download_media_threaded,
            args=(download_id, url, format_type),
            daemon=True # Hace que el hilo muera con el proceso principal
        )
        thread.start()
        
        return jsonify({
            "success": True,
            "download_id": download_id,
            "message": f"Descarga iniciada con ID: {download_id}"
        })

    except Exception as e:
        error_msg = f"Error al iniciar descarga: {str(e)}"
        logger.error(f"ERROR: {error_msg}")
        return jsonify({
            "success": False,
            "message": error_msg
        }), 500

@app.route("/download_status/<download_id>")
def download_status(download_id):
    # ... (El código de esta función es igual)
    if not download_id or len(download_id) > 20 or '..' in download_id:
        return jsonify({"status": "error", "message": "ID de descarga invalido"}), 400
    
    status_file = DOWNLOADS_DIR / f'{download_id}_status.txt'
    
    if not status_file.exists():
        return jsonify({"status": "pending"})

    try:
        with status_lock:
            content = status_file.read_text().strip().split('\n')
        
        status_data = {}
        for line in content:
            if ': ' in line:
                key, value = line.split(': ', 1)
                status_data[key.strip()] = value.strip()
        
        return jsonify(status_data)

    except Exception as e:
        logger.error(f"Error leyendo estado para {download_id}: {e}")
        return jsonify({"status": "error", "message": "Error leyendo estado de descarga"})

@app.route("/get_file/<filename>")
def get_file(filename):
    # ... (El código de esta función es igual)
    if '..' in filename or '/' in filename or '\\' in filename:
        logger.warning(f"Intento de acceso no autorizado: {filename}")
        return jsonify({"error": "Nombre de archivo invalido"}), 403
    
    if not filename.endswith(('.mp3', '.mp4')):
        return jsonify({"error": "Tipo de archivo no permitido"}), 403
    
    file_path = DOWNLOADS_DIR / filename
    
    if not file_path.exists():
        logger.error(f"Archivo no encontrado: {filename}")
        return jsonify({"error": f"Archivo no encontrado: {filename}"}), 404
    
    try:
        logger.info(f"Enviando archivo: {filename}")
        # Después de enviar el archivo, se recomienda borrarlo inmediatamente
        response = send_file(
            file_path, 
            as_attachment=True,
            download_name=filename
        )
        # ⚠️ Limpieza inmediata
        try:
            os.remove(file_path)
            logger.info(f"Archivo {filename} borrado después de ser servido.")
        except Exception as e:
            logger.error(f"No se pudo borrar el archivo {filename}: {e}")
            
        return response
    except Exception as e:
        logger.error(f"Error enviando archivo {filename}: {e}")
        return jsonify({"error": f"Error al enviar archivo: {str(e)}"}), 500

@app.route("/health")
def health_check():
    return jsonify({
        "status": "ok",
        "downloads_dir": str(DOWNLOADS_DIR),
        "files_count": len(list(DOWNLOADS_DIR.glob('*'))),
        "proxy": PROXY
    })

if __name__ == "__main__":
    logger.info("="*50)
    logger.info("Iniciando MusicDownloader")
    logger.info(f"Directorio de descargas: {DOWNLOADS_DIR}")
    logger.info(f"Proxy configurado: {PROXY}")
    logger.info("="*50)
    # ⚠️ Usamos '0.0.0.0' para el hosting, no '127.0.0.1'
    app.run(debug=True, host='0.0.0.0', port=5000)