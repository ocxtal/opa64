
FROM ubuntu:latest

# install prerequisites
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -y && apt-get install -y python3 make

# build data directory
RUN mkdir -p /opa64/data

COPY index.html opv86.css opv86.js jquery.min.js Makefile /opa64/
COPY data/db.json /opa64/data/

# run
ENTRYPOINT ["make", "DIR=/data", "DB_DIR=/opa64/data", "SCRIPT_DIR=/opa64", "-f", "/opa64/Makefile", "start"]
