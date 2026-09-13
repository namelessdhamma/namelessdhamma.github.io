FROM python:3.12-alpine
WORKDIR /app
COPY . /app
CMD ["python","-u","tmp/nd_v54_clean_context_loader.py"]
