# Dockerfile for the Demucs Audio Splitter Backend

# Use an official Python runtime as a parent image
FROM python:3.9-slim-buster

# Set the working directory in the container
WORKDIR /app

# Install necessary system dependencies for sound processing (might be needed by demucs dependencies)
# and build-essential for compiling some Python packages
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy the Flask application files into the container at /app
COPY app.py .

# Install Python dependencies
# First, install demucs from git
# Then, specifically handle the numpy version as per the user's request
RUN python3 -m pip install -U git+https://github.com/facebookresearch/demucs#egg=demucs && \
    pip uninstall -y numpy && \
    pip install numpy==1.26.4 && \
    pip install Flask flask_cors

# Expose the port the app runs on
EXPOSE 5000

# Run the Flask application
CMD ["python3", "app.py"]
