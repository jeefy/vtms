FROM python:3.13-slim

RUN apt-get update && apt-get install -y build-essential

# Set the working directory
WORKDIR /app
# Copy requirements 
COPY requirements.txt /app/requirements.txt

# Install any needed packages specified in requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . /app/

ENTRYPOINT ["python3", "-u", "client.py"]