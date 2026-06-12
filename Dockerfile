FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project source
COPY src/ ./src/
COPY run_pipeline.py .

# Expose Streamlit default port
EXPOSE 8501

# Default: run full pipeline then start dashboard
CMD ["sh", "-c", "python run_pipeline.py && streamlit run src/dashboard/app.py --server.address=0.0.0.0 --server.port=8501"]
