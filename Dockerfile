FROM debian:10

RUN apt-get update && \
    apt-get install -y build-essential python3-pip \
      libpq-dev libffi-dev python3-dev postgresql-client && \
    rm -rf /var/lib/apt/lists/*

ADD ./requirements_base.txt /requirements/pip/base.txt
RUN pip3 install --require-hashes -r /requirements/pip/base.txt

ADD ./requirements_dev.txt /requirements/pip/dev.txt
RUN pip3 install --require-hashes -r /requirements/pip/dev.txt

ADD ./requirements_tests.txt /requirements/pip/tests.txt
RUN pip3 install --require-hashes -r /requirements/pip/tests.txt

ADD . /app
WORKDIR /app
