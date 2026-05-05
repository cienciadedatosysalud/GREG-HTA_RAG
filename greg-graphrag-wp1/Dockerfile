FROM mambaorg/micromamba:latest

USER root
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libmagic1 \
    build-essential \
    && apt-get clean && rm -rf /var/lib/apt/lists/*


WORKDIR /app

COPY --chown=$MAMBA_USER:$MAMBA_USER environment.yml .
RUN micromamba install -y -n base -f environment.yml && \
    micromamba clean --all --yes

# Create directory structure
RUN mkdir -p data/falkordb data/raw data/lancedb data/processed src


COPY --chown=$MAMBA_USER:$MAMBA_USER src/ ./src/
COPY --chown=$MAMBA_USER:$MAMBA_USER .env .


ENV PATH="/opt/conda/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app"


CMD ["tail", "-f", "/dev/null"]