FROM debian:10

RUN apt-get update && \
    apt-get install -y build-essential python3-pip \
      libpq-dev libffi-dev python3-dev postgresql-client && \
    rm -rf /var/lib/apt/lists/*


COPY requirements_*.txt /tmp/

RUN pip3 install --require-hashes -r /tmp/requirements_base.txt \
      -r /tmp/requirements_tests.txt \
      -r /tmp/requirements_dev.txt

COPY . /app
WORKDIR /app
