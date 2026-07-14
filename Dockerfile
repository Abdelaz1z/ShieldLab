# ShieldLab — container image (portable: Hugging Face Spaces, Render, Fly.io, Cloud Run, any VPS)
# Streamlit multipage app. Python is pinned to 3.11 to match the environment the
# surrogate_bundle.joblib pickle was built with (see requirements.txt: scikit-learn==1.9.0).
FROM python:3.11-slim

# Hugging Face Spaces runs the container as a non-root user with UID 1000. Create it so
# file ownership and Streamlit's cache/config writes work the same locally and on the Space.
RUN useradd --create-home --uid 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    # Streamlit: run headless, bind all interfaces, no telemetry
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR $HOME/app

# Install deps first so this layer caches unless requirements.txt changes.
# The pinned wheels (scikit-learn, numpy, matplotlib) ship manylinux cp311 wheels,
# so no apt build toolchain is needed on slim.
COPY --chown=user requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# App source (models/ included — the surrogate bundle must ship with the image).
COPY --chown=user . .

EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
