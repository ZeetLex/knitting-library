# This file tells Docker how to build the backend server container.
# Uses Alpine Linux for a much smaller image size (~200MB vs ~750MB).

FROM python:3.11-alpine
LABEL org.opencontainers.image.source="https://github.com/ZeetLex/knitting-library"

# Install only what we actually need:
#   poppler     - converts PDF pages to images for thumbnails
#   gcc/musl    - needed to compile some Python packages on Alpine
#   zlib/jpeg   - image format support for Pillow
# All install caches are cleaned in the same layer to keep image size down
RUN apk add --no-cache \
    poppler-utils \
    gcc \
    musl-dev \
    zlib-dev \
    jpeg-dev \
    libffi-dev

# Set the working directory inside the container
WORKDIR /app

# Copy and install Python dependencies first (this layer is cached by Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend code
COPY . .

# Start the FastAPI server on port 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
