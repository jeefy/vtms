FROM python:3.13-slim

RUN apt-get update && apt-get install -y build-essential

# Set the working directory
WORKDIR /app
# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

ENTRYPOINT ["python3", "client.py"]