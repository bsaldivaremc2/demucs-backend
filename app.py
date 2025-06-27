#app.py - Flask Backend for Audio Splitting

import os
import subprocess
import tempfile
import shutil
from datetime import datetime
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS # Import CORS

app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# Define the maximum file size (20 MB)
MAX_FILE_SIZE = 20 * 1024 * 1024 # 20 megabytes in bytes

@app.route('/upload-audio', methods=['POST'])
def upload_audio():
    # Check if a file was uploaded
    if 'audioFile' not in request.files:
        return jsonify({"error": "No audio file part in the request"}), 400

    audio_file = request.files['audioFile']

    # Check if the file name is empty
    if audio_file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # Check file extension
    if not audio_file.filename.lower().endswith('.mp3'):
        return jsonify({"error": "Only MP3 files are allowed"}), 400

    # Check file size
    audio_file.seek(0, os.SEEK_END)
    file_size = audio_file.tell()
    audio_file.seek(0) # Reset file pointer to the beginning
    if file_size > MAX_FILE_SIZE:
        return jsonify({"error": f"File size exceeds {MAX_FILE_SIZE / (1024 * 1024)}MB limit"}), 413 # 413 Request Entity Too Large

    # Create a temporary directory to store the uploaded file and demucs output
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Save the uploaded audio file to the temporary directory
        input_audio_path = os.path.join(temp_dir, audio_file.filename)
        audio_file.save(input_audio_path)
        print(f"Uploaded file saved to: {input_audio_path}")

        # Generate a unique output directory name based on timestamp
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f") # Added microseconds for more uniqueness
        output_dir_name = f"separated_tmp_{timestamp}"
        output_dir_path = os.path.join(temp_dir, output_dir_name)

        # Run Demucs
        # The -o flag specifies the output directory. Demucs will create it inside temp_dir.
        demucs_command = ["demucs", input_audio_path, "-o", output_dir_path]
        print(f"Running Demucs command: {' '.join(demucs_command)}")
        
        # Capture stdout and stderr to help debug
        process = subprocess.run(demucs_command, capture_output=True, text=True, check=True)
        print("Demucs stdout:\n", process.stdout)
        print("Demucs stderr:\n", process.stderr)

        # Check if Demucs created the expected output directory
        if not os.path.isdir(output_dir_path):
            print(f"Error: Demucs output directory not found at {output_dir_path}")
            return jsonify({"error": "Demucs processing failed or output directory not found."}), 500
        
        # Compress the Demucs output directory
        archive_name = f"{output_dir_name}.tar.gz"
        archive_path = os.path.join(temp_dir, archive_name)
        
        # Create a tar.gz archive of the demucs output directory
        # The base directory for tar should be the parent of output_dir_path,
        # and the name to archive should be just output_dir_name.
        print(f"Compressing {output_dir_path} to {archive_path}")
        # Change current working directory to temp_dir before tar to ensure correct pathing
        original_cwd = os.getcwd()
        os.chdir(temp_dir)
        tar_command = ["tar", "-czvf", archive_name, output_dir_name]
        process = subprocess.run(tar_command, capture_output=True, text=True, check=True)
        print("Tar stdout:\n", process.stdout)
        print("Tar stderr:\n", process.stderr)
        os.chdir(original_cwd) # Change back to original working directory
        
        # Check if the archive was created
        if not os.path.exists(archive_path):
            print(f"Error: Archive file not found at {archive_path}")
            return jsonify({"error": "Failed to create compressed archive."}), 500

        # Send the compressed file back to the client
        print(f"Sending file: {archive_path}")
        return send_file(archive_path, as_attachment=True, download_name=archive_name, mimetype='application/gzip')

    except subprocess.CalledProcessError as e:
        print(f"Demucs or Tar command failed: {e}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        return jsonify({"error": f"Processing failed: {e.stderr}"}), 500
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500
    finally:
        # Clean up the temporary directory and its contents
        if os.path.exists(temp_dir):
            print(f"Cleaning up temporary directory: {temp_dir}")
            shutil.rmtree(temp_dir)


if __name__ == '__main__':
    # Listen on all available network interfaces
    app.run(host='0.0.0.0', port=5000, debug=True) # debug=True for development, set to False in production
