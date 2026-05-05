FROM mambaorg/micromamba:latest

USER root
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libmagic1 \
    build-essential \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN chown micromamba:micromamba /app

USER micromamba

# Copy environment first to leverage Docker cache
COPY --chown=micromamba:micromamba environment.yml .
RUN micromamba install -y -n base -f environment.yml && \
    micromamba clean --all --yes

# Create English-named directory structure
RUN mkdir -p data/falkordb data/raw data/lancedb data/processed src

# Copy source code and config
COPY --chown=micromamba:micromamba src/ ./src/
COPY --chown=micromamba:micromamba .env .

# Set environment paths
ENV PATH="/opt/conda/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app"

# KEEP ALIVE: This command keeps the container running forever.
# It allows you to enter via 'docker exec' or run 'make' commands at any time.
CMD ["tail", "-f", "/dev/null"]