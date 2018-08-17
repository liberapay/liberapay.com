FROM debian:9

RUN apt-get update && \
    apt-get install -y build-essential wget libpq-dev libffi-dev python-dev postgresql-client && \
    rm -rf /var/lib/apt/lists/*

RUN wget -O /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py && python /tmp/get-pip.py

ADD ./requirements_base.txt /requirements/pip/base.txt
RUN pip install --require-hashes -r /requirements/pip/base.txt

ADD ./requirements_dev.txt /requirements/pip/dev.txt
RUN pip install --require-hashes -r /requirements/pip/dev.txt

ADD ./requirements_tests.txt /requirements/pip/tests.txt
RUN pip install --require-hashes -r /requirements/pip/tests.txt

ADD . /app
WORKDIR /app
