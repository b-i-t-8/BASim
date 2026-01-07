FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    debian-keyring \
    debian-archive-keyring \
    apt-transport-https \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Caddy
RUN curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
    && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list \
    && apt-get update \
    && apt-get install -y caddy \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY models/ ./models/
COPY main.py .
COPY interfaces.py .
COPY servers.py .
COPY profiles/ ./profiles/
COPY profiles.py .
COPY web/ ./web/
COPY Caddyfile /etc/caddy/Caddyfile

# Expose ports
# HTTPS
EXPOSE 443
# HTTP (redirect)
EXPOSE 80
# BACnet (UDP)
EXPOSE 47808/udp
# Modbus (TCP)
EXPOSE 5020


# Environment Variables Defaults
ENV CAMPUS_SIZE="Small"
ENV GEO_LAT="36.16"
ENV SIMULATION_SPEED="1.0"
ENV PYTHONUNBUFFERED=1
ENV RUNNING_IN_DOCKER=true
# Caddy data directories for certificate persistence
ENV XDG_DATA_HOME=/data
ENV XDG_CONFIG_HOME=/config

# Start script to run both Caddy and Python app
COPY start.sh .
RUN chmod +x start.sh

CMD ["./start.sh"]
