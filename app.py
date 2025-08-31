import os
import time
import math
import requests
import logging
import uuid
import threading
from PIL import Image
from io import BytesIO
from flask import Flask, render_template, request, jsonify, send_file, session
from werkzeug.middleware.proxy_fix import ProxyFix

# Configure logging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "fallback-secret-key-for-dev")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Global dictionary to store download progress
download_progress = {}

# Headers for IIIF requests (from original code)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0",
    "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Connection": "keep-alive",
    "Referer": "https://antenati.cultura.gov.it/",
    "Sec-Fetch-Dest": "image",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "same-site",
    "Priority": "u=5, i",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
    "TE": "trailers"
}

def fetch_tile(url, retries=3):
    """Fetch a single tile with retry logic"""
    resp = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                return resp
            app.logger.warning(f"Tile failed (attempt {attempt}/{retries}), status {resp.status_code}")
            time.sleep(1)
        except requests.exceptions.RequestException as e:
            app.logger.warning(f"Request exception on attempt {attempt}: {e}")
            if attempt == retries:
                raise
            time.sleep(1)
    
    # If we get here, all retries failed
    if resp is not None:
        resp.raise_for_status()
    else:
        raise requests.exceptions.RequestException("Failed to fetch tile after all retries")

def update_progress(session_id, message, progress=None, error=None, completed=False, file_path=None):
    """Update download progress for a session"""
    download_progress[session_id] = {
        'message': message,
        'progress': progress,
        'error': error,
        'completed': completed,
        'file_path': file_path,
        'timestamp': time.time()
    }

def download_and_stitch_image(image_id, session_id):
    """Background task to download and stitch IIIF image"""
    try:
        update_progress(session_id, "Fetching image metadata...", 0)
        
        # Validate image_id
        if "/" in image_id or "\\" in image_id or not image_id.isalnum():
            update_progress(session_id, "Invalid image ID", error="Please provide a valid alphanumeric IIIF image ID")
            return
        
        base_url = f"https://iiif-antenati.cultura.gov.it/iiif/2/{image_id}"
        
        # Create downloads directory if it doesn't exist
        downloads_dir = os.path.join(os.getcwd(), 'downloads')
        os.makedirs(downloads_dir, exist_ok=True)
        
        output_file = os.path.join(downloads_dir, f"{image_id}_stitched.jpg")
        
        # Fetch image metadata
        info_url = f"{base_url}/info.json"
        app.logger.info(f"Fetching metadata from: {info_url}")
        
        info_resp = requests.get(info_url, headers=HEADERS, timeout=30)
        info_resp.raise_for_status()
        info = info_resp.json()
        
        width, height = info["width"], info["height"]
        tile_width = info["tiles"][0]["width"]
        tile_height = info["tiles"][0].get("height", tile_width)
        
        cols = math.ceil(width / tile_width)
        rows = math.ceil(height / tile_height)
        total_tiles = cols * rows
        
        update_progress(session_id, f"Image size: {width}x{height}, downloading {total_tiles} tiles...", 5)
        
        # Create final image
        final_img = Image.new("RGB", (width, height))
        tile_num = 0
        
        for row in range(rows):
            for col in range(cols):
                x = col * tile_width
                y = row * tile_height
                w = min(tile_width, width - x)
                h = min(tile_height, height - y)
                region = f"{x},{y},{w},{h}"
                tile_url = f"{base_url}/{region}/full/0/default.jpg"
                
                # Download tile
                resp = fetch_tile(tile_url)
                if resp and resp.content:
                    tile_img = Image.open(BytesIO(resp.content))
                    final_img.paste(tile_img, (x, y))
                else:
                    raise requests.exceptions.RequestException(f"Failed to download tile: {tile_url}")
                
                tile_num += 1
                progress = 5 + (tile_num / total_tiles) * 85  # 5-90% for downloading
                update_progress(session_id, f"Downloaded tile {tile_num}/{total_tiles}", progress)
        
        update_progress(session_id, "Saving final image...", 95)
        
        # Save the final image
        final_img.save(output_file, "JPEG", quality=95)
        
        update_progress(session_id, "Image ready for download!", 100, completed=True, file_path=output_file)
        
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Network error: {e}")
        update_progress(session_id, "Network error occurred", error=f"Failed to download image: {str(e)}")
    except Exception as e:
        app.logger.error(f"Unexpected error: {e}")
        update_progress(session_id, "An error occurred", error=f"Unexpected error: {str(e)}")

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/start_download', methods=['POST'])
def start_download():
    """Start image download process"""
    data = request.get_json()
    image_id = data.get('image_id', '').strip()
    
    if not image_id:
        return jsonify({'error': 'Please enter an IIIF image ID'}), 400
    
    if "/" in image_id or "\\" in image_id or not image_id.replace('_', '').replace('-', '').isalnum():
        return jsonify({'error': 'Invalid image ID format. Please provide a valid IIIF image ID.'}), 400
    
    # Generate session ID for this download
    session_id = str(uuid.uuid4())
    
    # Start background download
    thread = threading.Thread(target=download_and_stitch_image, args=(image_id, session_id))
    thread.daemon = True
    thread.start()
    
    return jsonify({'session_id': session_id})

@app.route('/progress/<session_id>')
def get_progress(session_id):
    """Get download progress for a session"""
    if session_id not in download_progress:
        return jsonify({'error': 'Session not found'}), 404
    
    return jsonify(download_progress[session_id])

@app.route('/download/<session_id>')
def download_file(session_id):
    """Download the completed image file"""
    if session_id not in download_progress:
        return jsonify({'error': 'Session not found'}), 404
    
    progress_data = download_progress[session_id]
    
    if not progress_data.get('completed'):
        return jsonify({'error': 'Download not completed yet'}), 400
    
    file_path = progress_data.get('file_path')
    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404
    
    filename = os.path.basename(file_path)
    
    return send_file(
        file_path,
        as_attachment=True,
        download_name=filename,
        mimetype='image/jpeg'
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
