FROM python:3.8

# Create working directory
WORKDIR /app

# Copy requirements. From source, to destination.
COPY requirements.txt ./requirements.txt

# Install dependencies
RUN pip3 install -r requirements.txt

# Set $PORT environment variable
ENV PORT 8080
ENV CLOUD False
ENV NEO4JUSER neo4j

# Use this when running container locally
ENV PWORD test
#ENV GRAPHURI bolt://0.0.0.0:7687
ENV GRAPHURI bolt://127.0.0.1:7687


# Expose port
EXPOSE 8080

# copying all files over. From source, to destination.
COPY . /app

#Run app
#CMD ["gunicorn", "--workers", "3", "--threads", "2", "app:app", "-b", ":8080"]
CMD ["gunicorn", "--threads", "3", "app:app", "-b", ":8080"]
#CMD python app.py

