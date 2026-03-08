# This file tells Docker how to build the backend server container.
# It installs Python, the required libraries, and starts the API server.

FROM python:3.11-slim

# Install system tools needed for PDF thumbnail generation (poppler)
# and image processing (libgl1)
RUN apt-get update && apt-get install -y \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# Copy and install Python dependencies first (this is cached by Docker for speed)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend code
COPY . .

# Start the FastAPI server on port 8000
# --host 0.0.0.0 makes it accessible from outside the container
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
