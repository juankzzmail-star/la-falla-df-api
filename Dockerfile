FROM python:3.12-slim

WORKDIR /app

COPY auditoria_qa.py ./auditoria_qa.py

COPY api_stakeholders/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY api_stakeholders/ ./api_stakeholders/

EXPOSE 8000

CMD ["uvicorn", "api_stakeholders.main:app", "--host", "0.0.0.0", "--port", "8000"]
