# Use a slim version of Python 3.11 for a smaller image size
# This version can most likely be updated
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Prevent Python from writing .pyc files to disc
ENV PYTHONDONTWRITEBYTECODE=1
# Prevent Python from buffering stdout and stderr
ENV PYTHONUNBUFFERED=1

# Install system dependencies?
# RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

# Copy the requirements files first to leverage Docker cache
COPY template_requirements.txt bot_requirements.txt ./

# Install python dependencies
RUN pip install --no-cache-dir -r template_requirements.txt && \
    pip install --no-cache-dir -r bot_requirements.txt

# Copy the rest of the application code
COPY . .

# Create volumes for persistent data (logs and configuration)
VOLUME ["/app/logs", "/app/configuration"]

# Command to run the bot
CMD ["python", "bot.py"]