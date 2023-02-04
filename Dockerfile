
FROM ubuntu:focal

# install prerequisites
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -y && apt-get install -y python3 make

# build data directory
RUN mkdir -p /usr/local/opa64/data && mkdir -p /data && ln -s /data /usr/local/opa64/data
COPY data/db.json /usr/local/opa64/data/

# copy scripts
COPY index.html opv86.css opv86.js jquery.min.js Makefile /usr/local/opa64/

# run
ENTRYPOINT ["make", "DIR=/data", "DB_DIR=/usr/local/opa64/data", "SCRIPT_DIR=/usr/local/opa64", "-f", "/usr/local/opa64/Makefile", "start"]
