FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY prepare_data.py safechem_data.py train_model.py ./
RUN python prepare_data.py && python train_model.py

COPY app.py dashboard.css ./
COPY .streamlit/config.toml .streamlit/config.toml

EXPOSE 8080
CMD ["sh", "-c", "exec streamlit run app.py --server.headless true --server.address 0.0.0.0 --server.port \"${PORT:-8080}\""]
