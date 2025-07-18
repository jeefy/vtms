TOPDIR=$(PWD)
WHOAMI=$(shell whoami)

requirements:
	bin/pip3 install -r requirements.txt

server:
	bin/python3 -m flask --app server run

client:
	bin/python3 client.py

image:
	docker build -t $(WHOAMI)/vtms:latest .

make image-run: image
	docker run -v ./data/:/app/data --privileged --rm --name vtms $(WHOAMI)/vtms:latest

make image-push: image
	docker push $(WHOAMI)/vtms:latest