# Контекст сборки — корень репозитория (нужен libs/contracts)
FROM python:3.11-slim
WORKDIR /srv
COPY services/gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY libs/contracts ./libs/contracts
RUN pip install --no-cache-dir ./libs/contracts
COPY services/gateway/app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
