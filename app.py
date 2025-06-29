# app.py - Flask Backend for Audio Splitting

import os
import subprocess
import tempfile
import shutil
from datetime import datetime
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

@app.route('/upload-audio', methods=['POST'])
def upload_audio():
    if 'audioFile' not in request.files:
        return jsonify({"error": "No audio file part in the request"}), 400

    audio_file = request.files['audioFile']

    if audio_file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if not audio_file.filename.lower().endswith('.mp3'):
        return jsonify({"error": "Only MP3 files are allowed"}), 400

    audio_file.seek(0, os.SEEK_END)
    file_size = audio_file.tell()
    audio_file.seek(0)
    if file_size > MAX_FILE_SIZE:
        return jsonify({"error": f"File size exceeds {MAX_FILE_SIZE / (1024 * 1024)}MB limit"}), 413

    temp_dir = tempfile.mkdtemp()
    
    try:
        input_audio_path = os.path.join(temp_dir, audio_file.filename)
        audio_file.save(input_audio_path)
        print(f"Uploaded file saved to: {input_audio_path}")

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        output_dir_name = f"separated_tmp_{timestamp}"
        output_dir_path = os.path.join(temp_dir, output_dir_name)

        # Run Demucs
        demucs_command = ["demucs", input_audio_path, "-o", output_dir_path]
        print(f"Running Demucs command: {' '.join(demucs_command)}")
        process = subprocess.run(demucs_command, capture_output=True, text=True, check=True)
        print("Demucs stdout:\n", process.stdout)
        print("Demucs stderr:\n", process.stderr)

        # Verify output directory
        if not os.path.isdir(output_dir_path):
            return jsonify({"error": "Demucs processing failed or output directory not found."}), 500

        # Convert all WAV files to MP3 to save space
        print("Converting WAV files to MP3...")
        for root, _, files in os.walk(output_dir_path):
            for file in files:
                if file.endswith(".wav"):
                    wav_path = os.path.join(root, file)
                    mp3_path = wav_path.replace(".wav", ".mp3")
                    ffmpeg_command = [
                        "ffmpeg", "-y",
                        "-i", wav_path,
                        "-codec:a", "libmp3lame",
                        "-qscale:a", "2",
                        mp3_path
                    ]
                    subprocess.run(ffmpeg_command, capture_output=True, check=True)
                    os.remove(wav_path)

        # Create archive
        archive_name = f"{output_dir_name}.tar.gz"
        archive_path = os.path.join(temp_dir, archive_name)

        original_cwd = os.getcwd()
        os.chdir(temp_dir)
        tar_command = ["tar", "-czvf", archive_name, output_dir_name]
        process = subprocess.run(tar_command, capture_output=True, text=True, check=True)
        print("Tar stdout:\n", process.stdout)
        print("Tar stderr:\n", process.stderr)
        os.chdir(original_cwd)

        if not os.path.exists(archive_path):
            return jsonify({"error": "Failed to create compressed archive."}), 500

        print(f"Sending file: {archive_path}")
        return send_file(archive_path, as_attachment=True, download_name=archive_name, mimetype='application/gzip')

    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        return jsonify({"error": f"Processing failed: {e.stderr}"}), 500
    except Exception as e:
        print(f"Unexpected error: {e}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500
    finally:
        if os.path.exists(temp_dir):
            print(f"Cleaning up temporary directory: {temp_dir}")
            shutil.rmtree(temp_dir)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
