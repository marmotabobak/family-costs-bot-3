FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY bot/ bot/
COPY migrations/ migrations/
COPY alembic.ini .

# Expose web UI port
EXPOSE 8000

# Run the bot
CMD ["python", "-m", "bot.main"]
