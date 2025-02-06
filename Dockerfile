# Use official Python runtime as the base image
FROM python:3.9-slim

# Set working directory in container
WORKDIR /app

# Copy requirements (if you have any) and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the project files into the container
COPY src/ .

# Command to run the application
CMD ["python", "main.py"]