# app.py - Flask Backend for Audio Splitting

import os
import subprocess
import tempfile
import shutil
from datetime import datetime
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

app = Flask(__name__)
# IMPORTANT: Replace with your actual frontend domain(s) for production
# For local development, you might use "http://localhost:8000" or similar.
# Ensure no trailing slash for exact match.
#CORS(app, resources={r"/*": {"origins": ["http://localhost:8000", "https://your-frontend-domain.com"]}}) 
CORS(app, resources={r"/*": {"origins": ["http://localhost:8000", "https://bsaldivaremc2.github.io/demucs-backend"]}})

# Replace with your actual Google Client ID (from Google Cloud Console)
GOOGLE_CLIENT_ID = "136078894256-6e15kiau376eja7htp018igfh72cbpue.apps.googleusercontent.com" 

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

def verify_google_token(token):
    """Verifies a Google ID Token."""
    try:
        # Specify the CLIENT_ID of the app that accesses the backend:
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)

        # Or, if multiple clients access the backend server:
        # idinfo = id_token.verify_oauth2_token(token, requests.Request())
        # if idinfo['aud'] not in [CLIENT_ID_1, CLIENT_ID_2, CLIENT_ID_3]:
        #     raise ValueError('Could not verify audience.')

        # If token is valid, you can get user info like:
        # userid = idinfo['sub']
        # email = idinfo['email']
        # print(f"Authenticated user: {email} (ID: {userid})")
        return True
    except ValueError as e:
        print(f"Token verification failed: {e}")
        return False

@app.route('/upload-audio', methods=['POST'])
def upload_audio():
    # Authentication Check
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "Authorization token missing or invalid"}), 401
    
    token = auth_header.split(' ')[1]
    if not verify_google_token(token):
        return jsonify({"error": "Authentication failed. Invalid token."}), 401

    # File and Separation Mode Checks
    if 'audioFile' not in request.files:
        return jsonify({"error": "No audio file part in the request"}), 400

    audio_file = request.files['audioFile']
    separation_mode = request.form.get('separation_mode', 'separate_all') # Default to separate_all

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

        # Define stem paths (Demucs outputs to a subdirectory like demucs/audio_filename/)
        # Adjust this path based on actual Demucs output structure
        # Demucs typically creates a structure like output_dir_path/demucs/model_name/input_audio_name/stems.wav
        # We need to find the actual directory containing the stems.
        stem_base_dir = None
        for root, dirs, files in os.walk(output_dir_path):
            if any(f.endswith(".wav") for f in files) and "vocals.wav" in files: # Heuristic to find stem dir
                stem_base_dir = root
                break
        
        if not stem_base_dir:
            return jsonify({"error": "Could not find separated audio stems."}), 500

        stems = {
            "vocals": os.path.join(stem_base_dir, "vocals.wav"),
            "drums": os.path.join(stem_base_dir, "drums.wav"),
            "bass": os.path.join(stem_base_dir, "bass.wav"),
            "other": os.path.join(stem_base_dir, "other.wav")
        }

        # --- Handle Separation Modes ---
        if separation_mode == 'separate_all':
            # Convert all WAV files to MP3 to save space
            print("Converting all WAV files to MP3...")
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
            
            # Create archive of the entire separated directory
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
                return jsonify({"error": "Failed to create compressed archive for separate_all."}), 500

            print(f"Sending file: {archive_path}")
            return send_file(archive_path, as_attachment=True, download_name=archive_name, mimetype='application/gzip')

        else: # Mute specific stems and mix the rest
            stems_to_keep = []
            if separation_mode == 'mute_guitar_other':
                stems_to_keep = [stems["vocals"], stems["drums"], stems["bass"]]
            elif separation_mode == 'mute_voice':
                stems_to_keep = [stems["drums"], stems["bass"], stems["other"]]
            elif separation_mode == 'mute_drums':
                stems_to_keep = [stems["vocals"], stems["bass"], stems["other"]]
            else:
                return jsonify({"error": "Invalid separation mode selected."}), 400

            # Filter out non-existent files
            stems_to_keep = [s for s in stems_to_keep if os.path.exists(s)]
            
            if not stems_to_keep:
                return jsonify({"error": "No stems to mix based on selection. Processing might have failed or input was empty."}), 500

            output_mixed_mp3_name = f"{audio_file.filename.rsplit('.', 1)[0]}_mixed.mp3"
            output_mixed_mp3_path = os.path.join(temp_dir, output_mixed_mp3_name)

            # Build ffmpeg command for mixing
            ffmpeg_mix_command = ["ffmpeg", "-y"]
            input_maps = []
            filter_complex_inputs = []

            for i, stem_path in enumerate(stems_to_keep):
                ffmpeg_mix_command.extend(["-i", stem_path])
                filter_complex_inputs.append(f"[{i}:a]")
            
            # Dynamically build amerge filter
            amerge_filter = f"{''.join(filter_complex_inputs)}amerge=inputs={len(stems_to_keep)}[a]"
            
            ffmpeg_mix_command.extend([
                "-filter_complex", amerge_filter,
                "-map", "[a]",
                "-ac", "2", # Ensure stereo output
                "-codec:a", "libmp3lame",
                "-qscale:a", "2", # Quality setting (0-9, 0 is best)
                output_mixed_mp3_path
            ])
            
            print(f"Running FFmpeg mix command: {' '.join(ffmpeg_mix_command)}")
            mix_process = subprocess.run(ffmpeg_mix_command, capture_output=True, text=True, check=True)
            print("FFmpeg mix stdout:\n", mix_process.stdout)
            print("FFmpeg mix stderr:\n", mix_process.stderr)

            if not os.path.exists(output_mixed_mp3_path):
                return jsonify({"error": "Failed to mix audio stems."}), 500

            print(f"Sending mixed file: {output_mixed_mp3_path}")
            return send_file(output_mixed_mp3_path, as_attachment=True, download_name=output_mixed_mp3_name, mimetype='audio/mpeg')

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
