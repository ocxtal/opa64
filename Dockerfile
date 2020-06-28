
FROM ubuntu:focal
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -y && apt-get install -y python3 python3-opencv python3-pip ghostscript make && pip3 install camelot-py requests
RUN mkdir -p /usr/local/opa64 && mkdir -p /data && ln -s /data /usr/local/opa64/data
COPY index.html /usr/local/opa64/.
COPY opv86.css /usr/local/opa64/.
COPY opv86.js /usr/local/opa64/.
COPY jquery.min.js /usr/local/opa64/.
COPY opa64.py /usr/local/opa64/.
COPY Makefile /usr/local/opa64/.
CMD make DIR=/data DB_DIR=/usr/local/opa64/data SCRIPT_DIR=/usr/local/opa64 -f /usr/local/opa64/Makefile start

